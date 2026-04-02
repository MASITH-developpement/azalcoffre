# =============================================================================
# AZALPLUS - Service de Connaissances Partagé
# =============================================================================
"""
Service de connaissances partagé entre Guardian et Marceau.

SÉPARATION STRICTE DES DONNÉES:

┌─────────────────────────────────────────────────────────────────┐
│  CONNAISSANCES GLOBALES (partagées) - TECHNIQUES UNIQUEMENT    │
│                                                                 │
│  ✅ Bases YAML techniques (config/knowledge/*.yml)              │
│     - python_programmation_index.yml                            │
│     - html_css_index.yml                                        │
│     - azal_stack_index.yml                                      │
│     - guardian_project_knowledge.yml                            │
│                                                                 │
│  ✅ Solutions Guardian (data/guardian_learnings/)               │
│     - Patterns d'erreur génériques                              │
│     - Solutions techniques sans données métier                  │
│                                                                 │
│  ❌ JAMAIS de données métier, clients, factures, etc.           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  CONNAISSANCES TENANT-SPECIFIC (privées) - NE PAS PARTAGER     │
│                                                                 │
│  🔒 Documents RAG tenant (data/rag/index_{tenant_id}.json)      │
│     - Documents métier appris par Marceau                       │
│     - Informations spécifiques à l'entreprise                   │
│                                                                 │
│  🔒 Données métier (PostgreSQL)                                 │
│     - Clients, factures, devis, etc.                            │
│                                                                 │
│  Guardian n'accède JAMAIS aux données tenant de Marceau        │
│  Marceau n'accède JAMAIS aux données tenant d'autres tenants   │
└─────────────────────────────────────────────────────────────────┘

AZAP-TENANT-001: Isolation stricte des données tenant
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field

import yaml

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeEntry:
    """Une entrée de connaissance."""
    id: str
    titre: str
    contenu: str
    source: str  # fichier YAML, web, RAG
    domaine: str
    type: str  # concept, exemple, commande, solution
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Résultat de recherche dans les connaissances."""
    entry: KnowledgeEntry
    score: float
    match_type: str  # exact, fuzzy, semantic


class SharedKnowledgeService:
    """
    Service de connaissances partagé.

    Fournit un accès unifié aux connaissances pour:
    - Guardian (débogage, solutions techniques)
    - Marceau (assistance utilisateur, métier)

    Sources:
    1. Bases YAML (config/knowledge/*.yml) - Globales
    2. RAG documents (data/rag/) - Par tenant
    3. Apprentissages Guardian (data/guardian_learnings/) - Globaux
    """

    # Chemins
    KNOWLEDGE_DIR = Path("/home/ubuntu/azalplus/config/knowledge")
    RAG_DIR = Path("/home/ubuntu/azalplus/data/rag")
    GUARDIAN_LEARNINGS_DIR = Path("/home/ubuntu/azalplus/data/guardian_learnings")

    # Cache des connaissances YAML (globales)
    _yaml_knowledge: Dict[str, List[KnowledgeEntry]] = {}
    _last_load: Optional[datetime] = None
    _cache_ttl = 300  # 5 minutes

    def __init__(self, tenant_id: Optional[UUID] = None):
        """
        Initialise le service.

        Args:
            tenant_id: ID du tenant pour les connaissances spécifiques.
                       None pour les connaissances globales uniquement.
        """
        self.tenant_id = tenant_id
        self._ensure_dirs()
        self._load_yaml_knowledge()

    def _ensure_dirs(self):
        """Crée les répertoires nécessaires."""
        self.KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        self.RAG_DIR.mkdir(parents=True, exist_ok=True)
        self.GUARDIAN_LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)

    def _load_yaml_knowledge(self, force: bool = False):
        """Charge les bases de connaissances YAML."""
        now = datetime.now()

        # Cache valide?
        if not force and self._last_load:
            elapsed = (now - self._last_load).total_seconds()
            if elapsed < self._cache_ttl and self._yaml_knowledge:
                return

        self._yaml_knowledge = {}

        # Charger tous les fichiers YAML
        for yaml_file in self.KNOWLEDGE_DIR.glob("*.yml"):
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}

                domaine = yaml_file.stem  # python_programmation, html_css, etc.
                entries = self._parse_yaml_knowledge(data, domaine, str(yaml_file))

                self._yaml_knowledge[domaine] = entries
                logger.debug(f"Loaded {len(entries)} entries from {yaml_file.name}")

            except Exception as e:
                logger.warning(f"Failed to load {yaml_file}: {e}")

        self._last_load = now
        logger.info(f"Knowledge loaded: {sum(len(v) for v in self._yaml_knowledge.values())} entries from {len(self._yaml_knowledge)} domains")

    def _parse_yaml_knowledge(
        self,
        data: Dict[str, Any],
        domaine: str,
        source: str
    ) -> List[KnowledgeEntry]:
        """Parse une structure YAML en entrées de connaissances."""
        entries = []

        def extract_entries(obj: Any, path: str = ""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_path = f"{path}/{key}" if path else key

                    # Si c'est une liste d'items avec contenu
                    if isinstance(value, list):
                        for i, item in enumerate(value):
                            if isinstance(item, dict):
                                titre = item.get('titre') or item.get('name') or item.get('concept') or f"{key}_{i}"
                                contenu = self._extract_content(item)
                                if contenu:
                                    entries.append(KnowledgeEntry(
                                        id=f"{domaine}:{new_path}:{i}",
                                        titre=titre,
                                        contenu=contenu,
                                        source=source,
                                        domaine=domaine,
                                        type=item.get('type', 'concept'),
                                        tags=item.get('tags', []),
                                        metadata=item.get('metadata', {})
                                    ))
                            elif isinstance(item, str) and len(item) > 20:
                                entries.append(KnowledgeEntry(
                                    id=f"{domaine}:{new_path}:{i}",
                                    titre=f"{key} - Item {i+1}",
                                    contenu=item,
                                    source=source,
                                    domaine=domaine,
                                    type="info",
                                    tags=[]
                                ))
                    elif isinstance(value, str) and len(value) > 50:
                        # Texte long = contenu intéressant
                        entries.append(KnowledgeEntry(
                            id=f"{domaine}:{new_path}",
                            titre=key,
                            contenu=value,
                            source=source,
                            domaine=domaine,
                            type="info",
                            tags=[]
                        ))
                    elif isinstance(value, dict):
                        extract_entries(value, new_path)

        extract_entries(data)
        return entries

    def _extract_content(self, item: Dict[str, Any]) -> str:
        """Extrait le contenu textuel d'un item."""
        content_fields = ['contenu', 'content', 'description', 'explication', 'definition', 'syntaxe', 'exemple']

        parts = []
        for field in content_fields:
            if field in item and item[field]:
                val = item[field]
                if isinstance(val, str):
                    parts.append(val)
                elif isinstance(val, list):
                    parts.extend(str(v) for v in val if v)

        return "\n".join(parts)

    def search(
        self,
        query: str,
        domaines: Optional[List[str]] = None,
        limit: int = 10,
        include_rag: bool = True,
        include_guardian: bool = True,
        caller: str = "unknown"
    ) -> List[SearchResult]:
        """
        Recherche dans les sources de connaissances AVEC ISOLATION.

        RÈGLES DE SÉCURITÉ:
        - Guardian: accède UNIQUEMENT aux bases YAML techniques et ses propres learnings
        - Marceau: accède aux bases YAML + RAG de SON tenant uniquement

        Args:
            query: Termes de recherche
            domaines: Filtrer par domaine (None = tous)
            limit: Nombre max de résultats
            include_rag: Inclure les documents RAG (SEULEMENT pour Marceau avec tenant_id)
            include_guardian: Inclure les apprentissages Guardian (techniques uniquement)
            caller: "guardian" ou "marceau" - détermine les accès

        Returns:
            Liste de résultats triés par pertinence
        """
        results: List[SearchResult] = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        # 1. Recherche dans les bases YAML TECHNIQUES (toujours autorisé)
        # Ces bases contiennent uniquement des connaissances techniques génériques
        for domaine, entries in self._yaml_knowledge.items():
            if domaines and domaine not in domaines:
                continue

            for entry in entries:
                score = self._calculate_score(query_lower, query_words, entry)
                if score > 0.1:
                    results.append(SearchResult(
                        entry=entry,
                        score=score,
                        match_type="fuzzy"
                    ))

        # 2. Recherche dans le RAG du tenant
        # SÉCURITÉ: Guardian n'accède JAMAIS au RAG (données métier sensibles)
        # SÉCURITÉ: Marceau accède UNIQUEMENT au RAG de SON tenant
        if include_rag and self.tenant_id and caller != "guardian":
            rag_results = self._search_rag(query, limit)
            results.extend(rag_results)

        # 3. Recherche dans les apprentissages Guardian
        # Ces apprentissages sont TECHNIQUES UNIQUEMENT (patterns d'erreur, solutions code)
        # Pas de données métier ou personnelles
        if include_guardian:
            guardian_results = self._search_guardian_learnings(query)
            results.extend(guardian_results)

        # Trier par score et limiter
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def search_technical(
        self,
        query: str,
        limit: int = 10
    ) -> List[SearchResult]:
        """
        Recherche UNIQUEMENT dans les connaissances techniques.
        Utilisé par Guardian - jamais d'accès aux données tenant.

        Sources:
        - Bases YAML techniques (Python, HTML/CSS, AZAL stack)
        - Solutions Guardian (patterns d'erreur génériques)

        JAMAIS:
        - Documents RAG (données métier)
        - Données tenant (PostgreSQL)
        """
        return self.search(
            query=query,
            limit=limit,
            include_rag=False,  # JAMAIS de RAG pour Guardian
            include_guardian=True,
            caller="guardian"
        )

    def _calculate_score(
        self,
        query_lower: str,
        query_words: set,
        entry: KnowledgeEntry
    ) -> float:
        """Calcule le score de pertinence d'une entrée."""
        score = 0.0

        titre_lower = entry.titre.lower()
        contenu_lower = entry.contenu.lower()

        # Match exact dans le titre (score élevé)
        if query_lower in titre_lower:
            score += 0.5

        # Mots de la query dans le titre
        titre_words = set(titre_lower.split())
        common_titre = query_words & titre_words
        if common_titre:
            score += 0.3 * (len(common_titre) / len(query_words))

        # Match dans le contenu
        if query_lower in contenu_lower:
            score += 0.2

        # Mots dans le contenu
        for word in query_words:
            if word in contenu_lower:
                score += 0.05

        # Bonus pour les tags correspondants
        for tag in entry.tags:
            if tag.lower() in query_lower:
                score += 0.1

        return min(score, 1.0)

    def _search_rag(self, query: str, limit: int) -> List[SearchResult]:
        """Recherche dans les documents RAG du tenant."""
        results = []

        if not self.tenant_id:
            return results

        index_file = self.RAG_DIR / f"index_{self.tenant_id}.json"
        if not index_file.exists():
            return results

        try:
            with open(index_file, 'r') as f:
                data = json.load(f)

            query_lower = query.lower()
            query_words = set(query_lower.split())

            for doc in data.get("documents", []):
                titre = doc.get("titre", "")
                contenu = doc.get("contenu", "")

                # Score simple basé sur les mots
                score = 0.0
                text = f"{titre} {contenu}".lower()

                for word in query_words:
                    if word in text:
                        score += 0.15

                if score > 0.1:
                    entry = KnowledgeEntry(
                        id=doc.get("id", ""),
                        titre=titre,
                        contenu=contenu[:500] + "..." if len(contenu) > 500 else contenu,
                        source=doc.get("source", "RAG"),
                        domaine=doc.get("domaine", "general"),
                        type="document",
                        tags=doc.get("tags", [])
                    )
                    results.append(SearchResult(
                        entry=entry,
                        score=min(score, 1.0),
                        match_type="rag"
                    ))

        except Exception as e:
            logger.warning(f"RAG search failed: {e}")

        return sorted(results, key=lambda r: r.score, reverse=True)[:limit]

    def _search_guardian_learnings(self, query: str) -> List[SearchResult]:
        """Recherche dans les apprentissages de Guardian."""
        results = []

        solutions_file = self.GUARDIAN_LEARNINGS_DIR / "solutions.json"
        if not solutions_file.exists():
            return results

        try:
            with open(solutions_file, 'r') as f:
                learnings = json.load(f)

            query_lower = query.lower()

            for key, learning in learnings.items():
                error_pattern = learning.get("error_pattern", "")
                solution = learning.get("solution", "")

                score = 0.0
                if query_lower in error_pattern.lower():
                    score += 0.4
                if query_lower in solution.lower():
                    score += 0.3

                # Bonus pour le taux de succès
                success_rate = learning.get("success_rate", 0)
                score *= (0.5 + 0.5 * success_rate)

                if score > 0.1:
                    entry = KnowledgeEntry(
                        id=f"guardian:{key}",
                        titre=f"Solution: {learning.get('error_type', 'unknown')}",
                        contenu=f"Pattern: {error_pattern}\nSolution: {solution}",
                        source="guardian_learning",
                        domaine="debug",
                        type="solution",
                        tags=learning.get("tags", []),
                        metadata={
                            "success_rate": success_rate,
                            "times_used": learning.get("times_used", 0)
                        }
                    )
                    results.append(SearchResult(
                        entry=entry,
                        score=score,
                        match_type="guardian"
                    ))

        except Exception as e:
            logger.warning(f"Guardian learnings search failed: {e}")

        return results

    def add_document(
        self,
        titre: str,
        contenu: str,
        domaine: str,
        source: str = "manual",
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Ajoute un document au RAG du tenant.

        Returns:
            ID du document créé
        """
        if not self.tenant_id:
            raise ValueError("tenant_id required for adding documents")

        import hashlib
        doc_id = hashlib.md5(f"{titre}:{contenu[:100]}".encode()).hexdigest()[:16]

        index_file = self.RAG_DIR / f"index_{self.tenant_id}.json"

        # Charger ou créer l'index
        if index_file.exists():
            with open(index_file, 'r') as f:
                data = json.load(f)
        else:
            data = {"documents": [], "metadata": {"created": datetime.now().isoformat()}}

        # Ajouter le document
        data["documents"].append({
            "id": doc_id,
            "titre": titre,
            "contenu": contenu,
            "source": source,
            "domaine": domaine,
            "tags": tags or [],
            "date_indexation": datetime.now().isoformat()
        })

        # Sauvegarder
        with open(index_file, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return doc_id

    def get_domains(self) -> List[str]:
        """Liste les domaines de connaissances disponibles."""
        domains = list(self._yaml_knowledge.keys())

        # Ajouter "debug" si des apprentissages Guardian existent
        solutions_file = self.GUARDIAN_LEARNINGS_DIR / "solutions.json"
        if solutions_file.exists():
            domains.append("debug")

        return sorted(set(domains))

    def get_stats(self) -> Dict[str, Any]:
        """Statistiques sur les connaissances disponibles."""
        yaml_count = sum(len(v) for v in self._yaml_knowledge.values())

        rag_count = 0
        if self.tenant_id:
            index_file = self.RAG_DIR / f"index_{self.tenant_id}.json"
            if index_file.exists():
                try:
                    with open(index_file, 'r') as f:
                        data = json.load(f)
                        rag_count = len(data.get("documents", []))
                except:
                    pass

        guardian_count = 0
        solutions_file = self.GUARDIAN_LEARNINGS_DIR / "solutions.json"
        if solutions_file.exists():
            try:
                with open(solutions_file, 'r') as f:
                    guardian_count = len(json.load(f))
            except:
                pass

        return {
            "yaml_entries": yaml_count,
            "yaml_domains": list(self._yaml_knowledge.keys()),
            "rag_documents": rag_count,
            "guardian_learnings": guardian_count,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None
        }


# Instance globale pour les connaissances système (pas tenant-specific)
_system_knowledge: Optional[SharedKnowledgeService] = None


def get_system_knowledge() -> SharedKnowledgeService:
    """Récupère le service de connaissances système (global)."""
    global _system_knowledge
    if _system_knowledge is None:
        _system_knowledge = SharedKnowledgeService(tenant_id=None)
    return _system_knowledge


def get_tenant_knowledge(tenant_id: UUID) -> SharedKnowledgeService:
    """Récupère le service de connaissances pour un tenant."""
    return SharedKnowledgeService(tenant_id=tenant_id)
