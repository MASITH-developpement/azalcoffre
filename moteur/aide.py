# =============================================================================
# AZALPLUS - Service d'Aide et Documentation
# =============================================================================
"""
Gestion de l'aide in-app et de la documentation contextuelle.
- Chargement et rendu des fichiers Markdown
- Recherche dans le contenu d'aide
- Aide contextuelle par module
- Visite guidee (onboarding)
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pathlib import Path
from typing import Optional, Dict, Any, List
import re
import structlog
from dataclasses import dataclass

from .auth import require_auth
from .ui import generate_layout, get_all_modules

logger = structlog.get_logger()

# =============================================================================
# Configuration
# =============================================================================

AIDE_DIR = Path(__file__).parent.parent / "config" / "aide"

# Mapping module -> fichier d'aide
MODULE_HELP_MAP = {
    "devis": "devis.md",
    "factures": "factures.md",
    "facture": "factures.md",
    "clients": "clients.md",
    "client": "clients.md",
    "interventions": "interventions.md",
    "produits": "produits.md",
}

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class HelpArticle:
    """Article d'aide."""
    slug: str
    title: str
    content: str
    html: str
    sections: List[Dict[str, str]]


@dataclass
class SearchResult:
    """Resultat de recherche."""
    slug: str
    title: str
    excerpt: str
    score: float


# =============================================================================
# Service d'Aide
# =============================================================================

class AideService:
    """Service de gestion de l'aide et documentation."""

    _cache: Dict[str, HelpArticle] = {}
    _search_index: Dict[str, List[str]] = {}  # mot -> [slugs]

    @classmethod
    def load_article(cls, slug: str) -> Optional[HelpArticle]:
        """Charge un article d'aide depuis le cache ou le fichier."""

        # Verifier le cache
        if slug in cls._cache:
            return cls._cache[slug]

        # Determiner le fichier
        filename = f"{slug}.md"
        filepath = AIDE_DIR / filename

        if not filepath.exists():
            logger.warning("aide_article_not_found", slug=slug)
            return None

        try:
            content = filepath.read_text(encoding="utf-8")
            html = cls._markdown_to_html(content)
            title = cls._extract_title(content)
            sections = cls._extract_sections(content)

            article = HelpArticle(
                slug=slug,
                title=title,
                content=content,
                html=html,
                sections=sections
            )

            cls._cache[slug] = article
            cls._index_article(article)

            return article

        except Exception as e:
            logger.error("aide_load_error", slug=slug, error=str(e))
            return None

    @classmethod
    def list_articles(cls) -> List[Dict[str, str]]:
        """Liste tous les articles d'aide disponibles."""
        articles = []

        if not AIDE_DIR.exists():
            return articles

        for filepath in AIDE_DIR.glob("*.md"):
            slug = filepath.stem
            content = filepath.read_text(encoding="utf-8")
            title = cls._extract_title(content)
            description = cls._extract_description(content)

            articles.append({
                "slug": slug,
                "title": title,
                "description": description,
                "url": f"/ui/aide/{slug}"
            })

        return articles

    @classmethod
    def search(cls, query: str, limit: int = 10) -> List[SearchResult]:
        """Recherche dans le contenu d'aide."""

        if not query or len(query) < 2:
            return []

        # Charger tous les articles si pas encore fait
        cls._ensure_index_loaded()

        results = []
        query_lower = query.lower()
        query_words = query_lower.split()

        for slug, article in cls._cache.items():
            score = 0.0
            content_lower = article.content.lower()

            # Score titre
            if query_lower in article.title.lower():
                score += 10.0

            # Score contenu
            for word in query_words:
                if word in content_lower:
                    count = content_lower.count(word)
                    score += min(count * 0.5, 5.0)  # Max 5 points par mot

            if score > 0:
                excerpt = cls._extract_excerpt(article.content, query)
                results.append(SearchResult(
                    slug=slug,
                    title=article.title,
                    excerpt=excerpt,
                    score=score
                ))

        # Trier par score decroissant
        results.sort(key=lambda x: x.score, reverse=True)

        return results[:limit]

    @classmethod
    def get_contextual_help(cls, module_name: str) -> Optional[HelpArticle]:
        """Retourne l'aide contextuelle pour un module."""

        slug = MODULE_HELP_MAP.get(module_name.lower())
        if slug:
            slug = slug.replace(".md", "")
            return cls.load_article(slug)

        return None

    @classmethod
    def get_onboarding_steps(cls) -> List[Dict[str, Any]]:
        """Retourne les etapes de la visite guidee."""

        return [
            {
                "element": ".sidebar-logo",
                "title": "Bienvenue sur AZALPLUS",
                "intro": "Votre logiciel de gestion tout-en-un. Suivez cette visite pour decouvrir les fonctionnalites principales.",
                "position": "right"
            },
            {
                "element": ".header-search",
                "title": "Recherche globale",
                "intro": "Recherchez rapidement clients, factures, devis... dans toute l'application. Raccourci : Ctrl+K",
                "position": "bottom"
            },
            {
                "element": ".sidebar-nav",
                "title": "Navigation",
                "intro": "Accedez a tous les modules depuis ce menu : Clients, Devis, Factures, Interventions...",
                "position": "right"
            },
            {
                "element": ".stats-row",
                "title": "Tableau de bord",
                "intro": "Visualisez vos indicateurs cles en un coup d'oeil.",
                "position": "bottom"
            },
            {
                "element": ".header-actions .btn-primary",
                "title": "Actions rapides",
                "intro": "Creez rapidement un nouveau devis ou facture depuis n'importe quelle page.",
                "position": "left"
            },
            {
                "element": ".header-notif",
                "title": "Notifications",
                "intro": "Restez informe des alertes importantes : factures en retard, devis a relancer...",
                "position": "left"
            },
            {
                "element": ".sidebar-user",
                "title": "Votre profil",
                "intro": "Gerez votre compte et vos preferences ici.",
                "position": "top"
            }
        ]

    @classmethod
    def _markdown_to_html(cls, content: str) -> str:
        """Convertit le Markdown en HTML (conversion simplifiee)."""

        html = content

        # Titres
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # Gras et italique
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

        # Liens
        html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)

        # Code inline
        html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)

        # Blocs de code
        html = re.sub(r'```(\w*)\n(.*?)```', r'<pre><code class="language-\1">\2</code></pre>', html, flags=re.DOTALL)

        # Tableaux (simple)
        lines = html.split('\n')
        in_table = False
        table_lines = []
        result_lines = []

        for line in lines:
            if '|' in line and not line.strip().startswith('```'):
                if not in_table:
                    in_table = True
                    table_lines = []
                table_lines.append(line)
            else:
                if in_table:
                    result_lines.append(cls._convert_table(table_lines))
                    in_table = False
                    table_lines = []
                result_lines.append(line)

        if in_table:
            result_lines.append(cls._convert_table(table_lines))

        html = '\n'.join(result_lines)

        # Listes
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'^(\d+)\. (.+)$', r'<li>\2</li>', html, flags=re.MULTILINE)

        # Grouper les <li> en <ul>
        html = re.sub(r'(<li>.*?</li>\n?)+', lambda m: '<ul>' + m.group(0) + '</ul>', html)

        # Paragraphes
        paragraphs = html.split('\n\n')
        processed = []
        for p in paragraphs:
            p = p.strip()
            if p and not p.startswith('<'):
                p = f'<p>{p}</p>'
            processed.append(p)
        html = '\n\n'.join(processed)

        # Separateurs
        html = re.sub(r'^---+$', '<hr>', html, flags=re.MULTILINE)

        return html

    @classmethod
    def _convert_table(cls, lines: List[str]) -> str:
        """Convertit un tableau Markdown en HTML."""

        if len(lines) < 2:
            return '\n'.join(lines)

        html = '<table class="help-table">\n<thead>\n<tr>'

        # En-tete
        headers = [cell.strip() for cell in lines[0].split('|') if cell.strip()]
        for header in headers:
            html += f'<th>{header}</th>'
        html += '</tr>\n</thead>\n<tbody>'

        # Lignes (sauter la ligne de separateurs)
        for line in lines[2:]:
            cells = [cell.strip() for cell in line.split('|') if cell.strip()]
            if cells:
                html += '\n<tr>'
                for cell in cells:
                    html += f'<td>{cell}</td>'
                html += '</tr>'

        html += '\n</tbody>\n</table>'
        return html

    @classmethod
    def _extract_title(cls, content: str) -> str:
        """Extrait le titre du document."""

        match = re.search(r'^# (.+)$', content, re.MULTILINE)
        if match:
            return match.group(1)
        return "Sans titre"

    @classmethod
    def _extract_description(cls, content: str) -> str:
        """Extrait la premiere description du document."""

        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('-'):
                return line[:150] + "..." if len(line) > 150 else line
        return ""

    @classmethod
    def _extract_sections(cls, content: str) -> List[Dict[str, str]]:
        """Extrait les sections (h2) du document."""

        sections = []
        matches = re.findall(r'^## (.+)$', content, re.MULTILINE)

        for match in matches:
            slug = re.sub(r'[^a-z0-9]+', '-', match.lower()).strip('-')
            sections.append({
                "title": match,
                "anchor": slug
            })

        return sections

    @classmethod
    def _extract_excerpt(cls, content: str, query: str, context_size: int = 100) -> str:
        """Extrait un extrait du contenu autour de la requete."""

        content_lower = content.lower()
        query_lower = query.lower()

        pos = content_lower.find(query_lower)
        if pos == -1:
            # Chercher le premier mot
            for word in query_lower.split():
                pos = content_lower.find(word)
                if pos != -1:
                    break

        if pos == -1:
            return content[:200] + "..."

        start = max(0, pos - context_size)
        end = min(len(content), pos + len(query) + context_size)

        excerpt = content[start:end]

        # Nettoyer
        if start > 0:
            excerpt = "..." + excerpt
        if end < len(content):
            excerpt = excerpt + "..."

        return excerpt.replace('\n', ' ')

    @classmethod
    def _ensure_index_loaded(cls):
        """S'assure que tous les articles sont charges dans le cache."""

        if not AIDE_DIR.exists():
            return

        for filepath in AIDE_DIR.glob("*.md"):
            slug = filepath.stem
            if slug not in cls._cache:
                cls.load_article(slug)

    @classmethod
    def _index_article(cls, article: HelpArticle):
        """Indexe un article pour la recherche."""

        words = re.findall(r'\w+', article.content.lower())
        for word in set(words):
            if len(word) > 2:
                if word not in cls._search_index:
                    cls._search_index[word] = []
                if article.slug not in cls._search_index[word]:
                    cls._search_index[word].append(article.slug)


# =============================================================================
# Router API Aide
# =============================================================================

aide_router = APIRouter()


@aide_router.get("/", response_class=HTMLResponse)
async def help_center(request: Request, user: dict = Depends(require_auth)):
    """Centre d'aide principal."""

    # Charger l'index
    article = AideService.load_article("index")
    articles = AideService.list_articles()

    # Exclure l'index de la liste
    articles = [a for a in articles if a["slug"] != "index"]

    # Generer les cartes d'articles
    articles_html = ""
    icons = {
        "devis": "file-text",
        "factures": "receipt",
        "clients": "users",
        "raccourcis": "keyboard",
        "faq": "help-circle"
    }

    for a in articles:
        icon = icons.get(a["slug"], "book")
        articles_html += f'''
        <a href="/ui/aide/{a['slug']}" class="help-card">
            <div class="help-card-icon">{_get_help_icon(icon)}</div>
            <div class="help-card-content">
                <h3>{a['title']}</h3>
                <p>{a['description']}</p>
            </div>
        </a>
        '''

    content_html = article.html if article else "<p>Centre d'aide</p>"

    html = generate_layout(
        title="Centre d'aide",
        content=f'''
        <div class="help-center">
            <!-- Barre de recherche -->
            <div class="help-search-box">
                <form action="/ui/aide/recherche" method="GET" class="help-search-form">
                    <input type="text" name="q" placeholder="Rechercher dans l'aide..." class="input help-search-input">
                    <button type="submit" class="btn btn-primary">Rechercher</button>
                </form>
            </div>

            <!-- Contenu principal -->
            <div class="help-content">
                {content_html}
            </div>

            <!-- Articles populaires -->
            <div class="help-articles-section">
                <h2>Rubriques d'aide</h2>
                <div class="help-articles-grid">
                    {articles_html}
                </div>
            </div>

            <!-- Bouton visite guidee -->
            <div class="help-tour-section">
                <button onclick="startTour()" class="btn btn-secondary">
                    Demarrer la visite guidee
                </button>
            </div>
        </div>

        {_get_help_styles()}
        {_get_tour_scripts()}
        ''',
        user=user,
        modules=get_all_modules()
    )

    return HTMLResponse(content=html)


@aide_router.get("/recherche", response_class=HTMLResponse)
async def help_search(
    request: Request,
    q: str = Query("", min_length=0),
    user: dict = Depends(require_auth)
):
    """Recherche dans l'aide."""

    results = AideService.search(q) if q else []

    results_html = ""
    if results:
        for r in results:
            results_html += f'''
            <a href="/ui/aide/{r.slug}" class="help-search-result">
                <h3>{r.title}</h3>
                <p>{r.excerpt}</p>
            </a>
            '''
    elif q:
        results_html = '''
        <div class="help-no-results">
            <p>Aucun resultat pour votre recherche.</p>
            <p>Essayez avec d'autres termes ou consultez les rubriques ci-dessous.</p>
        </div>
        '''

    html = generate_layout(
        title=f"Recherche : {q}" if q else "Recherche dans l'aide",
        content=f'''
        <div class="help-center">
            <div class="help-search-box">
                <form action="/ui/aide/recherche" method="GET" class="help-search-form">
                    <input type="text" name="q" value="{q}" placeholder="Rechercher dans l'aide..." class="input help-search-input">
                    <button type="submit" class="btn btn-primary">Rechercher</button>
                </form>
            </div>

            <div class="help-search-results">
                {f'<h2>{len(results)} resultat(s) pour "{q}"</h2>' if q else ''}
                {results_html}
            </div>

            <div class="mt-6">
                <a href="/ui/aide" class="text-muted">Retour au centre d'aide</a>
            </div>
        </div>

        {_get_help_styles()}
        ''',
        user=user,
        modules=get_all_modules()
    )

    return HTMLResponse(content=html)


@aide_router.get("/onboarding/steps")
async def get_onboarding_steps(user: dict = Depends(require_auth)):
    """Retourne les etapes de la visite guidee (API JSON)."""

    return {"steps": AideService.get_onboarding_steps()}


@aide_router.get("/{topic}", response_class=HTMLResponse)
async def help_topic(
    topic: str,
    request: Request,
    user: dict = Depends(require_auth)
):
    """Page d'aide specifique."""

    article = AideService.load_article(topic)

    if not article:
        raise HTTPException(status_code=404, detail="Article non trouve")

    # Navigation sections
    sections_html = ""
    if article.sections:
        sections_html = '<div class="help-sections"><h4>Sommaire</h4><ul>'
        for s in article.sections:
            sections_html += f'<li><a href="#{s["anchor"]}">{s["title"]}</a></li>'
        sections_html += '</ul></div>'

    html = generate_layout(
        title=article.title,
        content=f'''
        <div class="help-article">
            <div class="help-breadcrumb">
                <a href="/ui/aide">Centre d'aide</a> / {article.title}
            </div>

            <div class="help-article-layout">
                <aside class="help-sidebar">
                    {sections_html}

                    <div class="help-related">
                        <h4>Articles lies</h4>
                        <ul>
                            <li><a href="/ui/aide/faq">FAQ</a></li>
                            <li><a href="/ui/aide/raccourcis">Raccourcis clavier</a></li>
                        </ul>
                    </div>
                </aside>

                <article class="help-article-content">
                    {article.html}
                </article>
            </div>

            <div class="help-feedback">
                <p>Cet article vous a-t-il ete utile ?</p>
                <button class="btn btn-sm btn-success" onclick="helpFeedback('yes')">Oui</button>
                <button class="btn btn-sm btn-secondary" onclick="helpFeedback('no')">Non</button>
            </div>
        </div>

        {_get_help_styles()}

        <script>
        function helpFeedback(value) {{
            alert('Merci pour votre retour !');
        }}
        </script>
        ''',
        user=user,
        modules=get_all_modules()
    )

    return HTMLResponse(content=html)


# =============================================================================
# Helpers
# =============================================================================

def _get_help_icon(icon_name: str) -> str:
    """Retourne l'emoji pour une icone."""
    icons = {
        "file-text": "📄",
        "receipt": "🧾",
        "users": "👥",
        "keyboard": "⌨️",
        "help-circle": "❓",
        "book": "📖",
        "search": "🔍"
    }
    return icons.get(icon_name, "📄")


def _get_help_styles() -> str:
    """Retourne les styles CSS pour l'aide."""

    return '''
    <style>
        .help-center {
            max-width: 900px;
            margin: 0 auto;
        }

        .help-search-box {
            margin-bottom: 32px;
        }

        .help-search-form {
            display: flex;
            gap: 12px;
        }

        .help-search-input {
            flex: 1;
            font-size: 16px;
            padding: 14px 18px;
        }

        .help-content {
            background: white;
            border-radius: 12px;
            padding: 32px;
            margin-bottom: 32px;
            border: 1px solid var(--gray-200);
        }

        .help-content h1 {
            margin-bottom: 16px;
            color: var(--gray-900);
        }

        .help-content h2 {
            margin-top: 24px;
            margin-bottom: 12px;
            color: var(--gray-800);
        }

        .help-content h3 {
            margin-top: 20px;
            margin-bottom: 8px;
            color: var(--gray-700);
        }

        .help-content p {
            margin-bottom: 12px;
            line-height: 1.7;
            color: var(--gray-600);
        }

        .help-content ul, .help-content ol {
            margin-bottom: 16px;
            padding-left: 24px;
        }

        .help-content li {
            margin-bottom: 6px;
            color: var(--gray-600);
        }

        .help-content code {
            background: var(--gray-100);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 14px;
        }

        .help-content pre {
            background: var(--gray-800);
            color: white;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            margin: 16px 0;
        }

        .help-content pre code {
            background: none;
            padding: 0;
            color: inherit;
        }

        .help-content a {
            color: var(--primary);
            text-decoration: none;
        }

        .help-content a:hover {
            text-decoration: underline;
        }

        .help-table {
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0;
        }

        .help-table th,
        .help-table td {
            padding: 12px;
            text-align: left;
            border: 1px solid var(--gray-200);
        }

        .help-table th {
            background: var(--gray-50);
            font-weight: 600;
        }

        .help-table tr:hover {
            background: var(--gray-50);
        }

        .help-articles-section {
            margin-bottom: 32px;
        }

        .help-articles-section h2 {
            margin-bottom: 16px;
        }

        .help-articles-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 16px;
        }

        .help-card {
            display: flex;
            gap: 16px;
            padding: 20px;
            background: white;
            border-radius: 12px;
            border: 1px solid var(--gray-200);
            text-decoration: none;
            transition: all 0.2s;
        }

        .help-card:hover {
            border-color: var(--primary);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            transform: translateY(-2px);
        }

        .help-card-icon {
            font-size: 32px;
            flex-shrink: 0;
        }

        .help-card-content h3 {
            margin: 0 0 8px 0;
            color: var(--gray-900);
            font-size: 16px;
        }

        .help-card-content p {
            margin: 0;
            color: var(--gray-500);
            font-size: 14px;
            line-height: 1.5;
        }

        .help-tour-section {
            text-align: center;
            padding: 32px;
            background: var(--primary-light);
            border-radius: 12px;
        }

        .help-search-results {
            min-height: 200px;
        }

        .help-search-result {
            display: block;
            padding: 16px;
            margin-bottom: 12px;
            background: white;
            border-radius: 8px;
            border: 1px solid var(--gray-200);
            text-decoration: none;
            transition: all 0.2s;
        }

        .help-search-result:hover {
            border-color: var(--primary);
            background: var(--primary-light);
        }

        .help-search-result h3 {
            margin: 0 0 8px 0;
            color: var(--gray-900);
        }

        .help-search-result p {
            margin: 0;
            color: var(--gray-600);
            font-size: 14px;
        }

        .help-no-results {
            text-align: center;
            padding: 48px;
            color: var(--gray-500);
        }

        .help-breadcrumb {
            margin-bottom: 24px;
            font-size: 14px;
            color: var(--gray-500);
        }

        .help-breadcrumb a {
            color: var(--primary);
            text-decoration: none;
        }

        .help-article-layout {
            display: grid;
            grid-template-columns: 220px 1fr;
            gap: 32px;
        }

        @media (max-width: 768px) {
            .help-article-layout {
                grid-template-columns: 1fr;
            }
            .help-sidebar {
                order: 2;
            }
        }

        .help-sidebar {
            position: sticky;
            top: 20px;
            height: fit-content;
        }

        .help-sections,
        .help-related {
            background: white;
            border-radius: 8px;
            padding: 16px;
            border: 1px solid var(--gray-200);
            margin-bottom: 16px;
        }

        .help-sections h4,
        .help-related h4 {
            margin: 0 0 12px 0;
            font-size: 14px;
            color: var(--gray-700);
        }

        .help-sections ul,
        .help-related ul {
            list-style: none;
            padding: 0;
            margin: 0;
        }

        .help-sections li,
        .help-related li {
            margin-bottom: 8px;
        }

        .help-sections a,
        .help-related a {
            color: var(--gray-600);
            text-decoration: none;
            font-size: 14px;
        }

        .help-sections a:hover,
        .help-related a:hover {
            color: var(--primary);
        }

        .help-article-content {
            background: white;
            border-radius: 12px;
            padding: 32px;
            border: 1px solid var(--gray-200);
        }

        .help-feedback {
            margin-top: 32px;
            padding: 24px;
            background: var(--gray-50);
            border-radius: 12px;
            text-align: center;
        }

        .help-feedback p {
            margin: 0 0 12px 0;
            color: var(--gray-700);
        }

        .help-feedback button {
            margin: 0 8px;
        }

        /* Icone d'aide contextuelle */
        .contextual-help-btn {
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 56px;
            height: 56px;
            border-radius: 50%;
            background: var(--primary);
            color: white;
            font-size: 24px;
            border: none;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            transition: all 0.2s;
            z-index: 1000;
        }

        .contextual-help-btn:hover {
            transform: scale(1.1);
            background: var(--primary-dark);
        }

        /* Tooltip aide */
        .help-tooltip {
            position: relative;
            display: inline-block;
            margin-left: 4px;
            cursor: help;
        }

        .help-tooltip .tooltip-text {
            visibility: hidden;
            width: 250px;
            background: var(--gray-800);
            color: white;
            text-align: left;
            border-radius: 6px;
            padding: 12px;
            position: absolute;
            z-index: 100;
            bottom: 125%;
            left: 50%;
            margin-left: -125px;
            opacity: 0;
            transition: opacity 0.2s;
            font-size: 13px;
            line-height: 1.5;
        }

        .help-tooltip:hover .tooltip-text {
            visibility: visible;
            opacity: 1;
        }
    </style>
    '''


def _get_tour_scripts() -> str:
    """Retourne les scripts pour la visite guidee."""

    return '''
    <script>
    // Visite guidee simplifiee (sans intro.js)
    async function startTour() {
        try {
            const res = await fetch('/ui/aide/onboarding/steps');
            const data = await res.json();
            const steps = data.steps;

            let currentStep = 0;

            function showStep(index) {
                // Nettoyer les anciens highlights
                document.querySelectorAll('.tour-highlight').forEach(el => {
                    el.classList.remove('tour-highlight');
                });
                document.querySelectorAll('.tour-tooltip').forEach(el => {
                    el.remove();
                });

                if (index >= steps.length) {
                    // Fin de la visite
                    localStorage.setItem('azalplus_tour_done', 'true');
                    alert('Visite terminee ! Vous pouvez maintenant explorer AZALPLUS.');
                    return;
                }

                const step = steps[index];
                const element = document.querySelector(step.element);

                if (!element) {
                    // Passer au suivant si element non trouve
                    showStep(index + 1);
                    return;
                }

                // Highlight element
                element.classList.add('tour-highlight');
                element.scrollIntoView({ behavior: 'smooth', block: 'center' });

                // Creer tooltip
                const tooltip = document.createElement('div');
                tooltip.className = 'tour-tooltip';
                tooltip.innerHTML = `
                    <div class="tour-title">${step.title}</div>
                    <div class="tour-text">${step.intro}</div>
                    <div class="tour-buttons">
                        <button onclick="tourPrev()" ${index === 0 ? 'disabled' : ''}>Precedent</button>
                        <span class="tour-progress">${index + 1} / ${steps.length}</span>
                        <button onclick="tourNext()">${index === steps.length - 1 ? 'Terminer' : 'Suivant'}</button>
                    </div>
                `;

                document.body.appendChild(tooltip);

                // Positionner tooltip
                const rect = element.getBoundingClientRect();
                tooltip.style.position = 'fixed';
                tooltip.style.top = (rect.bottom + 10) + 'px';
                tooltip.style.left = Math.max(10, Math.min(rect.left, window.innerWidth - 320)) + 'px';
            }

            window.tourNext = function() {
                currentStep++;
                showStep(currentStep);
            };

            window.tourPrev = function() {
                if (currentStep > 0) {
                    currentStep--;
                    showStep(currentStep);
                }
            };

            // Ajouter styles tour
            if (!document.getElementById('tour-styles')) {
                const style = document.createElement('style');
                style.id = 'tour-styles';
                style.textContent = `
                    .tour-highlight {
                        position: relative;
                        z-index: 999;
                        box-shadow: 0 0 0 4px var(--primary), 0 0 0 8px rgba(37, 99, 235, 0.2) !important;
                        border-radius: 8px;
                    }
                    .tour-tooltip {
                        position: fixed;
                        z-index: 1001;
                        background: white;
                        border-radius: 12px;
                        padding: 20px;
                        box-shadow: 0 8px 32px rgba(0,0,0,0.2);
                        max-width: 300px;
                        border: 1px solid var(--gray-200);
                    }
                    .tour-title {
                        font-weight: 700;
                        font-size: 16px;
                        margin-bottom: 8px;
                        color: var(--gray-900);
                    }
                    .tour-text {
                        color: var(--gray-600);
                        font-size: 14px;
                        line-height: 1.6;
                        margin-bottom: 16px;
                    }
                    .tour-buttons {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                    }
                    .tour-buttons button {
                        padding: 8px 16px;
                        border: 1px solid var(--gray-300);
                        background: white;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 13px;
                    }
                    .tour-buttons button:last-child {
                        background: var(--primary);
                        color: white;
                        border: none;
                    }
                    .tour-buttons button:disabled {
                        opacity: 0.5;
                        cursor: not-allowed;
                    }
                    .tour-progress {
                        font-size: 12px;
                        color: var(--gray-500);
                    }
                `;
                document.head.appendChild(style);
            }

            showStep(0);

        } catch (e) {
            console.error('Erreur visite guidee:', e);
            alert('Impossible de demarrer la visite guidee.');
        }
    }

    // Verifier si premiere visite
    document.addEventListener('DOMContentLoaded', function() {
        const tourDone = localStorage.getItem('azalplus_tour_done');
        // Ne pas demarrer auto pour le moment
        // if (!tourDone) { startTour(); }
    });
    </script>
    '''
