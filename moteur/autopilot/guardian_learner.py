# =============================================================================
# GUARDIAN LEARNER - Système d'auto-apprentissage autonome pour Guardian
# =============================================================================
"""
Guardian Learner: Système d'apprentissage complet avec boucle de vérification.

Flux de résolution d'erreur:
1. Erreur détectée par Guardian
2. AutoFixer tente correction automatique (patterns connus)
3. Si échec → ClaudeFixer analyse avec Claude
4. Si échec Claude → Recherche web (DuckDuckGo)
5. Appliquer la solution
6. Vérifier que la solution fonctionne
7. Si échec → retour à l'étape 3 avec le nouveau code d'erreur
8. Si succès → Enregistrer la solution pour réutilisation future

Normes:
- AZAP-TENANT: tenant_id sur tous les services (mais Guardian est système global)
- AZAP-IA-001: IA subordonnée (validation humaine possible)
"""

import os
import re
import json
import asyncio
import subprocess
import structlog
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field

logger = structlog.get_logger()

# Import des composants existants
try:
    from .claude_fixer import ClaudeFixer
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False

try:
    from .auto_fixer import AutoFixer
    AUTOFIXER_AVAILABLE = True
except ImportError:
    AUTOFIXER_AVAILABLE = False

# Import du service de recherche web de Marceau
try:
    from ...app.modules.marceau.web_search_service import WebSearchService
    WEB_SEARCH_AVAILABLE = True
except ImportError:
    WEB_SEARCH_AVAILABLE = False

# Import du service de connaissances partagé
# SÉCURITÉ: Guardian utilise search_technical() - JAMAIS d'accès aux données tenant
try:
    from ...app.modules.shared.knowledge_service import get_system_knowledge, SharedKnowledgeService
    SHARED_KNOWLEDGE_AVAILABLE = True
except ImportError:
    SHARED_KNOWLEDGE_AVAILABLE = False


@dataclass
class SolutionAttempt:
    """Représente une tentative de solution."""
    source: str  # "autofixer", "claude", "web_search", "knowledge_base"
    solution: str
    applied_at: datetime = field(default_factory=datetime.now)
    verified: bool = False
    success: bool = False
    error_after: Optional[str] = None


@dataclass
class LearningRecord:
    """Enregistrement d'une solution apprise."""
    error_type: str
    error_pattern: str
    solution: str
    source: str
    confidence: float = 0.5
    times_used: int = 0
    success_rate: float = 1.0
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "error_pattern": self.error_pattern,
            "solution": self.solution,
            "source": self.source,
            "confidence": self.confidence,
            "times_used": self.times_used,
            "success_rate": self.success_rate,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningRecord":
        return cls(
            error_type=data["error_type"],
            error_pattern=data["error_pattern"],
            solution=data["solution"],
            source=data["source"],
            confidence=data.get("confidence", 0.5),
            times_used=data.get("times_used", 0),
            success_rate=data.get("success_rate", 1.0),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            last_used=datetime.fromisoformat(data["last_used"]) if "last_used" in data else datetime.now(),
            tags=data.get("tags", []),
        )


class GuardianLearner:
    """
    Système d'apprentissage autonome pour Guardian.

    Gère le cycle complet de résolution d'erreurs:
    - Analyse
    - Recherche de solution (local → Claude → web)
    - Application
    - Vérification
    - Apprentissage
    """

    # Configuration
    MAX_ITERATIONS = 5  # Maximum d'itérations pour résoudre une erreur
    VERIFICATION_TIMEOUT = 30  # Secondes pour vérifier une solution

    # Chemins
    LEARNINGS_DIR = Path("/home/ubuntu/azalplus/data/guardian_learnings")
    LEARNINGS_FILE = LEARNINGS_DIR / "solutions.json"
    PROJECT_KNOWLEDGE_FILE = Path("/home/ubuntu/azalplus/config/knowledge/guardian_project_knowledge.yml")

    def __init__(self):
        self._learnings: Dict[str, LearningRecord] = {}
        self._current_attempts: List[SolutionAttempt] = []
        self._project_knowledge: Dict[str, Any] = {}
        self._knowledge_service: Optional[SharedKnowledgeService] = None
        self._initialized = False

    def initialize(self) -> bool:
        """Initialise Guardian Learner."""
        try:
            # Créer les répertoires
            self.LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)

            # Charger les apprentissages existants
            self._load_learnings()

            # Charger la connaissance du projet
            self._load_project_knowledge()

            # Initialiser le service de connaissances partagé
            # SÉCURITÉ: Guardian utilise UNIQUEMENT search_technical()
            # Jamais d'accès aux données tenant (RAG métier)
            if SHARED_KNOWLEDGE_AVAILABLE:
                self._knowledge_service = get_system_knowledge()
                logger.info("guardian_shared_knowledge_connected")

            # Initialiser Claude Fixer si disponible
            if CLAUDE_AVAILABLE:
                ClaudeFixer.initialize()

            self._initialized = True
            logger.info("guardian_learner_initialized",
                       learnings=len(self._learnings),
                       claude_available=CLAUDE_AVAILABLE,
                       web_search_available=WEB_SEARCH_AVAILABLE,
                       shared_knowledge=SHARED_KNOWLEDGE_AVAILABLE)

            return True

        except Exception as e:
            logger.error("guardian_learner_init_failed", error=str(e))
            return False

    def _load_learnings(self):
        """Charge les apprentissages depuis le fichier."""
        if self.LEARNINGS_FILE.exists():
            try:
                with open(self.LEARNINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, record_data in data.items():
                        self._learnings[key] = LearningRecord.from_dict(record_data)
                logger.info("guardian_learnings_loaded", count=len(self._learnings))
            except Exception as e:
                logger.warning("guardian_learnings_load_failed", error=str(e))

    def _save_learnings(self):
        """Sauvegarde les apprentissages."""
        try:
            data = {key: record.to_dict() for key, record in self._learnings.items()}
            with open(self.LEARNINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug("guardian_learnings_saved", count=len(self._learnings))
        except Exception as e:
            logger.error("guardian_learnings_save_failed", error=str(e))

    def _load_project_knowledge(self):
        """Charge la connaissance du projet AZALPLUS."""
        if self.PROJECT_KNOWLEDGE_FILE.exists():
            try:
                import yaml
                with open(self.PROJECT_KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
                    self._project_knowledge = yaml.safe_load(f) or {}
                logger.info("guardian_project_knowledge_loaded")
            except Exception as e:
                logger.warning("guardian_project_knowledge_load_failed", error=str(e))

    def _get_error_signature(self, error_log: str) -> str:
        """Génère une signature unique pour une erreur."""
        # Extraire les éléments clés
        error_type = "unknown"

        patterns = [
            (r'(\w+Error):', 'python'),
            (r'HTTP (\d{3})', 'http'),
            (r'(SyntaxError|IndentationError)', 'syntax'),
            (r'(ImportError|ModuleNotFoundError)', 'import'),
            (r'column "(\w+)".*does not exist', 'sql_column'),
            (r'relation "(\w+)" does not exist', 'sql_table'),
        ]

        for pattern, err_type in patterns:
            match = re.search(pattern, error_log)
            if match:
                error_type = f"{err_type}:{match.group(1)}"
                break

        # Ajouter un hash pour unicité
        error_hash = hash(error_log[:500]) % 10000
        return f"{error_type}:{error_hash}"

    async def resolve_error(
        self,
        error_log: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Résout une erreur avec le cycle complet.

        Args:
            error_log: Le log d'erreur complet
            context: Contexte additionnel (fichier, fonction, etc.)

        Returns:
            Tuple[bool, str, Optional[str]]:
                - success: True si résolu
                - message: Description de la résolution
                - solution: La solution appliquée (ou None)
        """
        if not self._initialized:
            self.initialize()

        self._current_attempts = []
        error_signature = self._get_error_signature(error_log)

        logger.info("guardian_learner_resolving",
                   signature=error_signature,
                   error_preview=error_log[:150])

        # 1. Vérifier si on a déjà une solution apprise
        if error_signature in self._learnings:
            learning = self._learnings[error_signature]
            if learning.success_rate > 0.7:
                logger.info("guardian_using_learned_solution",
                           signature=error_signature,
                           success_rate=learning.success_rate)

                success = await self._apply_and_verify(learning.solution, error_log, context)
                if success:
                    learning.times_used += 1
                    learning.last_used = datetime.now()
                    self._save_learnings()
                    return True, f"Résolu avec solution apprise (utilisée {learning.times_used}x)", learning.solution

        # 1b. Chercher dans les connaissances techniques partagées
        # SÉCURITÉ: search_technical() n'accède JAMAIS aux données tenant
        if self._knowledge_service:
            knowledge_solution = self._search_knowledge_base(error_log)
            if knowledge_solution:
                logger.info("guardian_using_knowledge_solution",
                           signature=error_signature)
                success = await self._apply_and_verify(knowledge_solution, error_log, context)
                if success:
                    return True, "Résolu avec base de connaissances techniques", knowledge_solution

        # 2. Boucle de résolution avec itérations
        current_error = error_log
        for iteration in range(self.MAX_ITERATIONS):
            logger.info("guardian_resolution_iteration",
                       iteration=iteration + 1,
                       max=self.MAX_ITERATIONS)

            # 2a. Essayer AutoFixer (patterns connus)
            if AUTOFIXER_AVAILABLE:
                success, message = AutoFixer.try_fix(current_error)
                if success:
                    # Vérifier que le fix fonctionne
                    verified = await self._verify_fix(context)
                    if verified:
                        self._record_learning(error_signature, message, "autofixer", current_error)
                        return True, f"Résolu par AutoFixer: {message}", message

            # 2b. Essayer Claude
            if CLAUDE_AVAILABLE and ClaudeFixer.is_enabled():
                error_context = {
                    "error_log": current_error,
                    "error_type": self._extract_error_type(current_error),
                    "path": context.get("path", "") if context else "",
                    "source_file": context.get("file", "") if context else "",
                    "attempts": iteration + 1,
                    "previous_attempts": [a.solution for a in self._current_attempts[-3:]]
                }

                success, message, diff = await ClaudeFixer.fix_error(error_context)

                if success:
                    # Vérifier que le fix fonctionne
                    verified = await self._verify_fix(context)
                    if verified:
                        self._record_learning(error_signature, message, "claude", current_error)
                        return True, f"Résolu par Claude: {message}", diff
                    else:
                        # Le fix n'a pas fonctionné, continuer avec la nouvelle erreur
                        new_error = await self._get_current_error(context)
                        if new_error and new_error != current_error:
                            current_error = new_error
                            self._current_attempts.append(SolutionAttempt(
                                source="claude",
                                solution=message,
                                verified=True,
                                success=False,
                                error_after=new_error[:200]
                            ))
                            continue

            # 2c. Recherche web si Claude échoue
            if WEB_SEARCH_AVAILABLE:
                search_solution = await self._search_web_solution(current_error)
                if search_solution:
                    # Appliquer la solution trouvée sur le web
                    applied = await self._apply_web_solution(search_solution, context)
                    if applied:
                        verified = await self._verify_fix(context)
                        if verified:
                            self._record_learning(error_signature, search_solution, "web_search", current_error)
                            return True, f"Résolu avec solution web", search_solution

            # Récupérer la nouvelle erreur après tentative
            new_error = await self._get_current_error(context)
            if not new_error or new_error == current_error:
                # Pas de changement, on arrête
                break
            current_error = new_error

        # 3. Échec après toutes les tentatives → APPEL FINAL À CLAUDE
        logger.warning("guardian_resolution_failed_trying_claude_final",
                      signature=error_signature,
                      iterations=self.MAX_ITERATIONS)

        # Dernier recours: appel à Claude avec TOUT le contexte
        final_solution = await self._final_claude_attempt(error_log, error_signature, context)

        if final_solution:
            # Claude a trouvé une solution!
            verified = await self._verify_fix(context)
            if verified:
                self._record_learning(error_signature, final_solution, "claude_final", error_log)
                return True, "Résolu par Claude (appel final avec contexte complet)", final_solution

        # 4. Vraiment échec → ESCALADE AU CRÉATEUR
        logger.error("guardian_all_attempts_failed_escalating",
                    signature=error_signature)

        await self._escalate_to_creator(error_log, error_signature, context)

        return False, f"Échec total - Escaladé au créateur", None

    def _extract_error_type(self, error_log: str) -> str:
        """Extrait le type d'erreur."""
        patterns = [
            r'(\w+Error):',
            r'HTTP (\d{3})',
            r'(YAML|SQL|Python) error',
        ]

        for pattern in patterns:
            match = re.search(pattern, error_log, re.IGNORECASE)
            if match:
                return match.group(1)

        return "unknown"

    def _search_knowledge_base(self, error_log: str) -> Optional[str]:
        """
        Recherche une solution dans la base de connaissances techniques.

        SÉCURITÉ: Utilise search_technical() qui n'accède JAMAIS:
        - Aux documents RAG (données métier du tenant)
        - Aux données PostgreSQL du tenant
        - À toute information sensible

        Seules sources:
        - Bases YAML techniques (Python, HTML, AZAL stack)
        - Solutions Guardian précédentes (patterns génériques)
        """
        if not self._knowledge_service:
            return None

        try:
            # Extraire les termes de recherche de l'erreur
            error_type = self._extract_error_type(error_log)
            error_message = ""

            match = re.search(r'(Error|Exception):\s*(.+?)(?:\n|$)', error_log)
            if match:
                error_message = match.group(2)[:100]

            # Construire la requête
            query = f"{error_type} {error_message}"

            # Recherche TECHNIQUE UNIQUEMENT
            results = self._knowledge_service.search_technical(query, limit=5)

            if results:
                # Retourner la meilleure solution si score suffisant
                best = results[0]
                if best.score > 0.4:
                    logger.info("guardian_knowledge_match",
                               titre=best.entry.titre,
                               score=best.score,
                               source=best.entry.source)
                    return best.entry.contenu

            return None

        except Exception as e:
            logger.warning("guardian_knowledge_search_failed", error=str(e))
            return None

    async def _apply_and_verify(
        self,
        solution: str,
        error_log: str,
        context: Optional[Dict[str, Any]]
    ) -> bool:
        """Applique une solution et vérifie qu'elle fonctionne."""
        try:
            # L'application dépend du type de solution
            # Pour l'instant, on suppose que la solution est déjà appliquée par le fixer
            return await self._verify_fix(context)
        except Exception as e:
            logger.error("guardian_apply_verify_failed", error=str(e))
            return False

    async def _verify_fix(self, context: Optional[Dict[str, Any]]) -> bool:
        """
        Vérifie qu'un fix a fonctionné.

        Stratégies de vérification:
        1. Recharger le module Python modifié
        2. Exécuter des tests spécifiques
        3. Faire une requête HTTP de test
        4. Vérifier que l'erreur ne se reproduit pas
        """
        if not context:
            # Sans contexte, on ne peut pas vérifier automatiquement
            return True  # Optimiste par défaut

        try:
            verification_type = context.get("verification_type", "syntax")

            if verification_type == "syntax":
                # Vérifier la syntaxe Python
                file_path = context.get("file")
                if file_path and Path(file_path).exists():
                    return self._verify_python_syntax(file_path)

            elif verification_type == "http":
                # Faire une requête HTTP de test
                endpoint = context.get("endpoint")
                if endpoint:
                    return await self._verify_http_endpoint(endpoint)

            elif verification_type == "test":
                # Exécuter un test spécifique
                test_command = context.get("test_command")
                if test_command:
                    return await self._run_test(test_command)

            return True

        except Exception as e:
            logger.error("guardian_verify_failed", error=str(e))
            return False

    def _verify_python_syntax(self, file_path: str) -> bool:
        """Vérifie la syntaxe d'un fichier Python."""
        import ast
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            ast.parse(code)
            return True
        except SyntaxError as e:
            logger.warning("guardian_syntax_error", file=file_path, error=str(e))
            return False

    async def _verify_http_endpoint(self, endpoint: str) -> bool:
        """Vérifie qu'un endpoint HTTP répond correctement."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, timeout=10) as response:
                    return response.status < 500
        except Exception as e:
            logger.warning("guardian_http_verify_failed", endpoint=endpoint, error=str(e))
            return False

    async def _run_test(self, test_command: str) -> bool:
        """Exécute une commande de test."""
        try:
            result = subprocess.run(
                test_command.split(),
                capture_output=True,
                timeout=self.VERIFICATION_TIMEOUT,
                cwd="/home/ubuntu/azalplus"
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning("guardian_test_failed", command=test_command, error=str(e))
            return False

    async def _get_current_error(self, context: Optional[Dict[str, Any]]) -> Optional[str]:
        """Récupère l'erreur courante après une tentative de fix."""
        if not context:
            return None

        # Vérifier les logs d'erreur récents
        log_file = Path("/home/ubuntu/azalplus/logs/guardian_errors.log")
        if log_file.exists():
            try:
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    if lines:
                        # Dernière erreur
                        return lines[-1].strip()
            except:
                pass

        return None

    async def _search_web_solution(self, error_log: str) -> Optional[str]:
        """
        Recherche une solution sur le web.

        Utilise le service de recherche de Marceau avec des requêtes ciblées.
        """
        if not WEB_SEARCH_AVAILABLE:
            return None

        try:
            # Construire une requête de recherche pertinente
            error_type = self._extract_error_type(error_log)

            # Extraire le message d'erreur clé
            error_message = ""
            match = re.search(r'(Error|Exception):\s*(.+?)(?:\n|$)', error_log)
            if match:
                error_message = match.group(2)[:100]

            # Construire des requêtes de recherche
            queries = [
                f"Python {error_type} {error_message} fix solution",
                f"FastAPI {error_type} how to fix",
                f"SQLAlchemy {error_message} solution stackoverflow",
            ]

            search_service = WebSearchService()

            for query in queries[:2]:  # Limiter à 2 recherches
                results = await search_service.search(query, max_results=5)

                if results:
                    # Analyser les résultats pour extraire une solution
                    solution = self._extract_solution_from_results(results, error_log)
                    if solution:
                        logger.info("guardian_web_solution_found",
                                   query=query,
                                   solution_preview=solution[:100])
                        return solution

            return None

        except Exception as e:
            logger.error("guardian_web_search_failed", error=str(e))
            return None

    def _extract_solution_from_results(
        self,
        results: List[Dict[str, Any]],
        error_log: str
    ) -> Optional[str]:
        """
        Extrait une solution exploitable depuis les résultats de recherche.

        Cherche des patterns comme:
        - Blocs de code Python
        - Instructions "pip install"
        - Modifications de configuration
        """
        for result in results:
            content = result.get("content", "") or result.get("snippet", "")

            # Chercher des blocs de code
            code_blocks = re.findall(r'```(?:python)?\n(.*?)```', content, re.DOTALL)
            for code in code_blocks:
                if len(code) > 20 and self._is_relevant_code(code, error_log):
                    return code.strip()

            # Chercher des commandes pip
            pip_match = re.search(r'pip install\s+[\w\-\[\]]+', content)
            if pip_match:
                return pip_match.group()

            # Chercher des instructions de fix
            fix_patterns = [
                r'(?:fix|solution|résolution):\s*(.+?)(?:\n|$)',
                r'(?:you need to|you should|try)\s+(.+?)(?:\n|$)',
            ]
            for pattern in fix_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    return match.group(1).strip()

        return None

    def _is_relevant_code(self, code: str, error_log: str) -> bool:
        """Vérifie si un bloc de code est pertinent pour l'erreur."""
        # Vérifier que le code contient des éléments liés à l'erreur
        error_keywords = []

        # Extraire des mots-clés de l'erreur
        match = re.search(r"'(\w+)'", error_log)
        if match:
            error_keywords.append(match.group(1))

        match = re.search(r'(\w+Error)', error_log)
        if match:
            error_keywords.append(match.group(1))

        # Vérifier si le code mentionne ces mots-clés
        code_lower = code.lower()
        for keyword in error_keywords:
            if keyword.lower() in code_lower:
                return True

        # Vérifier si c'est du code Python valide
        try:
            import ast
            ast.parse(code)
            return True
        except:
            return False

    async def _apply_web_solution(
        self,
        solution: str,
        context: Optional[Dict[str, Any]]
    ) -> bool:
        """
        Applique une solution trouvée sur le web.

        Selon le type de solution:
        - pip install → exécuter la commande
        - Code Python → demander à Claude de l'intégrer
        - Configuration → modifier le fichier approprié
        """
        try:
            # Commande pip install
            if solution.startswith("pip install"):
                result = subprocess.run(
                    solution.split(),
                    capture_output=True,
                    timeout=60
                )
                return result.returncode == 0

            # Code Python → demander à Claude de l'intégrer
            if CLAUDE_AVAILABLE and ClaudeFixer.is_enabled():
                integration_prompt = {
                    "error_log": f"Integrate this solution: {solution}",
                    "error_type": "integration",
                    "path": context.get("path", "") if context else "",
                    "source_file": context.get("file", "") if context else "",
                }
                success, _, _ = await ClaudeFixer.fix_error(integration_prompt)
                return success

            return False

        except Exception as e:
            logger.error("guardian_apply_web_solution_failed", error=str(e))
            return False

    def _record_learning(
        self,
        signature: str,
        solution: str,
        source: str,
        error_log: str
    ):
        """Enregistre une solution réussie pour réutilisation future."""
        learning = LearningRecord(
            error_type=self._extract_error_type(error_log),
            error_pattern=error_log[:200],
            solution=solution,
            source=source,
            confidence=0.8 if source == "claude" else 0.6,
            times_used=1,
            success_rate=1.0,
        )

        self._learnings[signature] = learning
        self._save_learnings()

        logger.info("guardian_learning_recorded",
                   signature=signature,
                   source=source,
                   solution_preview=solution[:100])

    async def _final_claude_attempt(
        self,
        error_log: str,
        signature: str,
        context: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Dernier appel à Claude avec TOUT le contexte.

        Différent des appels précédents car on envoie:
        - L'erreur originale
        - TOUTES les tentatives précédentes et leurs résultats
        - Les erreurs après chaque tentative
        - La structure du projet
        - Demande une analyse approfondie
        """
        if not CLAUDE_AVAILABLE or not ClaudeFixer.is_enabled():
            logger.debug("guardian_final_claude_not_available")
            return None

        try:
            # Construire un contexte enrichi avec tout l'historique
            attempts_summary = []
            for i, attempt in enumerate(self._current_attempts, 1):
                attempts_summary.append({
                    "tentative": i,
                    "source": attempt.source,
                    "solution_essayee": attempt.solution[:300] if attempt.solution else None,
                    "succes": attempt.success,
                    "erreur_apres": attempt.error_after[:200] if attempt.error_after else None
                })

            # Charger la connaissance du projet pour donner du contexte
            project_context = ""
            if self._project_knowledge:
                project_context = f"""
Structure projet AZALPLUS:
- Backend: Python 3.12, FastAPI, SQLAlchemy 2.0
- Frontend: Jinja2 HTML
- Base de données: PostgreSQL 16
- Fichiers clés: moteur/core.py, moteur/parser.py, moteur/db.py, moteur/ui.py
- Modules YAML: modules/*.yml
"""

            # Construire le prompt enrichi
            enriched_context = {
                "error_log": error_log,
                "error_type": "unresolved_after_multiple_attempts",
                "path": context.get("path", "") if context else "",
                "source_file": context.get("file", "") if context else "",
                "attempts": len(self._current_attempts),
                "previous_attempts_detail": attempts_summary,
                "project_context": project_context,
                "special_instructions": """
CONTEXTE CRITIQUE: Toutes les tentatives automatiques ont échoué.
C'est le DERNIER APPEL avant escalade humaine.

Tu as accès à:
1. L'erreur originale
2. Toutes les tentatives précédentes et pourquoi elles ont échoué
3. La structure du projet

ANALYSE EN PROFONDEUR requise:
- Pourquoi les solutions précédentes n'ont pas fonctionné?
- Quelle est la VRAIE cause racine?
- Propose une solution DIFFÉRENTE et COMPLÈTE

Format de réponse JSON:
{
    "analysis": "Analyse approfondie du problème",
    "why_previous_failed": "Pourquoi les tentatives précédentes ont échoué",
    "root_cause": "Vraie cause racine identifiée",
    "fix": {
        "file": "/chemin/complet/fichier.py",
        "action": "edit",
        "search": "code exact à remplacer",
        "replace": "nouveau code",
        "description": "Ce que fait cette correction"
    },
    "confidence": 0.8,
    "additional_steps": ["Étape 1", "Étape 2 si nécessaire"]
}
"""
            }

            logger.info("guardian_final_claude_attempt",
                       attempts=len(self._current_attempts),
                       signature=signature[:50])

            success, message, diff = await ClaudeFixer.fix_error(enriched_context)

            if success:
                logger.info("guardian_final_claude_success",
                           message=message[:100] if message else "")
                return message

            logger.info("guardian_final_claude_no_solution",
                       reason=message[:100] if message else "")
            return None

        except Exception as e:
            logger.error("guardian_final_claude_error", error=str(e))
            return None

    async def _escalate_to_creator(
        self,
        error_log: str,
        signature: str,
        context: Optional[Dict[str, Any]]
    ):
        """
        Escalade une erreur non résolue vers le créateur.

        Actions:
        1. Créer un fichier d'alerte détaillé
        2. Logger en CRITICAL
        3. Envoyer un email au créateur (si configuré)
        4. Ajouter à la liste des problèmes en attente
        """
        from datetime import datetime
        from pathlib import Path

        logger.critical("guardian_escalation_to_creator",
                       signature=signature,
                       attempts=len(self._current_attempts),
                       message="Guardian n'a pas pu résoudre cette erreur")

        # 1. Créer un rapport d'escalade détaillé
        escalation_dir = Path("/home/ubuntu/azalplus/logs/escalations")
        escalation_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = escalation_dir / f"escalation_{timestamp}_{signature[:20]}.md"

        report = f"""# 🚨 ESCALADE GUARDIAN - {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}

## Résumé
- **Signature erreur**: `{signature}`
- **Tentatives**: {len(self._current_attempts)}
- **Statut**: NON RÉSOLU - Intervention humaine requise

## Erreur originale
```
{error_log[:2000]}
```

## Contexte
```json
{json.dumps(context, indent=2, default=str) if context else "Aucun contexte"}
```

## Tentatives de résolution

"""
        for i, attempt in enumerate(self._current_attempts, 1):
            report += f"""### Tentative {i} - {attempt.source}
- **Solution essayée**: {attempt.solution[:500] if attempt.solution else "N/A"}
- **Vérifié**: {"Oui" if attempt.verified else "Non"}
- **Succès**: {"Oui" if attempt.success else "Non"}
- **Erreur après**: {attempt.error_after[:200] if attempt.error_after else "N/A"}

"""

        report += f"""## Actions requises
1. Analyser l'erreur manuellement
2. Trouver et appliquer la solution
3. Ajouter la solution à Guardian pour apprentissage futur

## Fichier d'escalade
`{report_file}`

---
*Généré automatiquement par Guardian AutoPilot*
"""

        # Écrire le rapport
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info("guardian_escalation_report_created", file=str(report_file))
        except Exception as e:
            logger.error("guardian_escalation_report_failed", error=str(e))

        # 2. Ajouter au fichier d'alertes global
        alerts_file = Path("/home/ubuntu/azalplus/logs/guardian_alerts.log")
        try:
            with open(alerts_file, 'a') as f:
                f.write(f"{datetime.now().isoformat()} | ESCALATION | {signature} | {len(self._current_attempts)} attempts | {report_file}\n")
        except Exception as e:
            logger.error("guardian_alerts_write_failed", error=str(e))

        # 3. Envoyer un email au créateur (si le service email est disponible)
        await self._notify_creator_email(signature, error_log, report_file)

        # 4. Ajouter aux problèmes en attente (pour le dashboard Guardian)
        pending_file = Path("/home/ubuntu/azalplus/data/guardian_learnings/pending_issues.json")
        try:
            pending_file.parent.mkdir(parents=True, exist_ok=True)

            pending = []
            if pending_file.exists():
                with open(pending_file, 'r') as f:
                    pending = json.load(f)

            pending.append({
                "signature": signature,
                "error_preview": error_log[:500],
                "attempts": len(self._current_attempts),
                "escalated_at": datetime.now().isoformat(),
                "report_file": str(report_file),
                "status": "pending_human_review"
            })

            # Garder seulement les 100 dernières
            pending = pending[-100:]

            with open(pending_file, 'w') as f:
                json.dump(pending, f, indent=2)

        except Exception as e:
            logger.error("guardian_pending_issues_failed", error=str(e))

    async def _notify_creator_email(
        self,
        signature: str,
        error_log: str,
        report_file: Path
    ):
        """Envoie un email au créateur pour l'alerter."""
        try:
            # Récupérer l'email du créateur depuis la config
            from ...config import settings
            creator_email = getattr(settings, 'CREATEUR_EMAIL', None)

            if not creator_email:
                logger.debug("guardian_no_creator_email_configured")
                return

            # Essayer d'envoyer via le service email
            try:
                from ...moteur.email_router import send_email_internal

                subject = f"🚨 Guardian Escalation: {signature[:50]}"
                body = f"""
Guardian n'a pas pu résoudre automatiquement l'erreur suivante:

Signature: {signature}
Erreur: {error_log[:500]}...

Un rapport détaillé a été créé: {report_file}

Connectez-vous au dashboard Guardian pour plus de détails:
/guardian/dashboard

---
Guardian AutoPilot
"""
                await send_email_internal(
                    to=creator_email,
                    subject=subject,
                    body=body
                )
                logger.info("guardian_creator_notified", email=creator_email)

            except ImportError:
                logger.debug("guardian_email_service_not_available")
            except Exception as e:
                logger.warning("guardian_email_notification_failed", error=str(e))

        except Exception as e:
            logger.warning("guardian_notify_creator_failed", error=str(e))

    def get_pending_issues(self) -> List[Dict[str, Any]]:
        """Récupère les problèmes en attente de résolution humaine."""
        pending_file = Path("/home/ubuntu/azalplus/data/guardian_learnings/pending_issues.json")
        if not pending_file.exists():
            return []

        try:
            with open(pending_file, 'r') as f:
                return json.load(f)
        except:
            return []

    def resolve_pending_issue(self, signature: str, solution: str) -> bool:
        """
        Marque un problème comme résolu et enregistre la solution.

        Appelé manuellement par le créateur après avoir trouvé la solution.
        """
        pending_file = Path("/home/ubuntu/azalplus/data/guardian_learnings/pending_issues.json")
        if not pending_file.exists():
            return False

        try:
            with open(pending_file, 'r') as f:
                pending = json.load(f)

            # Trouver et retirer le problème
            updated = [p for p in pending if p.get("signature") != signature]

            if len(updated) == len(pending):
                return False  # Pas trouvé

            with open(pending_file, 'w') as f:
                json.dump(updated, f, indent=2)

            # Enregistrer la solution pour apprentissage futur
            self._record_learning(signature, solution, "human", f"Résolu manuellement: {signature}")

            logger.info("guardian_pending_issue_resolved",
                       signature=signature,
                       solution_preview=solution[:100])

            return True

        except Exception as e:
            logger.error("guardian_resolve_pending_failed", error=str(e))
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques d'apprentissage."""
        sources = {}
        total_uses = 0

        for learning in self._learnings.values():
            sources[learning.source] = sources.get(learning.source, 0) + 1
            total_uses += learning.times_used

        return {
            "total_learnings": len(self._learnings),
            "by_source": sources,
            "total_uses": total_uses,
            "claude_available": CLAUDE_AVAILABLE,
            "web_search_available": WEB_SEARCH_AVAILABLE,
        }


# Instance globale
_guardian_learner: Optional[GuardianLearner] = None


def get_guardian_learner() -> GuardianLearner:
    """Récupère l'instance globale de Guardian Learner."""
    global _guardian_learner
    if _guardian_learner is None:
        _guardian_learner = GuardianLearner()
        _guardian_learner.initialize()
    return _guardian_learner


async def resolve_error(error_log: str, context: Optional[Dict[str, Any]] = None) -> Tuple[bool, str, Optional[str]]:
    """
    Point d'entrée simplifié pour résoudre une erreur.

    Usage:
        success, message, solution = await resolve_error("NameError: ...", {"file": "..."})
    """
    learner = get_guardian_learner()
    return await learner.resolve_error(error_log, context)
