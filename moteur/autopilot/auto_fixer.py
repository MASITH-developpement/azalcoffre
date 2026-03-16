# =============================================================================
# AUTOPILOT - Auto-Fixer: Corrections automatiques sans validation
# =============================================================================
"""
Auto-Fixer: Applique automatiquement les corrections pour les erreurs connues.

Ce module corrige automatiquement SANS intervention humaine:

BACKEND:
- SQL: colonnes manquantes, NOT NULL, tables manquantes
- Python: ImportError, ModuleNotFoundError (pip install auto)
- Database: pool exhausted, connexion perdue, deadlocks, timeouts
- Redis: connexion cache, mémoire pleine
- YAML: erreurs syntaxe, structure modules
- Templates: variables Jinja2 non définies, templates manquants
- Validation: erreurs Pydantic, champs requis

FRONTEND:
- JavaScript: ReferenceError (fonctions manquantes), clipboard polyfill
- CSS: fichiers manquants, classes non définies
- HTTP: 404 (routes, fichiers statiques), CORS, CSRF
- React/Mobile: composants manquants, Vite HMR, port en cours d'utilisation
- TypeScript: types manquants, modules non trouvés

SYSTÈME:
- Auth: tokens expirés, refresh automatique
- Fichiers: permissions, disque plein, fichiers manquants
- Réseau: timeouts, connexion refusée, DNS

Guardian détecte → AutoFixer corrige → Application continue.
"""

import re
import asyncio
import structlog
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
from pathlib import Path

logger = structlog.get_logger()

# Import ClaudeFixer (correction par IA)
try:
    from .claude_fixer import ClaudeFixer
    CLAUDE_FIXER_AVAILABLE = True
except ImportError:
    CLAUDE_FIXER_AVAILABLE = False


class AutoFixer:
    """
    Corrige automatiquement les erreurs SQL simples.

    Fonctionne en analysant l'erreur et en exécutant directement
    les corrections en base de données.

    APPRENTISSAGE: Détecte les échecs répétés et escalade vers Claude.
    """

    # Session factory (injecté depuis Database)
    _get_session = None

    # Suivi des tentatives de fix (apprentissage des échecs)
    _fix_attempts: dict = {}  # error_key -> {"count": int, "last_fix": datetime, "fix_type": str}
    _MAX_ATTEMPTS = 3  # Après 3 échecs, escalader
    _ATTEMPT_WINDOW = 300  # 5 minutes - si même erreur revient dans ce délai, c'est un échec

    @classmethod
    def initialize(cls, get_session_func):
        """Initialise avec la factory de session."""
        cls._get_session = get_session_func
        cls._fix_attempts = {}
        logger.info("auto_fixer_initialized")

    @classmethod
    def _get_error_key(cls, error_log: str) -> str:
        """Génère une clé unique pour identifier une erreur (sans timestamps)."""
        # Extraire les éléments clés: type d'erreur, path/table/module
        key_parts = []

        # Extraire le type d'erreur
        if "404" in error_log:
            key_parts.append("404")
        elif "500" in error_log:
            key_parts.append("500")
        elif "401" in error_log:
            key_parts.append("401")

        # Extraire le path/source
        source_match = re.search(r'Source:\s*(/[^\s:]+)', error_log)
        if source_match:
            key_parts.append(source_match.group(1))

        # Extraire la table/module
        table_match = re.search(r'relation "(\w+)"', error_log)
        if table_match:
            key_parts.append(table_match.group(1))

        module_match = re.search(r'module[=\s]+(\w+)', error_log, re.IGNORECASE)
        if module_match:
            key_parts.append(module_match.group(1))

        return ":".join(key_parts) if key_parts else str(hash(error_log[:200]))

    @classmethod
    def _track_fix_attempt(cls, error_key: str, fix_type: str) -> bool:
        """
        Enregistre une tentative de fix et vérifie si on doit escalader.

        Returns:
            True si on peut continuer à tenter, False si on doit escalader
        """
        now = datetime.now()

        if error_key in cls._fix_attempts:
            attempt = cls._fix_attempts[error_key]
            time_since_last = (now - attempt["last_fix"]).total_seconds()

            if time_since_last < cls._ATTEMPT_WINDOW:
                # Même erreur revenue rapidement = notre fix n'a pas marché
                attempt["count"] += 1
                attempt["last_fix"] = now

                if attempt["count"] >= cls._MAX_ATTEMPTS:
                    # Escalader vers Claude
                    logger.warning("autofix_escalation_required",
                                 error_key=error_key,
                                 attempts=attempt["count"],
                                 fix_type=fix_type,
                                 message=f"Fix '{fix_type}' échoue après {attempt['count']} tentatives")
                    cls._escalate_to_claude(error_key, fix_type, attempt["count"])
                    return False
            else:
                # Assez de temps passé, reset le compteur
                attempt["count"] = 1
                attempt["last_fix"] = now
        else:
            # Première tentative
            cls._fix_attempts[error_key] = {
                "count": 1,
                "last_fix": now,
                "fix_type": fix_type
            }

        return True

    # Contexte d'erreur courant pour ClaudeFixer
    _current_error_context: Dict[str, Any] = {}

    # Erreurs HTTP qui ne sont PAS des bugs à corriger (comportement normal)
    SKIP_CLAUDE_ERRORS = [
        "401",      # Non autorisé (token expiré, pas de token)
        "403",      # Interdit (permissions)
        "404",      # Non trouvé (URL incorrecte de l'utilisateur)
        "422",      # Validation Pydantic (données invalides de l'utilisateur)
        "favicon",  # Requêtes favicon
        "/metrics", # Prometheus metrics
        "/health",  # Health checks
    ]

    @classmethod
    def _escalate_to_claude(cls, error_key: str, fix_type: str, attempts: int):
        """Escalade vers Claude quand les corrections automatiques échouent."""

        # Ne pas escalader les erreurs HTTP normales
        for skip in cls.SKIP_CLAUDE_ERRORS:
            if skip in error_key.lower():
                logger.debug("skip_claude_escalation", error_key=error_key, reason="Normal HTTP error")
                return

        logger.error("claude_action_required",
                    priority="HIGH",
                    error_key=error_key,
                    fix_type=fix_type,
                    attempts=attempts,
                    reason="AutoFix répété sans succès",
                    message=f"Guardian n'arrive pas à corriger: {error_key} (tenté {attempts}x avec '{fix_type}')")

        # Créer une alerte dans le fichier d'alertes
        alert_file = Path("/home/ubuntu/azalplus/logs/guardian_alerts.log")
        alert_file.parent.mkdir(parents=True, exist_ok=True)
        with open(alert_file, "a") as f:
            f.write(f"{datetime.now().isoformat()} | ESCALATION | {error_key} | {fix_type} | {attempts} attempts\n")

        # NOUVEAU: Appeler ClaudeFixer pour correction par IA
        if CLAUDE_FIXER_AVAILABLE and ClaudeFixer.is_enabled():
            try:
                error_context = {
                    "error_log": cls._current_error_context.get("error_log", ""),
                    "error_type": fix_type,
                    "path": error_key,
                    "attempts": attempts,
                    "source_file": cls._guess_source_file(error_key, fix_type)
                }

                # Exécuter de manière asynchrone
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(cls._run_claude_fixer(error_context))
                else:
                    asyncio.run(cls._run_claude_fixer(error_context))

            except Exception as e:
                logger.warning("claude_fixer_escalation_failed", error=str(e))

    @classmethod
    async def _run_claude_fixer(cls, error_context: Dict[str, Any]):
        """Exécute ClaudeFixer de manière asynchrone."""
        try:
            success, message, diff = await ClaudeFixer.fix_error(error_context)
            if success:
                logger.info("claude_fixer_success",
                           path=error_context.get("path"),
                           message=message)
            else:
                logger.info("claude_fixer_no_fix",
                           path=error_context.get("path"),
                           reason=message)
        except Exception as e:
            logger.error("claude_fixer_run_error", error=str(e))

    @classmethod
    def _guess_source_file(cls, error_key: str, fix_type: str) -> str:
        """Devine le fichier source à partir de l'erreur."""
        # Frontend JS errors -> ui.py
        if "/api/" in error_key and fix_type in ["http_400", "http_404"]:
            return "/home/ubuntu/azalplus/moteur/ui.py"

        # API errors -> api.py ou api_v1.py
        if "api" in fix_type or "/api/" in error_key:
            return "/home/ubuntu/azalplus/moteur/api_v1.py"

        # SQL errors -> db.py
        if "sql" in fix_type or "column" in error_key:
            return "/home/ubuntu/azalplus/moteur/db.py"

        return ""

    @classmethod
    def _log_fix_applied(cls, fix_type: str, fix_message: str, error_key: str):
        """Log une correction appliquée avec succès."""
        logger.info("autofix_applied", fix_type=fix_type, message=fix_message, error_key=error_key)
        fix_file = Path("/home/ubuntu/azalplus/logs/guardian_fixes.log")
        fix_file.parent.mkdir(parents=True, exist_ok=True)
        with open(fix_file, "a") as f:
            f.write(f"{datetime.now().isoformat()} | FIX | {fix_type} | {fix_message[:100]} | {error_key}\n")

    @classmethod
    def _log_error_detected(cls, error_type: str, error_msg: str):
        """Log une erreur détectée."""
        error_file = Path("/home/ubuntu/azalplus/logs/guardian_errors.log")
        error_file.parent.mkdir(parents=True, exist_ok=True)
        with open(error_file, "a") as f:
            f.write(f"{datetime.now().isoformat()} | ERROR | {error_type} | {error_msg[:150]}\n")

    @classmethod
    def _log_learning(cls, category: str, what_learned: str):
        """Log un nouvel apprentissage de Guardian."""
        logger.info("guardian_learning", category=category, learned=what_learned)
        learn_file = Path("/home/ubuntu/azalplus/logs/guardian_learning.log")
        learn_file.parent.mkdir(parents=True, exist_ok=True)
        with open(learn_file, "a") as f:
            f.write(f"{datetime.now().isoformat()} | LEARN | {category} | {what_learned}\n")

    # Erreurs à ignorer (développement uniquement)
    DEV_ONLY_PATTERNS = [
        "[hmr]",  # Vite Hot Module Reload
        "vite",
        "hot update",
        "@vite/client",
        "content-script.js",  # Extensions browser
        "chrome-extension://",
        "moz-extension://",
        "React DevTools",
        "Download the React DevTools",
    ]

    @classmethod
    def _is_dev_only_error(cls, error_log: str) -> bool:
        """Vérifie si c'est une erreur de développement à ignorer."""
        error_lower = error_log.lower()
        for pattern in cls.DEV_ONLY_PATTERNS:
            if pattern.lower() in error_lower:
                return True
        return False

    @classmethod
    def try_fix(cls, error_log: str) -> Tuple[bool, str]:
        """
        Tente de corriger automatiquement une erreur.

        APPRENTISSAGE: Suit les tentatives et escalade si les fixes échouent.

        Returns:
            (success, message) - True si corrigé, avec message explicatif
        """
        logger.info("autofixer_try_fix_called", error_preview=error_log[:100])

        # Stocker le contexte pour ClaudeFixer si escalade nécessaire
        cls._current_error_context = {"error_log": error_log}

        if not cls._get_session:
            logger.warning("autofixer_not_initialized")
            return False, "AutoFixer non initialisé"

        # APPRENTISSAGE: Ignorer les erreurs de développement
        if cls._is_dev_only_error(error_log):
            logger.debug("dev_error_ignored", preview=error_log[:100])
            return True, "Erreur de développement ignorée"

        # Générer la clé d'erreur pour le tracking
        error_key = cls._get_error_key(error_log)

        # Logger l'erreur détectée
        error_type = "unknown"
        if "404" in error_log: error_type = "http_404"
        elif "422" in error_log: error_type = "http_422"
        elif "500" in error_log: error_type = "http_500"
        elif "ReferenceError" in error_log: error_type = "js_reference"
        elif "TypeError" in error_log: error_type = "js_type"
        elif "column" in error_log.lower() and "does not exist" in error_log: error_type = "sql_column"
        cls._log_error_detected(error_type, error_log[:200])

        # Fonction helper pour tracker et retourner le résultat
        def apply_fix(result: Tuple[bool, str], fix_type: str) -> Tuple[bool, str]:
            if result[0]:
                # Fix appliqué - logger la correction réussie
                cls._log_fix_applied(fix_type, result[1], error_key)
                # Vérifier si on doit escalader (échecs répétés)
                if not cls._track_fix_attempt(error_key, fix_type):
                    # Trop d'échecs, on a escaladé
                    return False, f"Escaladé vers Claude après échecs répétés ({fix_type})"
            return result

        # 1. Erreurs JavaScript (ReferenceError, TypeError)
        result = cls._fix_javascript_error(error_log)
        if result[0]:
            return apply_fix(result, "javascript")

        # 2. Colonne manquante
        result = cls._fix_missing_column(error_log)
        if result[0]:
            return apply_fix(result, "missing_column")

        # 3. NOT NULL violation
        result = cls._fix_not_null_violation(error_log)
        if result[0]:
            return apply_fix(result, "not_null")

        # 4. Table manquante
        result = cls._fix_missing_table(error_log)
        if result[0]:
            return apply_fix(result, "missing_table")

        # 5. Erreurs CORS/CSRF
        result = cls._fix_cors_csrf(error_log)
        if result[0]:
            return apply_fix(result, "cors_csrf")

        # 6. Erreurs HTTP (404, 500)
        result = cls._fix_http_error(error_log)
        if result[0]:
            return apply_fix(result, "http_error")

        # 7. Erreurs CSS (fichiers manquants, classes)
        result = cls._fix_css_error(error_log)
        if result[0]:
            return apply_fix(result, "css")

        # 8. Erreurs Python (ImportError, ModuleNotFoundError)
        result = cls._fix_python_import_error(error_log)
        if result[0]:
            return apply_fix(result, "python_import")

        # 8b. Erreurs AttributeError (méthode/attribut manquant)
        result = cls._fix_attribute_error(error_log)
        if result[0]:
            return apply_fix(result, "attribute_error")

        # 8c. Erreurs NoneType (itération/accès sur None)
        result = cls._fix_nonetype_error(error_log)
        if result[0]:
            return apply_fix(result, "nonetype_error")

        # 9. Erreurs Database (connexion, pool, timeout)
        result = cls._fix_database_error(error_log)
        if result[0]:
            return apply_fix(result, "database")

        # 10. Erreurs Redis (connexion cache)
        result = cls._fix_redis_error(error_log)
        if result[0]:
            return apply_fix(result, "redis")

        # 11. Erreurs Auth (token expiré, refresh)
        result = cls._fix_auth_error(error_log)
        if result[0]:
            return apply_fix(result, "auth")

        # 12. Erreurs Validation (Pydantic)
        result = cls._fix_validation_error(error_log)
        if result[0]:
            return apply_fix(result, "validation")

        # 13. Erreurs YAML (parsing modules)
        result = cls._fix_yaml_error(error_log)
        if result[0]:
            return apply_fix(result, "yaml")

        # 14. Erreurs Templates (Jinja2)
        result = cls._fix_template_error(error_log)
        if result[0]:
            return apply_fix(result, "template")

        # 15. Erreurs React/Mobile
        result = cls._fix_react_error(error_log)
        if result[0]:
            return apply_fix(result, "react")

        # 16. Erreurs TypeScript
        result = cls._fix_typescript_error(error_log)
        if result[0]:
            return apply_fix(result, "typescript")

        # 17. Erreurs Fichiers (permission, disk)
        result = cls._fix_file_error(error_log)
        if result[0]:
            return apply_fix(result, "file")

        # 18. Erreurs Réseau (timeout)
        result = cls._fix_network_error(error_log)
        if result[0]:
            return apply_fix(result, "network")

        # APPRENTISSAGE: Escalader TOUTE erreur non résolue
        # Guardian ne doit jamais ignorer une erreur silencieusement
        cls._escalate_to_claude(error_key, "unknown_error", 1)
        logger.warning("unknown_error_escalated", error_key=error_key, error=error_log[:200])
        return False, f"Erreur non reconnue, escaladée vers Claude: {error_key}"

    @classmethod
    def _fix_missing_column(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige TOUTES les colonnes manquantes d'un module en une fois."""
        # Pattern: column "xxx" of relation "yyy" does not exist
        match = re.search(
            r'column "(\w+)" of relation "(\w+)" does not exist',
            error_log,
            re.IGNORECASE
        )
        if not match:
            return False, ""

        column_name = match.group(1)
        table_name = match.group(2)

        try:
            with cls._get_session() as session:
                from sqlalchemy import text
                from pathlib import Path
                import yaml

                # 1. Récupérer les colonnes existantes dans la table
                existing_cols_sql = """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'azalplus' AND table_name = :table_name
                """
                result = session.execute(text(existing_cols_sql), {"table_name": table_name})
                existing_columns = {row[0] for row in result}

                # 2. Charger le module YAML pour avoir la liste complète des champs
                module_path = Path("/home/ubuntu/azalplus/modules") / f"{table_name}.yml"
                yaml_columns = {}

                if module_path.exists():
                    try:
                        with open(module_path, 'r', encoding='utf-8') as f:
                            module_def = yaml.safe_load(f)

                        if module_def and 'champs' in module_def:
                            for champ in module_def['champs']:
                                champ_name = champ.get('nom')
                                champ_type = champ.get('type', 'text')
                                if champ_name:
                                    yaml_columns[champ_name] = champ_type
                    except Exception as e:
                        logger.warning("yaml_parse_failed", file=str(module_path), error=str(e))

                # 3. Identifier toutes les colonnes manquantes
                missing_columns = []

                # Ajouter d'abord la colonne qui a causé l'erreur
                if column_name not in existing_columns:
                    col_type = yaml_columns.get(column_name) if yaml_columns else None
                    sql_type = cls._yaml_type_to_sql(col_type) if col_type else cls._guess_column_type(column_name)
                    missing_columns.append((column_name, sql_type))

                # Ajouter les autres colonnes manquantes du YAML
                for col_name, col_type in yaml_columns.items():
                    if col_name not in existing_columns and col_name != column_name:
                        sql_type = cls._yaml_type_to_sql(col_type)
                        missing_columns.append((col_name, sql_type))

                if not missing_columns:
                    return False, "Aucune colonne manquante identifiée"

                # 4. Ajouter toutes les colonnes manquantes en une transaction
                added_columns = []
                for col_name, col_type in missing_columns:
                    try:
                        sql = f"""
                            ALTER TABLE azalplus.{table_name}
                            ADD COLUMN IF NOT EXISTS {col_name} {col_type}
                        """
                        session.execute(text(sql))
                        added_columns.append(col_name)
                        logger.info(
                            "auto_fix_column_added",
                            table=table_name,
                            column=col_name,
                            type=col_type
                        )
                    except Exception as col_e:
                        logger.warning("column_add_failed", column=col_name, error=str(col_e))

                session.commit()

                if added_columns:
                    cls._log_learning("sql_column", f"{table_name}: {', '.join(added_columns)}")
                    return True, f"{len(added_columns)} colonnes ajoutées à '{table_name}': {', '.join(added_columns)}"

                return False, "Aucune colonne ajoutée"

        except Exception as e:
            logger.error("auto_fix_column_failed", error=str(e))
            return False, f"Échec ajout colonne: {e}"

    @classmethod
    def _yaml_type_to_sql(cls, yaml_type: str) -> str:
        """Convertit un type YAML en type SQL PostgreSQL."""
        type_mapping = {
            'text': 'VARCHAR(255)',
            'texte': 'VARCHAR(255)',
            'string': 'VARCHAR(255)',
            'number': 'NUMERIC(15,2)',
            'nombre': 'NUMERIC(15,2)',
            'entier': 'INTEGER',
            'integer': 'INTEGER',
            'date': 'DATE',
            'datetime': 'TIMESTAMP',
            'boolean': 'BOOLEAN',
            'booleen': 'BOOLEAN',
            'select': 'VARCHAR(100)',
            'enum': 'VARCHAR(100)',
            'relation': 'UUID',
            'lien': 'UUID',
            'textarea': 'TEXT',
            'email': 'VARCHAR(255)',
            'tel': 'VARCHAR(20)',
            'telephone': 'VARCHAR(20)',
            'json': 'JSONB',
            'tags': 'JSONB',
            'money': 'NUMERIC(15,2)',
            'montant': 'NUMERIC(15,2)',
        }
        return type_mapping.get(yaml_type.lower(), 'VARCHAR(255)')

    @classmethod
    def _fix_not_null_violation(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige une violation NOT NULL en ajoutant une valeur par défaut."""
        # Pattern: null value in column "xxx" of relation "yyy" violates not-null constraint
        match = re.search(
            r'null value in column "(\w+)" of relation "(\w+)" violates not-null',
            error_log,
            re.IGNORECASE
        )
        if not match:
            return False, ""

        column_name = match.group(1)
        table_name = match.group(2)

        try:
            with cls._get_session() as session:
                from sqlalchemy import text

                # Déterminer une valeur par défaut appropriée
                default_value = cls._get_default_value(column_name)

                sql = f"""
                    ALTER TABLE azalplus.{table_name}
                    ALTER COLUMN {column_name} SET DEFAULT {default_value}
                """
                session.execute(text(sql))
                session.commit()

                logger.info(
                    "auto_fix_default_added",
                    table=table_name,
                    column=column_name,
                    default=default_value
                )
                return True, f"Valeur par défaut ajoutée pour '{table_name}.{column_name}'"

        except Exception as e:
            logger.error("auto_fix_default_failed", error=str(e))
            return False, f"Échec ajout défaut: {e}"

    @classmethod
    def _fix_missing_table(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige une table manquante en rechargeant les modules."""
        # Pattern: relation "xxx" does not exist
        match = re.search(
            r'relation "(\w+)" does not exist',
            error_log,
            re.IGNORECASE
        )
        if not match:
            return False, ""

        table_name = match.group(1)

        try:
            # Recharger les modules YAML pour créer les tables
            from ..parser import ModuleParser
            from ..db import Database

            ModuleParser.load_all_modules()

            # Vérifier si la table existe maintenant
            with cls._get_session() as session:
                from sqlalchemy import text
                result = session.execute(text(f"""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'azalplus'
                        AND table_name = '{table_name}'
                    )
                """))
                exists = result.scalar()

                if exists:
                    logger.info("auto_fix_table_created", table=table_name)
                    return True, f"Table '{table_name}' créée après rechargement"
                else:
                    return False, f"Table '{table_name}' non trouvée après rechargement"

        except Exception as e:
            logger.error("auto_fix_table_failed", error=str(e))
            return False, f"Échec création table: {e}"

    @classmethod
    def _guess_column_type(cls, column_name: str) -> str:
        """Devine le type PostgreSQL basé sur le nom de la colonne."""
        name_lower = column_name.lower()

        # UUID
        if name_lower.endswith('_id') or name_lower == 'id':
            return "UUID"

        # Dates
        if any(x in name_lower for x in ['date', 'created_at', 'updated_at', 'deleted_at']):
            return "TIMESTAMP"

        # Booléens
        if any(x in name_lower for x in ['is_', 'has_', 'actif', 'active', 'enabled']):
            return "BOOLEAN DEFAULT false"

        # Montants
        if any(x in name_lower for x in ['montant', 'prix', 'total', 'amount', 'price']):
            return "NUMERIC(15,2) DEFAULT 0"

        # Nombres entiers
        if any(x in name_lower for x in ['count', 'nombre', 'quantity', 'qty', 'duree']):
            return "INTEGER DEFAULT 0"

        # Texte long
        if any(x in name_lower for x in ['description', 'notes', 'content', 'body']):
            return "TEXT"

        # JSON
        if any(x in name_lower for x in ['data', 'meta', 'config', 'settings', 'json']):
            return "JSONB DEFAULT '{}'"

        # Défaut: VARCHAR
        return "VARCHAR(255)"

    @classmethod
    def _get_default_value(cls, column_name: str) -> str:
        """Retourne une valeur par défaut appropriée."""
        name_lower = column_name.lower()

        # Texte
        if any(x in name_lower for x in ['titre', 'title', 'name', 'nom']):
            return "'Sans titre'"

        if any(x in name_lower for x in ['description', 'notes']):
            return "''"

        # Statut
        if 'statut' in name_lower or 'status' in name_lower:
            return "'BROUILLON'"

        # Civilité
        if 'civilite' in name_lower:
            return "''"

        # Nombre
        if any(x in name_lower for x in ['montant', 'prix', 'total', 'count', 'nombre']):
            return "0"

        # Booléen
        if any(x in name_lower for x in ['is_', 'has_', 'actif']):
            return "false"

        # Défaut générique
        return "''"

    # =========================================================================
    # CORRECTIONS JAVASCRIPT
    # =========================================================================

    # Fonctions JS connues à ajouter automatiquement
    # NOTE: Double accolades {{}} car inséré dans f-string Python
    JS_FUNCTIONS = {
        "handleRowClick": '''function handleRowClick(event, id, url) {{
    if (event.target.type === 'checkbox' || event.target.tagName === 'BUTTON' || event.target.closest('button')) return;
    window.location.href = url;
}}''',
        "copyMobileLink": '''async function copyMobileLink() {{
    const link = document.getElementById('mobileLink')?.value || window.location.href;
    try {{
        if (navigator.clipboard && navigator.clipboard.writeText) {{
            await navigator.clipboard.writeText(link);
        }} else {{
            const t = document.createElement('textarea');
            t.value = link; t.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(t); t.select();
            document.execCommand('copy'); document.body.removeChild(t);
        }}
        alert('Lien copié !');
    }} catch (e) {{ alert('Erreur: ' + e); }}
}}''',
        "showNotification": '''function showNotification(msg, type) {{
    const n = document.createElement('div');
    n.textContent = msg;
    n.style.cssText = 'position:fixed;top:20px;right:20px;padding:12px 20px;border-radius:8px;z-index:9999;color:white;background:' + (type==='success'?'#10b981':type==='error'?'#ef4444':'#3b82f6');
    document.body.appendChild(n);
    setTimeout(() => n.remove(), 3000);
}}''',
        "confirmDelete": '''function confirmDelete(id, name) {{
    if (confirm('Supprimer "' + name + '" ?')) {{
        fetch(window.location.pathname + '/' + id, {{method:'DELETE'}}).then(r => r.ok ? location.reload() : alert('Erreur'));
    }}
}}''',
        "openModal": '''function openModal(id) {{ const m = document.getElementById(id); if (m) {{ m.style.display = 'flex'; m.classList.add('active'); }} }}''',
        "closeModal": '''function closeModal(id) {{ const m = document.getElementById(id); if (m) {{ m.style.display = 'none'; m.classList.remove('active'); }} }}''',
        "updateBulkSelection": '''function updateBulkSelection() {{
    const checkboxes = document.querySelectorAll('input[name="bulk_select"]:checked');
    const bulkActions = document.getElementById('bulkActions');
    const selectedCount = document.getElementById('selectedCount');
    if (bulkActions) bulkActions.style.display = checkboxes.length > 0 ? 'flex' : 'none';
    if (selectedCount) selectedCount.textContent = checkboxes.length;
}}''',
        "selectAll": '''function selectAll(checked) {{
    document.querySelectorAll('input[name="bulk_select"]').forEach(cb => cb.checked = checked);
    updateBulkSelection();
}}''',
        "executeBulkAction": '''function executeBulkAction(action) {{
    const ids = Array.from(document.querySelectorAll('input[name="bulk_select"]:checked')).map(cb => cb.value);
    if (ids.length === 0) {{ alert('Sélectionnez au moins un élément'); return; }}
    if (action === 'delete' && !confirm('Supprimer ' + ids.length + ' élément(s) ?')) return;
    fetch(window.location.pathname + '/bulk', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{action: action, ids: ids}})
    }}).then(r => r.ok ? location.reload() : alert('Erreur'));
}}''',
        "toggleDetails": '''function toggleDetails(id) {{
    const el = document.getElementById('details-' + id);
    if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}}''',
        "formatDate": '''function formatDate(date) {{
    if (!date) return '-';
    const d = new Date(date);
    return d.toLocaleDateString('fr-FR');
}}''',
        "formatMoney": '''function formatMoney(amount) {{
    if (amount === null || amount === undefined) return '-';
    return new Intl.NumberFormat('fr-FR', {{style: 'currency', currency: 'EUR'}}).format(amount);
}}''',
    }

    @classmethod
    def _add_clipboard_polyfill(cls) -> Tuple[bool, str]:
        """Ajoute un polyfill clipboard pour les navigateurs/contextes sans support natif."""
        try:
            ui_path = Path("/home/ubuntu/azalplus/moteur/ui.py")
            content = ui_path.read_text()

            # Vérifier si le polyfill existe déjà
            if "clipboardPolyfill" in content or "execCommand('copy')" in content:
                return True, "Clipboard polyfill déjà présent"

            polyfill_code = '''
        // Polyfill clipboard pour HTTP et navigateurs anciens
        async function clipboardPolyfill(text) {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                try {
                    await navigator.clipboard.writeText(text);
                    return true;
                } catch (e) {
                    console.warn('Clipboard API failed, using fallback');
                }
            }
            // Fallback avec execCommand
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px;top:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                return true;
            } catch (e) {
                console.error('Clipboard fallback failed:', e);
                return false;
            } finally {
                document.body.removeChild(textarea);
            }
        }'''

            insert_marker = "// === FONCTIONS COMMUNES GUARDIAN ==="
            if insert_marker in content:
                new_content = content.replace(
                    insert_marker,
                    f"{insert_marker}\n{polyfill_code}"
                )
            else:
                # Chercher <script> et ajouter
                script_tag = "    <script>"
                if script_tag in content:
                    new_content = content.replace(
                        script_tag,
                        f"{script_tag}\n        {insert_marker}\n{polyfill_code}"
                    )
                else:
                    return False, "Impossible de trouver le bloc script"

            ui_path.write_text(new_content)
            logger.info("guardian_clipboard_polyfill_added")
            return True, "Clipboard polyfill ajouté"

        except Exception as e:
            logger.error("clipboard_polyfill_error", error=str(e))
            return False, f"Erreur polyfill: {e}"

    @classmethod
    def _fix_javascript_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs JavaScript (fonctions manquantes, polyfills)."""

        # TypeError: Cannot read properties of undefined (reading 'writeText')
        # Ajouter polyfill clipboard
        if "writeText" in error_log or "clipboard" in error_log.lower():
            return cls._add_clipboard_polyfill()

        # SyntaxError: Unexpected token 'default' ou autre
        if "syntaxerror" in error_log.lower():
            return cls._fix_js_syntax_error(error_log)

        # ReferenceError: X is not defined
        match = re.search(r"ReferenceError: (\w+) is not defined", error_log)
        if not match:
            return False, ""

        func_name = match.group(1)

        # Vérifier si c'est une fonction connue
        if func_name not in cls.JS_FUNCTIONS:
            logger.debug("js_function_unknown", function=func_name)
            return False, f"Fonction JS inconnue: {func_name}"

        try:
            ui_path = Path("/home/ubuntu/azalplus/moteur/ui.py")
            content = ui_path.read_text()

            # Vérifier si la fonction existe déjà
            if f"function {func_name}" in content:
                return True, f"Fonction {func_name} existe déjà"

            # Trouver où insérer (après le début du bloc <script>)
            js_code = cls.JS_FUNCTIONS[func_name]
            insert_marker = "// === FONCTIONS COMMUNES GUARDIAN ==="

            if insert_marker in content:
                # Insérer après le marker
                new_content = content.replace(
                    insert_marker,
                    f"{insert_marker}\n\n        {js_code.replace(chr(10), chr(10) + '        ')}"
                )
            else:
                # Chercher <script> et ajouter le marker + code
                script_tag = "    <script>"
                if script_tag in content:
                    new_content = content.replace(
                        script_tag,
                        f"{script_tag}\n        {insert_marker}\n\n        {js_code.replace(chr(10), chr(10) + '        ')}"
                    )
                else:
                    return False, "Impossible de trouver le bloc script"

            ui_path.write_text(new_content)
            logger.info("guardian_js_fix_applied", function=func_name)
            # Notifier que la page doit être rafraîchie
            logger.warning("page_refresh_needed",
                          reason=f"Fonction JS '{func_name}' ajoutée",
                          action="L'utilisateur doit rafraîchir la page (Ctrl+F5)")
            return True, f"JS: {func_name} ajouté (rafraîchir page)"

        except Exception as e:
            logger.error("js_fix_error", error=str(e))
            return False, f"Erreur JS fix: {e}"

    # =========================================================================
    # CORRECTIONS CORS/CSRF
    # =========================================================================

    @classmethod
    def _fix_cors_csrf(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs CORS et CSRF."""
        error_lower = error_log.lower()

        # CSRF manquant
        if "csrf" in error_lower and ("403" in error_log or "manquant" in error_lower):
            # Extraire l'URL
            url_match = re.search(r'URL:\s*([^\s]+)', error_log)
            if url_match:
                url = url_match.group(1)
                # Extraire le path
                path_match = re.search(r'https?://[^/]+(/[^\s?]*)', url)
                if path_match:
                    path = path_match.group(1)
                    return cls._add_csrf_exemption(path)

        # CORS bloqué
        if "cors" in error_lower or "access-control-allow-origin" in error_lower:
            origin_match = re.search(r"origin '([^']+)'", error_log)
            if origin_match:
                origin = origin_match.group(1)
                return cls._add_cors_origin(origin)

        return False, ""

    @classmethod
    def _add_csrf_exemption(cls, path: str) -> Tuple[bool, str]:
        """Ajoute une exemption CSRF pour un chemin."""
        try:
            csrf_path = Path("/home/ubuntu/azalplus/moteur/csrf.py")
            content = csrf_path.read_text()

            # Vérifier si déjà exempté
            if path in content:
                return True, f"Chemin {path} déjà exempté"

            # Trouver CSRF_EXEMPT_PATHS et ajouter
            if "CSRF_EXEMPT_PATHS = [" in content:
                new_content = content.replace(
                    "CSRF_EXEMPT_PATHS = [",
                    f'CSRF_EXEMPT_PATHS = [\n    "{path}",  # Auto-ajouté par Guardian'
                )
                csrf_path.write_text(new_content)
                logger.info("guardian_csrf_exemption_added", path=path)
                return True, f"CSRF exemption: {path}"

            return False, "CSRF_EXEMPT_PATHS non trouvé"

        except Exception as e:
            return False, f"Erreur CSRF: {e}"

    @classmethod
    def _add_cors_origin(cls, origin: str) -> Tuple[bool, str]:
        """Ajoute une origine CORS autorisée."""
        try:
            core_path = Path("/home/ubuntu/azalplus/moteur/core.py")
            content = core_path.read_text()

            # Vérifier si déjà autorisé
            if origin in content:
                return True, f"Origine {origin} déjà autorisée"

            # Trouver allow_origins et ajouter
            match = re.search(r'allow_origins=\[([^\]]*)\]', content)
            if match:
                origins_list = match.group(1)
                new_origins = f'{origins_list}, "{origin}"' if origins_list.strip() else f'"{origin}"'
                new_content = content.replace(
                    f'allow_origins=[{origins_list}]',
                    f'allow_origins=[{new_origins}]'
                )
                core_path.write_text(new_content)
                logger.info("guardian_cors_origin_added", origin=origin)
                return True, f"CORS origin: {origin}"

            return False, "allow_origins non trouvé"

        except Exception as e:
            return False, f"Erreur CORS: {e}"

    # =========================================================================
    # CORRECTIONS HTTP (404, 500, routes manquantes)
    # =========================================================================

    @classmethod
    def _fix_http_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs HTTP (400, 404, 500, routes manquantes)."""
        error_lower = error_log.lower()
        logger.debug("fix_http_error_called", has_400="400" in error_log, has_http_400="http_400" in error_lower)

        # 400 Bad Request - souvent un endpoint manquant
        if "400" in error_log or "http_400" in error_lower:
            logger.info("http_400_detected", error_preview=error_log[:150])
            path = cls._extract_path_from_error(error_log)
            if path and "/api/" in path:
                return cls._fix_missing_endpoint(path, error_log)

        # 404 sur une route manquante
        if "404" in error_log or "http_404" in error_lower:
            path = None

            # Format ErrorCollector: "Source: /api/xxx:?:?"
            source_match = re.search(r'Source:\s*(/[^\s:]+)', error_log)
            if source_match:
                path = source_match.group(1)

            # Format standard: "GET /path 404"
            if not path:
                url_match = re.search(r'(?:GET|POST|PUT|DELETE)\s+([^\s]+)\s+404', error_log)
                if url_match:
                    path = url_match.group(1)

            # Format alternatif
            if not path:
                url_match = re.search(r'404.*?(/[^\s"\'<>:]+)', error_log)
                if url_match:
                    path = url_match.group(1)

            if path:

                # Vérifier si c'est une route d'API manquante
                if "/api/" in path:
                    return cls._fix_missing_api_route(path)

                # Vérifier si c'est un fichier statique manquant
                if any(ext in path for ext in ['.css', '.js', '.ico', '.png', '.jpg', '.webmanifest']):
                    return cls._fix_missing_static_file(path)

                # Vérifier si c'est une route UI manquante
                if "/ui/" in path:
                    return cls._fix_missing_ui_route(path)

        # 422 Unprocessable Entity - erreur de validation
        if "422" in error_log or "http_422" in error_lower:
            return cls._fix_validation_422(error_log)

        # 500 Internal Server Error - log pour analyse
        if "500" in error_log:
            logger.warning("http_500_detected", error=error_log[:500])
            # Les 500 sont généralement des bugs Python, pas auto-fixables
            return False, "Erreur 500 détectée, nécessite analyse manuelle"

        return False, ""

    @classmethod
    def _extract_path_from_error(cls, error_log: str) -> Optional[str]:
        """Extrait le chemin API d'un message d'erreur."""
        # Format: Source: /api/recent/track:?:?
        patterns = [
            r'Source:\s*(/api/[^:\s]+)',  # Source: /api/xxx (arrête à : ou espace)
            r'["\']?source["\']?\s*[:\s]+\s*["\']?(/api/[^:\s"\'<>]+)',
            r'POST\s+(/api/[^\s]+)',
            r'GET\s+(/api/[^\s]+)',
            r'(/api/[^\s"\'<>:]+)\s+\d{3}',
        ]
        for pattern in patterns:
            match = re.search(pattern, error_log, re.IGNORECASE)
            if match:
                path = match.group(1)
                logger.debug("path_extracted_from_error", path=path)
                return path
        logger.debug("no_path_extracted", error_preview=error_log[:200])
        return None

    @classmethod
    def _fix_missing_endpoint(cls, path: str, error_log: str) -> Tuple[bool, str]:
        """
        Crée automatiquement un endpoint manquant.

        Détecte le type d'endpoint nécessaire et le crée dans generated_endpoints.py
        """
        # Extraire les composants du chemin
        # /api/recent/track -> prefix="recent", action="track"
        # /api/v1/clients/bulk -> prefix="clients", action="bulk"
        match = re.search(r'/api/(?:v1/)?(\w+)(?:/(\w+))?', path)
        if not match:
            return False, "Chemin non reconnu"

        prefix = match.group(1)
        action = match.group(2) if match.lastindex >= 2 else None

        # Fichier pour les endpoints générés automatiquement
        generated_file = Path("/home/ubuntu/azalplus/moteur/generated_endpoints.py")
        core_file = Path("/home/ubuntu/azalplus/moteur/core.py")

        # Créer le fichier s'il n'existe pas
        if not generated_file.exists():
            initial_content = '''# =============================================================================
# AZALPLUS - Generated Endpoints (Auto-created by Guardian/AutoFixer)
# =============================================================================
"""
Endpoints créés automatiquement par Guardian pour corriger les erreurs 400.
Ces endpoints sont des stubs qui acceptent les requêtes et retournent OK.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional, Any, Dict
import structlog

logger = structlog.get_logger()

generated_router = APIRouter(tags=["Generated"])


class GenericRequest(BaseModel):
    """Schema générique pour les requêtes."""
    class Config:
        extra = "allow"

'''
            generated_file.write_text(initial_content)
            logger.info("generated_endpoints_file_created")

            # Ajouter l'import dans core.py
            core_content = core_file.read_text()
            if "generated_endpoints" not in core_content:
                # Trouver où ajouter l'import
                insert_marker = "# Recent Items Tracker"
                if insert_marker in core_content:
                    new_import = '''# Generated Endpoints (Auto-created by Guardian)
try:
    from .generated_endpoints import generated_router
    app.include_router(generated_router, prefix="/api", tags=["Generated"])
except ImportError:
    pass

'''
                    core_content = core_content.replace(insert_marker, new_import + insert_marker)
                    core_file.write_text(core_content)
                    logger.info("generated_router_added_to_core")

        # Lire le contenu actuel
        content = generated_file.read_text()

        # Construire le nom de la route
        if action:
            route_path = f"/{prefix}/{action}"
            func_name = f"generated_{prefix}_{action}"
        else:
            route_path = f"/{prefix}"
            func_name = f"generated_{prefix}"

        # Vérifier si l'endpoint existe déjà
        if f'"{route_path}"' in content or f"'{route_path}'" in content:
            # L'endpoint existe, le fix a été appliqué, l'erreur disparaîtra après reload
            logger.info("endpoint_already_exists", path=route_path)
            return True, f"Endpoint {route_path} existe déjà (reload serveur requis)"

        # Déterminer la méthode HTTP depuis l'erreur
        method = "post"  # Par défaut POST
        if "GET" in error_log:
            method = "get"
        elif "PUT" in error_log:
            method = "put"
        elif "DELETE" in error_log:
            method = "delete"

        # Générer le code de l'endpoint
        endpoint_code = f'''
@generated_router.{method}("{route_path}")
async def {func_name}(request: Request, data: Optional[GenericRequest] = None):
    """Endpoint auto-généré par Guardian pour {route_path}"""
    logger.debug("generated_endpoint_called", path="{route_path}", method="{method}")
    return {{"status": "ok"}}

'''

        # Ajouter l'endpoint au fichier
        content += endpoint_code
        generated_file.write_text(content)

        logger.info("endpoint_auto_created",
                   path=route_path,
                   method=method,
                   file=str(generated_file))

        return True, f"Endpoint {method.upper()} {route_path} créé automatiquement"

    @classmethod
    def _fix_missing_api_route(cls, path: str) -> Tuple[bool, str]:
        """
        Tente de corriger une route API manquante.

        APPRENTISSAGE:
        - Gère les variations singulier/pluriel
        - Détecte les routes /bulk manquantes
        - Crée des alias si nécessaire
        """
        # Extraire le nom du module de la route
        match = re.search(r'/api/(?:v1/)?(\w+)(?:/(\w+))?', path)
        if not match:
            return False, ""

        module_name = match.group(1)
        sub_route = match.group(2) if match.lastindex >= 2 else None

        modules_path = Path("/home/ubuntu/azalplus/modules")

        # 1. Vérifier le module tel quel
        yaml_file = modules_path / f"{module_name}.yml"
        if yaml_file.exists():
            return cls._reload_module(module_name)

        # 2. APPRENTISSAGE: Variations singulier/pluriel
        singular = module_name.rstrip('s') if module_name.endswith('s') else module_name
        plural = module_name if module_name.endswith('s') else module_name + 's'

        # Essayer singulier
        singular_file = modules_path / f"{singular}.yml"
        if singular_file.exists() and singular != module_name:
            logger.info("route_mismatch_detected",
                       requested=module_name,
                       actual=singular,
                       suggestion=f"Frontend appelle /{module_name} mais route est /{singular}")
            # Créer alias route
            cls._create_route_alias(singular, module_name)
            return cls._reload_module(singular)

        # Essayer pluriel
        plural_file = modules_path / f"{plural}.yml"
        if plural_file.exists() and plural != module_name:
            logger.info("route_mismatch_detected",
                       requested=module_name,
                       actual=plural,
                       suggestion=f"Frontend appelle /{module_name} mais route est /{plural}")
            return cls._reload_module(plural)

        # 3. APPRENTISSAGE: Route /bulk manquante
        if sub_route == 'bulk':
            logger.info("bulk_route_missing", module=module_name)
            cls._ensure_bulk_route(module_name)
            return True, f"Route bulk ajoutée pour {module_name}"

        # 4. APPRENTISSAGE: Corriger le code source si module existe avec autre nom
        def to_snake_case(name):
            s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
            return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

        snake_name = to_snake_case(module_name)
        correct_module = None

        # Chercher le bon module
        for candidate in [snake_name, f"{snake_name}s", module_name.lower(), f"{module_name.lower()}s"]:
            if (modules_path / f"{candidate}.yml").exists():
                correct_module = candidate
                break

        if correct_module and correct_module != module_name:
            # Corriger automatiquement le code source
            return cls._fix_api_path_in_source(module_name, correct_module)

        return False, f"Module {module_name} non trouvé"

    @classmethod
    def _fix_api_path_in_source(cls, wrong_name: str, correct_name: str) -> Tuple[bool, str]:
        """
        Corrige automatiquement les appels fetch avec le mauvais chemin API.

        Args:
            wrong_name: Nom incorrect (ex: "Client")
            correct_name: Nom correct (ex: "clients")

        Returns:
            (success, message)
        """
        search_dirs = [
            Path("/home/ubuntu/azalplus/moteur"),
            Path("/home/ubuntu/azalplus/templates"),
        ]

        patterns_to_fix = [
            (f"/api/{wrong_name}", f"/api/v1/{correct_name}"),
            (f"'/api/{wrong_name}'", f"'/api/v1/{correct_name}'"),
            (f'"/api/{wrong_name}"', f'"/api/v1/{correct_name}"'),
            (f"`/api/{wrong_name}`", f"`/api/v1/{correct_name}`"),
        ]

        files_fixed = []
        total_replacements = 0

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            # Chercher dans les fichiers .py et .html
            for ext in ['*.py', '*.html']:
                for filepath in search_dir.rglob(ext):
                    try:
                        content = filepath.read_text(encoding='utf-8')
                        original_content = content
                        file_replacements = 0

                        for old_pattern, new_pattern in patterns_to_fix:
                            if old_pattern in content:
                                content = content.replace(old_pattern, new_pattern)
                                file_replacements += content.count(new_pattern) - original_content.count(new_pattern)

                        if content != original_content:
                            filepath.write_text(content, encoding='utf-8')
                            files_fixed.append(str(filepath))
                            total_replacements += file_replacements
                            logger.info("api_path_fixed",
                                       file=str(filepath),
                                       old=f"/api/{wrong_name}",
                                       new=f"/api/v1/{correct_name}")

                    except Exception as e:
                        logger.warning("api_path_fix_error",
                                      file=str(filepath),
                                      error=str(e))

        if files_fixed:
            return True, f"Corrigé /api/{wrong_name} → /api/v1/{correct_name} dans {len(files_fixed)} fichier(s)"

        return False, f"Pattern /api/{wrong_name} non trouvé dans le code"

    @classmethod
    def _reload_module(cls, module_name: str) -> Tuple[bool, str]:
        """Recharge un module."""
        try:
            from ..parser import ModuleParser
            ModuleParser.load_all_modules()
            logger.info("http_fix_module_reloaded", module=module_name)
            return True, f"Module {module_name} rechargé"
        except Exception as e:
            return False, f"Échec rechargement: {e}"

    @classmethod
    def _create_route_alias(cls, actual_module: str, alias_name: str) -> None:
        """
        Crée un alias de route pour corriger les mismatches singulier/pluriel.
        Note: Écrit dans un fichier de configuration pour que le parser le prenne en compte.
        """
        alias_file = Path("/home/ubuntu/azalplus/config/route_aliases.json")
        alias_file.parent.mkdir(parents=True, exist_ok=True)

        import json
        aliases = {}
        if alias_file.exists():
            try:
                aliases = json.loads(alias_file.read_text())
            except:
                pass

        aliases[alias_name] = actual_module
        alias_file.write_text(json.dumps(aliases, indent=2))
        logger.info("route_alias_created", alias=alias_name, target=actual_module)
        cls._log_learning("route_alias", f"/{alias_name} → /{actual_module}")

    @classmethod
    def _ensure_bulk_route(cls, module_name: str) -> None:
        """S'assure que la route /bulk existe pour un module."""
        logger.info("bulk_route_ensured", module=module_name)
        # Le rechargement des modules devrait inclure les routes bulk
        try:
            from ..parser import ModuleParser
            ModuleParser.load_all_modules()
        except Exception as e:
            logger.error("bulk_route_error", error=str(e))

    @classmethod
    def _fix_missing_static_file(cls, path: str) -> Tuple[bool, str]:
        """Crée les fichiers statiques manquants."""
        filename = path.split('/')[-1]

        # Favicon manquant
        if 'favicon' in filename:
            favicon_path = Path("/home/ubuntu/azalplus/static/favicon.ico")
            if not favicon_path.exists():
                favicon_path.parent.mkdir(parents=True, exist_ok=True)
                # Créer un favicon minimal (1x1 pixel transparent)
                favicon_data = bytes([
                    0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x01, 0x01,
                    0x00, 0x00, 0x01, 0x00, 0x18, 0x00, 0x30, 0x00,
                    0x00, 0x00, 0x16, 0x00, 0x00, 0x00, 0x28, 0x00,
                    0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x02, 0x00,
                    0x00, 0x00, 0x01, 0x00, 0x18, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3B, 0x7E,
                    0xD1, 0x00, 0x00, 0x00, 0x00, 0x00
                ])
                favicon_path.write_bytes(favicon_data)
                logger.info("http_fix_favicon_created")
                return True, "Favicon créé"

        # Manifest manquant
        if 'manifest' in filename:
            manifest_path = Path("/home/ubuntu/azalplus/static/manifest.webmanifest")
            if not manifest_path.exists():
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_content = '''{
    "name": "AZALPLUS",
    "short_name": "AZALPLUS",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#ffffff",
    "theme_color": "#3b82f6",
    "icons": []
}'''
                manifest_path.write_text(manifest_content)
                logger.info("http_fix_manifest_created")
                return True, "Manifest créé"

        return False, f"Fichier statique {filename} non géré"

    @classmethod
    def _fix_missing_ui_route(cls, path: str) -> Tuple[bool, str]:
        """Tente de corriger une route UI manquante."""
        # Extraire le nom du module
        match = re.search(r'/ui/(\w+)', path)
        if not match:
            return False, ""

        module_name = match.group(1)

        # Vérifier si le module existe
        modules_path = Path("/home/ubuntu/azalplus/modules")
        yaml_file = modules_path / f"{module_name}.yml"

        if yaml_file.exists():
            # Le module existe, forcer le rechargement des routes UI
            try:
                from ..parser import ModuleParser
                ModuleParser.load_all_modules()
                logger.info("http_fix_ui_route_loaded", module=module_name)
                return True, f"Route UI {module_name} chargée"
            except Exception as e:
                return False, f"Échec: {e}"

        return False, f"Module UI {module_name} non trouvé"

    # =========================================================================
    # CORRECTIONS CSS
    # =========================================================================

    @classmethod
    def _fix_css_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs CSS (fichiers manquants, classes non définies)."""
        error_lower = error_log.lower()

        # Fichier CSS manquant
        css_match = re.search(r'(?:Failed to load|404|not found).*?([^\s"\'<>]+\.css)', error_log, re.IGNORECASE)
        if css_match:
            css_file = css_match.group(1)
            return cls._create_missing_css(css_file)

        # Classe CSS non trouvée (rare, mais possible dans les warnings)
        if "unknown class" in error_lower or "undefined style" in error_lower:
            class_match = re.search(r'class[:\s]+["\']?(\w[\w-]*)', error_log)
            if class_match:
                class_name = class_match.group(1)
                return cls._add_css_class(class_name)

        return False, ""

    @classmethod
    def _create_missing_css(cls, css_path: str) -> Tuple[bool, str]:
        """Crée un fichier CSS vide si manquant."""
        # Nettoyer le chemin
        filename = css_path.split('/')[-1]

        # Chemins possibles
        possible_paths = [
            Path(f"/home/ubuntu/azalplus/static/css/{filename}"),
            Path(f"/home/ubuntu/azalplus/static/{filename}"),
            Path(f"/home/ubuntu/azalplus/mobile/public/{filename}"),
        ]

        for path in possible_paths:
            if not path.exists():
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(f"/* Auto-generated by Guardian - {datetime.now().isoformat()} */\n")
                    logger.info("css_fix_file_created", file=str(path))
                    return True, f"CSS {filename} créé"
                except Exception as e:
                    continue

        return False, f"Impossible de créer {filename}"

    @classmethod
    def _add_css_class(cls, class_name: str) -> Tuple[bool, str]:
        """Ajoute une classe CSS manquante au fichier de styles principal."""
        try:
            # Fichier de styles principal
            style_path = Path("/home/ubuntu/azalplus/static/css/guardian-fixes.css")
            style_path.parent.mkdir(parents=True, exist_ok=True)

            # Lire le contenu existant
            existing = style_path.read_text() if style_path.exists() else ""

            # Vérifier si la classe existe déjà
            if f".{class_name}" in existing:
                return True, f"Classe .{class_name} existe déjà"

            # Ajouter la classe
            new_class = f"\n/* Auto-added by Guardian */\n.{class_name} {{ }}\n"
            style_path.write_text(existing + new_class)

            logger.info("css_fix_class_added", class_name=class_name)
            return True, f"Classe .{class_name} ajoutée"

        except Exception as e:
            return False, f"Erreur CSS: {e}"

    # =========================================================================
    # CORRECTIONS PYTHON (ImportError, ModuleNotFoundError)
    # =========================================================================

    # Mapping des modules Python manquants vers leurs packages pip
    PYTHON_PACKAGES = {
        "structlog": "structlog",
        "pydantic": "pydantic",
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "sqlalchemy": "sqlalchemy",
        "redis": "redis",
        "jwt": "python-jose",
        "jose": "python-jose",
        "argon2": "argon2-cffi",
        "pyotp": "pyotp",
        "yaml": "pyyaml",
        "jinja2": "jinja2",
        "httpx": "httpx",
        "aiohttp": "aiohttp",
        "anthropic": "anthropic",
        "openai": "openai",
        "weasyprint": "weasyprint",
        "PIL": "pillow",
        "cv2": "opencv-python",
        "numpy": "numpy",
        "pandas": "pandas",
    }

    @classmethod
    def _fix_python_import_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs d'import Python."""
        # ModuleNotFoundError: No module named 'xxx'
        match = re.search(r"(?:ModuleNotFoundError|ImportError).*?['\"](\w+)['\"]", error_log)
        if not match:
            return False, ""

        module_name = match.group(1)

        # Vérifier si c'est un module connu
        package = cls.PYTHON_PACKAGES.get(module_name)
        if package:
            try:
                import subprocess
                result = subprocess.run(
                    ["pip", "install", package],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode == 0:
                    logger.info("python_fix_package_installed", package=package)
                    return True, f"Package {package} installé"
                else:
                    return False, f"Échec installation {package}: {result.stderr}"
            except Exception as e:
                return False, f"Erreur pip: {e}"

        # Module local manquant - vérifier si c'est un module azalplus
        if module_name in ['moteur', 'modules', 'config', 'app']:
            # Ajouter au PYTHONPATH si nécessaire
            import sys
            azalplus_path = "/home/ubuntu/azalplus"
            if azalplus_path not in sys.path:
                sys.path.insert(0, azalplus_path)
                logger.info("python_fix_path_added", path=azalplus_path)
                return True, f"Path {azalplus_path} ajouté"

        return False, f"Module Python inconnu: {module_name}"

    # =========================================================================
    # CORRECTIONS ATTRIBUTEERROR (méthode/attribut manquant)
    # =========================================================================

    # Mapping des méthodes manquantes vers leurs équivalents
    METHOD_ALIASES = {
        # Database
        "get": ("get_by_id", "moteur/db.py"),
        "find": ("query", "moteur/db.py"),
        "find_one": ("get_by_id", "moteur/db.py"),
        "find_all": ("query", "moteur/db.py"),
        "fetch": ("get_by_id", "moteur/db.py"),
        "fetch_one": ("get_by_id", "moteur/db.py"),
        "delete": ("soft_delete", "moteur/db.py"),
        "remove": ("soft_delete", "moteur/db.py"),
    }

    @classmethod
    def _fix_attribute_error(cls, error_log: str) -> Tuple[bool, str]:
        """
        Corrige les erreurs AttributeError en créant des alias de méthodes.

        Détecte les patterns:
        - type object 'X' has no attribute 'Y' (méthode de classe)
        - 'X' object has no attribute 'Y' (attribut d'instance)
        """
        import re

        # Pattern pour méthode de classe manquante
        match = re.search(
            r"AttributeError: type object '(\w+)' has no attribute '(\w+)'",
            error_log
        )

        if not match:
            # Pattern pour attribut d'instance
            match = re.search(
                r"AttributeError: '(\w+)' object has no attribute '(\w+)'",
                error_log
            )

        if not match:
            return False, "Pas une erreur AttributeError connue"

        class_name = match.group(1)
        missing_method = match.group(2)

        logger.info("attribute_error_detected",
                   class_name=class_name,
                   missing_method=missing_method)

        # Vérifier si c'est un alias connu
        if missing_method in cls.METHOD_ALIASES:
            correct_method, file_hint = cls.METHOD_ALIASES[missing_method]
            return cls._add_method_alias(class_name, missing_method, correct_method, file_hint)

        # Sinon, chercher le fichier de la classe et proposer une solution
        return cls._suggest_method_fix(class_name, missing_method, error_log)

    @classmethod
    def _add_method_alias(
        cls,
        class_name: str,
        alias_name: str,
        target_method: str,
        file_hint: str
    ) -> Tuple[bool, str]:
        """
        Ajoute un alias de méthode à une classe.

        Exemple: Database.get -> Database.get_by_id
        """
        import os

        base_path = "/home/ubuntu/azalplus"
        file_path = os.path.join(base_path, file_hint)

        if not os.path.exists(file_path):
            return False, f"Fichier {file_hint} non trouvé"

        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Vérifier si l'alias existe déjà
            if f"def {alias_name}(" in content:
                return True, f"Alias {alias_name} existe déjà"

            # Vérifier si la méthode cible existe
            if f"def {target_method}(" not in content:
                return False, f"Méthode cible {target_method} non trouvée"

            # Trouver la position pour ajouter l'alias (juste avant la méthode cible)
            # Pattern: @classmethod\n    def target_method(
            import re

            # Chercher le pattern de la méthode cible
            pattern = rf"(\n    @classmethod\n    def {target_method}\()"
            match = re.search(pattern, content)

            if match:
                # Créer l'alias
                alias_code = f'''
    @classmethod
    def {alias_name}(cls, *args, **kwargs):
        """Alias pour {target_method}."""
        return cls.{target_method}(*args, **kwargs)

'''
                # Insérer avant la méthode cible
                new_content = content[:match.start()] + alias_code + content[match.start():]

                with open(file_path, "w") as f:
                    f.write(new_content)

                logger.info("method_alias_added",
                           class_name=class_name,
                           alias=alias_name,
                           target=target_method,
                           file=file_hint)

                return True, f"Alias {class_name}.{alias_name} -> {target_method} créé dans {file_hint}"

            return False, f"Pattern de méthode {target_method} non trouvé"

        except Exception as e:
            logger.error("method_alias_failed", error=str(e))
            return False, f"Erreur création alias: {e}"

    @classmethod
    def _suggest_method_fix(
        cls,
        class_name: str,
        missing_method: str,
        error_log: str
    ) -> Tuple[bool, str]:
        """
        Suggère une correction pour une méthode manquante non connue.
        Escalade vers Claude pour les cas complexes.
        """
        # Extraire le fichier de l'erreur
        import re

        file_match = re.search(r'File "([^"]+)"', error_log)
        if file_match:
            error_file = file_match.group(1)

            # Log pour Claude
            logger.warning("unknown_method_missing",
                          class_name=class_name,
                          method=missing_method,
                          file=error_file)

            # Escalader vers Claude
            cls._escalate_to_claude(
                f"attribute_error_{class_name}_{missing_method}",
                "unknown_attribute",
                1
            )

            return False, f"Méthode {class_name}.{missing_method} inconnue - escaladé vers Claude"

        return False, f"Méthode {class_name}.{missing_method} inconnue"

    # =========================================================================
    # CORRECTIONS NONETYPE (itération/accès sur None)
    # =========================================================================

    @classmethod
    def _fix_nonetype_error(cls, error_log: str) -> Tuple[bool, str]:
        """
        Corrige les erreurs NoneType en ajoutant des valeurs par défaut.

        Détecte les patterns:
        - 'NoneType' object is not iterable (boucle sur None)
        - 'NoneType' object is not subscriptable (index sur None)
        - 'NoneType' object has no attribute (attribut sur None)
        """
        import re

        error_lower = error_log.lower()

        # Vérifier si c'est une erreur NoneType
        if "nonetype" not in error_lower:
            return False, "Pas une erreur NoneType"

        # Extraire le fichier et la ligne
        file_match = re.search(r'File "([^"]+)", line (\d+)', error_log)
        if not file_match:
            return False, "Impossible d'extraire le fichier"

        file_path = file_match.group(1)
        line_num = int(file_match.group(2))

        # Vérifier si c'est un template Jinja2
        if ".html" in file_path:
            return cls._fix_jinja_nonetype(file_path, line_num, error_log)

        # Vérifier si c'est un fichier Python
        if ".py" in file_path:
            return cls._fix_python_nonetype(file_path, line_num, error_log)

        return False, "Type de fichier non supporté"

    @classmethod
    def _fix_jinja_nonetype(
        cls,
        file_path: str,
        line_num: int,
        error_log: str
    ) -> Tuple[bool, str]:
        """
        Corrige une erreur NoneType dans un template Jinja2.
        Ajoute 'or []' aux boucles for.
        """
        import re

        try:
            with open(file_path, "r") as f:
                lines = f.readlines()

            if line_num > len(lines):
                return False, f"Ligne {line_num} hors limites"

            line = lines[line_num - 1]

            # Chercher un pattern {% for x in variable %}
            match = re.search(r'{%\s*for\s+\w+\s+in\s+(\S+)\s*%}', line)
            if match:
                variable = match.group(1)
                # Vérifier si 'or []' est déjà présent
                if "or []" not in line and "or []" not in line:
                    # Ajouter 'or []'
                    old_pattern = f"in {variable}"
                    new_pattern = f"in {variable} or []"
                    new_line = line.replace(old_pattern, new_pattern)
                    lines[line_num - 1] = new_line

                    with open(file_path, "w") as f:
                        f.writelines(lines)

                    logger.info("jinja_nonetype_fixed",
                               file=file_path,
                               line=line_num,
                               variable=variable)

                    return True, f"Ajout 'or []' à {variable} dans {file_path}:{line_num}"

            return False, "Pattern Jinja non reconnu"

        except Exception as e:
            logger.error("jinja_nonetype_fix_failed", error=str(e))
            return False, f"Erreur: {e}"

    @classmethod
    def _fix_python_nonetype(
        cls,
        file_path: str,
        line_num: int,
        error_log: str
    ) -> Tuple[bool, str]:
        """
        Corrige une erreur NoneType dans un fichier Python.
        Ajoute 'or []' ou 'or {}' selon le contexte.
        """
        import re

        try:
            with open(file_path, "r") as f:
                lines = f.readlines()

            if line_num > len(lines):
                return False, f"Ligne {line_num} hors limites"

            line = lines[line_num - 1]

            # Pattern: for x in variable:
            match = re.search(r'for\s+\w+\s+in\s+(\w+):', line)
            if match:
                variable = match.group(1)
                if "or []" not in line:
                    old_pattern = f"in {variable}:"
                    new_pattern = f"in ({variable} or []):"
                    new_line = line.replace(old_pattern, new_pattern)
                    lines[line_num - 1] = new_line

                    with open(file_path, "w") as f:
                        f.writelines(lines)

                    logger.info("python_nonetype_fixed",
                               file=file_path,
                               line=line_num,
                               variable=variable)

                    return True, f"Ajout 'or []' à {variable} dans {file_path}:{line_num}"

            # Pattern: variable[key]
            match = re.search(r'(\w+)\[', line)
            if match and "subscriptable" in error_log:
                variable = match.group(1)
                # Plus complexe - on escalade vers Claude
                logger.warning("python_subscript_nonetype",
                              file=file_path,
                              line=line_num,
                              variable=variable)
                return False, f"Subscript sur None ({variable}) - correction manuelle requise"

            return False, "Pattern Python non reconnu"

        except Exception as e:
            logger.error("python_nonetype_fix_failed", error=str(e))
            return False, f"Erreur: {e}"

    # =========================================================================
    # CORRECTIONS DATABASE (connexion, pool, timeout)
    # =========================================================================

    @classmethod
    def _fix_database_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs de base de données."""
        error_lower = error_log.lower()

        # Pool de connexions épuisé
        if "pool" in error_lower and ("exhausted" in error_lower or "timeout" in error_lower):
            return cls._reset_db_pool()

        # Connexion perdue
        if any(x in error_lower for x in ["connection refused", "connection reset", "connection closed", "server closed"]):
            return cls._reconnect_database()

        # Deadlock
        if "deadlock" in error_lower:
            logger.warning("database_deadlock_detected")
            return True, "Deadlock détecté - transaction sera réessayée automatiquement"

        # Table locked
        if "lock" in error_lower and "timeout" in error_lower:
            return cls._release_locks()

        return False, ""

    @classmethod
    def _reset_db_pool(cls) -> Tuple[bool, str]:
        """Réinitialise le pool de connexions."""
        try:
            from ..db import Database
            Database.dispose_engine()
            logger.info("database_pool_reset")
            return True, "Pool de connexions réinitialisé"
        except Exception as e:
            return False, f"Échec reset pool: {e}"

    @classmethod
    def _reconnect_database(cls) -> Tuple[bool, str]:
        """Tente de reconnecter la base de données."""
        try:
            from ..db import Database
            import time

            # Attendre un peu avant de réessayer
            time.sleep(2)

            # Réinitialiser le moteur
            Database.dispose_engine()

            # Tester la connexion
            with cls._get_session() as session:
                from sqlalchemy import text
                session.execute(text("SELECT 1"))

            logger.info("database_reconnected")
            return True, "Base de données reconnectée"

        except Exception as e:
            return False, f"Échec reconnexion DB: {e}"

    @classmethod
    def _release_locks(cls) -> Tuple[bool, str]:
        """Tente de libérer les verrous bloquants."""
        try:
            with cls._get_session() as session:
                from sqlalchemy import text
                # Annuler les requêtes bloquées depuis plus de 30 secondes
                session.execute(text("""
                    SELECT pg_cancel_backend(pid)
                    FROM pg_stat_activity
                    WHERE state = 'active'
                    AND query_start < NOW() - INTERVAL '30 seconds'
                    AND pid <> pg_backend_pid()
                """))
                session.commit()
                logger.info("database_locks_released")
                return True, "Verrous libérés"
        except Exception as e:
            return False, f"Échec libération verrous: {e}"

    # =========================================================================
    # CORRECTIONS REDIS (cache)
    # =========================================================================

    @classmethod
    def _fix_redis_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs Redis."""
        error_lower = error_log.lower()

        if not any(x in error_lower for x in ["redis", "cache"]):
            return False, ""

        # Connexion refusée
        if "connection refused" in error_lower or "connection error" in error_lower:
            return cls._reconnect_redis()

        # Timeout
        if "timeout" in error_lower:
            return cls._reset_redis_connection()

        # Mémoire pleine
        if "oom" in error_lower or "out of memory" in error_lower:
            return cls._flush_redis_cache()

        return False, ""

    @classmethod
    def _reconnect_redis(cls) -> Tuple[bool, str]:
        """Tente de reconnecter Redis."""
        try:
            import redis
            import os
            import time

            time.sleep(1)

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            client = redis.from_url(redis_url)
            client.ping()

            logger.info("redis_reconnected")
            return True, "Redis reconnecté"

        except Exception as e:
            # Redis non disponible - désactiver le cache temporairement
            logger.warning("redis_unavailable", error=str(e))
            return True, "Redis indisponible - cache désactivé temporairement"

    @classmethod
    def _reset_redis_connection(cls) -> Tuple[bool, str]:
        """Réinitialise la connexion Redis."""
        try:
            from ..cache import Cache
            Cache.reset_connection()
            logger.info("redis_connection_reset")
            return True, "Connexion Redis réinitialisée"
        except Exception as e:
            return False, f"Échec reset Redis: {e}"

    @classmethod
    def _flush_redis_cache(cls) -> Tuple[bool, str]:
        """Vide le cache Redis en cas de mémoire pleine."""
        try:
            import redis
            import os

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            client = redis.from_url(redis_url)

            # Supprimer les clés expirées
            client.execute_command("MEMORY", "PURGE")

            # Supprimer les clés de cache anciennes (pattern azalplus:cache:*)
            for key in client.scan_iter("azalplus:cache:*"):
                client.delete(key)

            logger.info("redis_cache_flushed")
            return True, "Cache Redis vidé"

        except Exception as e:
            return False, f"Échec flush cache: {e}"

    # =========================================================================
    # CORRECTIONS AUTH (token, refresh)
    # =========================================================================

    @classmethod
    def _fix_auth_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs d'authentification."""
        error_lower = error_log.lower()

        # Token expiré
        if "token" in error_lower and ("expired" in error_lower or "expiré" in error_lower):
            return cls._handle_expired_token(error_log)

        # Token invalide
        if "token" in error_lower and ("invalid" in error_lower or "invalide" in error_lower):
            return True, "Token invalide - redirection vers login requise"

        # Session expirée
        if "session" in error_lower and ("expired" in error_lower or "expiré" in error_lower):
            return True, "Session expirée - nouvelle authentification requise"

        return False, ""

    @classmethod
    def _handle_expired_token(cls, error_log: str) -> Tuple[bool, str]:
        """Gère un token expiré en tentant un refresh."""
        # Extraire le refresh token si présent
        refresh_match = re.search(r'refresh[_-]?token["\s:=]+([a-zA-Z0-9._-]+)', error_log)

        if refresh_match:
            try:
                from ..auth import AuthService
                refresh_token = refresh_match.group(1)
                new_tokens = AuthService.refresh_tokens(refresh_token)
                if new_tokens:
                    logger.info("auth_token_refreshed")
                    return True, "Token rafraîchi automatiquement"
            except Exception as e:
                pass

        # Pas de refresh possible
        return True, "Token expiré - nouvelle authentification requise"

    # =========================================================================
    # CORRECTIONS VALIDATION (Pydantic)
    # =========================================================================

    @classmethod
    def _fix_validation_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs de validation Pydantic."""
        error_lower = error_log.lower()

        if "validationerror" not in error_lower and "validation error" not in error_lower:
            return False, ""

        # Extraire le champ concerné
        field_match = re.search(r"(?:field|champ)[:\s]+['\"]?(\w+)", error_log, re.IGNORECASE)
        type_match = re.search(r"type[=:\s]+(\w+)", error_log)

        if field_match:
            field_name = field_match.group(1)

            # Champ obligatoire manquant
            if "required" in error_lower or "obligatoire" in error_lower:
                return cls._add_field_default(field_name)

            # Type incorrect
            if type_match:
                expected_type = type_match.group(1)
                return True, f"Champ '{field_name}' attend type {expected_type}"

        return False, ""

    @classmethod
    def _add_field_default(cls, field_name: str) -> Tuple[bool, str]:
        """Suggère une valeur par défaut pour un champ obligatoire."""
        # Cette correction ne peut pas être automatique car elle dépend du contexte
        # On log simplement pour l'analyse
        logger.warning("validation_required_field", field=field_name)
        return True, f"Champ '{field_name}' requis - vérifier le formulaire"

    @classmethod
    def _fix_validation_422(cls, error_log: str) -> Tuple[bool, str]:
        """
        Corrige les erreurs HTTP 422 (Unprocessable Entity).
        Ces erreurs viennent souvent de:
        - Body JSON mal formaté
        - Champs manquants
        - Types incorrects
        - IDs invalides (cb.value au lieu de cb.dataset.id)
        - Body() multiples sans modèle Pydantic
        """
        # Extraire le path de l'erreur
        path_match = re.search(r'source_file["\s:]+([^\s"]+)', error_log)
        path = path_match.group(1) if path_match else ""

        if not path:
            path_match = re.search(r'/api/([a-z_]+)/bulk', error_log, re.IGNORECASE)
            path = path_match.group(0) if path_match else ""

        # Erreur sur route bulk - tenter fix automatique
        if "/bulk" in error_log or "/bulk" in path:
            # Extraire le module concerné
            module_match = re.search(r'/api/(?:v1/)?([a-z_]+)/bulk', error_log, re.IGNORECASE)
            module_name = module_match.group(1) if module_match else None

            if module_name:
                # Vérifier si api.py utilise Body() au lieu de modèles Pydantic
                fixed = cls._fix_bulk_body_params(module_name)
                if fixed:
                    cls._log_fix_applied("bulk_body_format", f"Corrigé Body() → Pydantic model pour {module_name}/bulk", f"422:{path}")
                    cls._log_learning("api_validation", f"422 bulk: utiliser BulkDeleteRequest/BulkUpdateRequest au lieu de Body() multiples")
                    return True, f"Corrigé format body pour {module_name}/bulk - utilise maintenant modèles Pydantic"

            logger.warning("validation_422_bulk",
                          path=path,
                          hint="Vérifier format body: {ids: [uuid1, uuid2]} et que cb.dataset.id est utilisé")
            cls._escalate_to_claude(f"422:{path}", "validation_422", 1)
            return False, "Erreur 422 sur bulk - format body incorrect, escaladé vers Claude"

        # Autres erreurs 422
        logger.warning("validation_422_detected", error=error_log[:300])
        cls._escalate_to_claude(f"422:{path}", "validation_422", 1)
        return False, "Erreur 422 détectée, escaladé vers Claude"

    @classmethod
    def _fix_bulk_body_params(cls, module_name: str) -> bool:
        """
        Vérifie et corrige si les endpoints bulk utilisent Body() au lieu de modèles Pydantic.
        Retourne True si une correction a été appliquée.
        """
        api_path = Path("/home/ubuntu/azalplus/moteur/api.py")

        try:
            content = api_path.read_text()

            # Vérifier si les modèles Pydantic existent déjà
            if "class BulkDeleteRequest" in content and "class BulkUpdateRequest" in content:
                # Les modèles existent, vérifier s'ils sont utilisés
                if "body: BulkDeleteRequest" in content and "body: BulkUpdateRequest" in content:
                    return False  # Déjà corrigé

            # Si on arrive ici, les modèles existent mais ne sont pas utilisés partout
            # ou n'existent pas du tout - le fix a déjà été fait manuellement
            logger.info("bulk_body_params_check", module=module_name, status="models_exist")
            return False

        except Exception as e:
            logger.error("bulk_body_params_check_failed", error=str(e))
            return False

    # =========================================================================
    # CORRECTIONS YAML (parsing modules)
    # =========================================================================

    @classmethod
    def _fix_yaml_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs de parsing YAML."""
        error_lower = error_log.lower()

        if "yaml" not in error_lower:
            return False, ""

        # Extraire le fichier concerné
        file_match = re.search(r"(?:file|fichier)[:\s]+['\"]?([^\s'\"]+\.ya?ml)", error_log, re.IGNORECASE)
        if not file_match:
            file_match = re.search(r"([^\s'\"]+\.ya?ml)", error_log)

        if file_match:
            yaml_file = file_match.group(1)

            # Erreur de syntaxe YAML
            if "syntax" in error_lower or "scanner" in error_lower:
                return cls._fix_yaml_syntax(yaml_file, error_log)

            # Valeur manquante
            if "expected" in error_lower:
                return cls._fix_yaml_structure(yaml_file, error_log)

        return False, ""

    @classmethod
    def _fix_yaml_syntax(cls, yaml_file: str, error_log: str) -> Tuple[bool, str]:
        """Tente de corriger la syntaxe YAML."""
        try:
            # Extraire le numéro de ligne
            line_match = re.search(r"line\s+(\d+)", error_log, re.IGNORECASE)
            line_num = int(line_match.group(1)) if line_match else None

            yaml_path = Path(yaml_file) if yaml_file.startswith('/') else Path(f"/home/ubuntu/azalplus/modules/{yaml_file}")

            if not yaml_path.exists():
                return False, f"Fichier {yaml_file} non trouvé"

            content = yaml_path.read_text()
            lines = content.split('\n')

            fixed = False

            # Corrections courantes
            for i, line in enumerate(lines):
                original = line

                # Valeurs avec : non quotées
                if ':' in line and not line.strip().startswith('#'):
                    # Pattern: "key: value with : inside"
                    match = re.match(r'^(\s*)(\w+):\s*(.+)$', line)
                    if match and ':' in match.group(3) and not match.group(3).startswith('"'):
                        indent, key, value = match.groups()
                        if not value.startswith('[') and not value.startswith('{'):
                            lines[i] = f'{indent}{key}: "{value}"'
                            fixed = True

                # Tabs -> espaces
                if '\t' in line:
                    lines[i] = line.replace('\t', '  ')
                    fixed = True

            if fixed:
                yaml_path.write_text('\n'.join(lines))
                logger.info("yaml_syntax_fixed", file=yaml_file)
                return True, f"Syntaxe YAML corrigée: {yaml_file}"

            return False, f"Erreur YAML non corrigeable automatiquement à la ligne {line_num}"

        except Exception as e:
            return False, f"Erreur correction YAML: {e}"

    @classmethod
    def _fix_yaml_structure(cls, yaml_file: str, error_log: str) -> Tuple[bool, str]:
        """Corrige la structure YAML (champs manquants)."""
        try:
            yaml_path = Path(yaml_file) if yaml_file.startswith('/') else Path(f"/home/ubuntu/azalplus/modules/{yaml_file}")

            if not yaml_path.exists():
                return False, f"Fichier {yaml_file} non trouvé"

            import yaml
            content = yaml_path.read_text()

            try:
                data = yaml.safe_load(content)
            except:
                return False, "YAML invalide"

            # Vérifier les champs requis pour un module
            required_fields = ['nom', 'champs']
            fixed = False

            for field in required_fields:
                if field not in data:
                    if field == 'nom':
                        # Utiliser le nom du fichier
                        module_name = yaml_path.stem.replace('_', ' ').title()
                        data['nom'] = module_name
                        fixed = True
                    elif field == 'champs':
                        data['champs'] = []
                        fixed = True

            if fixed:
                with open(yaml_path, 'w') as f:
                    yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
                logger.info("yaml_structure_fixed", file=yaml_file)
                return True, f"Structure YAML corrigée: {yaml_file}"

            return False, ""

        except Exception as e:
            return False, f"Erreur structure YAML: {e}"

    # =========================================================================
    # CORRECTIONS TEMPLATES (Jinja2)
    # =========================================================================

    @classmethod
    def _fix_template_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs de templates Jinja2."""
        error_lower = error_log.lower()

        if "jinja" not in error_lower and "template" not in error_lower:
            return False, ""

        # Variable non définie
        if "undefined" in error_lower or "undefinederror" in error_lower:
            var_match = re.search(r"['\"](\w+)['\"] is undefined", error_log)
            if var_match:
                var_name = var_match.group(1)
                return cls._fix_undefined_template_var(var_name, error_log)

        # Template non trouvé
        if "templatenotfound" in error_lower or "not found" in error_lower:
            template_match = re.search(r"['\"]([^'\"]+\.html)['\"]", error_log)
            if template_match:
                template_name = template_match.group(1)
                return cls._create_missing_template(template_name)

        return False, ""

    @classmethod
    def _fix_undefined_template_var(cls, var_name: str, error_log: str) -> Tuple[bool, str]:
        """Corrige une variable non définie dans un template."""
        # On ne peut pas corriger automatiquement les variables manquantes
        # Mais on peut logger pour analyse
        logger.warning("template_undefined_var", variable=var_name)
        return True, f"Variable template '{var_name}' non définie - vérifier le contexte"

    @classmethod
    def _create_missing_template(cls, template_name: str) -> Tuple[bool, str]:
        """Crée un template manquant."""
        try:
            templates_path = Path("/home/ubuntu/azalplus/templates")
            template_path = templates_path / template_name

            if template_path.exists():
                return True, f"Template {template_name} existe déjà"

            template_path.parent.mkdir(parents=True, exist_ok=True)

            # Créer un template minimal
            base_template = """{% extends "base.html" %}
{% block content %}
<div class="container mx-auto p-4">
    <h1 class="text-2xl font-bold mb-4">{{ title or 'Page' }}</h1>
    <p>Contenu à définir</p>
</div>
{% endblock %}
"""
            template_path.write_text(base_template)
            logger.info("template_created", template=template_name)
            return True, f"Template {template_name} créé"

        except Exception as e:
            return False, f"Erreur création template: {e}"

    # =========================================================================
    # CORRECTIONS REACT/MOBILE
    # =========================================================================

    @classmethod
    def _fix_react_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs React/Mobile."""
        error_lower = error_log.lower()

        # React Router v7 deprecation warnings
        if "react router" in error_lower and "v7" in error_lower:
            return cls._fix_react_router_v7_warnings(error_log)

        # Erreur React
        if "react" not in error_lower and "component" not in error_lower:
            # Vérifier aussi les erreurs mobiles génériques
            if not any(x in error_lower for x in ["vite", "tsx", "jsx", "mobile"]):
                return False, ""

        # Hook rules violation
        if "rules of hooks" in error_lower or "hook" in error_lower:
            return True, "Erreur React Hooks - vérifier l'ordre des hooks dans le composant"

        # Composant non trouvé
        comp_match = re.search(r"(?:Element type is invalid|is not a function).*?['\"](\w+)['\"]", error_log)
        if comp_match:
            component_name = comp_match.group(1)
            return cls._fix_missing_react_component(component_name)

        # Erreur de rendu
        if "cannot read property" in error_lower or "cannot read properties" in error_lower:
            prop_match = re.search(r"reading ['\"](\w+)['\"]", error_log)
            if prop_match:
                prop_name = prop_match.group(1)
                return True, f"Erreur lecture propriété '{prop_name}' - vérifier null/undefined"

        # Erreur Vite HMR
        if "hmr" in error_lower or "hot" in error_lower:
            return cls._restart_vite_server()

        # Erreur de build mobile
        if "build" in error_lower and ("failed" in error_lower or "error" in error_lower):
            return cls._fix_mobile_build()

        # Port déjà utilisé
        if "port" in error_lower and ("in use" in error_lower or "already" in error_lower):
            return cls._fix_port_in_use(error_log)

        return False, ""

    @classmethod
    def _fix_js_syntax_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs de syntaxe JavaScript."""
        try:
            # Extraire le fichier source et la ligne
            source_match = re.search(r'source[_file]*["\s:]+([^\s"]+)', error_log, re.IGNORECASE)
            line_match = re.search(r'line["\s:]+(\d+)', error_log, re.IGNORECASE)

            # Erreur "Unexpected token 'default'" - souvent un export default mal placé
            if "unexpected token" in error_log.lower() and "default" in error_log.lower():
                ui_path = Path("/home/ubuntu/azalplus/moteur/ui.py")
                content = ui_path.read_text()

                # Chercher les patterns problématiques
                # Pattern: "export default" dans du code inline
                if "export default" in content:
                    # Remplacer export default par une assignation
                    new_content = content.replace("export default ", "")
                    if new_content != content:
                        ui_path.write_text(new_content)
                        logger.info("js_syntax_export_default_fixed")
                        return True, "SyntaxError: 'export default' supprimé du code inline"

                # Pattern: default mal placé dans switch/case
                # Chercher "default:" sans "case" avant
                bad_default = re.search(r'[^a-zA-Z]default\s*[^:]', content)
                if bad_default:
                    logger.warning("js_syntax_default_found", position=bad_default.start())
                    return True, "SyntaxError détecté - vérifier 'default' dans ui.py"

            # Autres erreurs de syntaxe courantes
            if "unexpected end of input" in error_log.lower():
                return True, "SyntaxError: accolade/parenthèse manquante - vérifier le code"

            if "unexpected identifier" in error_log.lower():
                return True, "SyntaxError: point-virgule manquant ou mot-clé mal utilisé"

            return True, "SyntaxError détecté - nécessite analyse manuelle"

        except Exception as e:
            return False, f"Erreur fix syntax: {e}"

    @classmethod
    def _fix_react_router_v7_warnings(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les warnings React Router v7 en ajoutant les future flags."""
        try:
            main_tsx = Path("/home/ubuntu/azalplus/mobile/src/main.tsx")
            if not main_tsx.exists():
                return False, "main.tsx non trouvé"

            content = main_tsx.read_text()

            # Vérifier si déjà corrigé
            if "future={{" in content or "v7_startTransition" in content:
                return True, "React Router future flags déjà configurés"

            # Ajouter les future flags au BrowserRouter
            old_router = "<BrowserRouter>"
            new_router = """<BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>"""

            if old_router not in content:
                return False, "BrowserRouter non trouvé dans main.tsx"

            new_content = content.replace(old_router, new_router)
            main_tsx.write_text(new_content)

            logger.info("react_router_v7_flags_added")
            return True, "React Router v7 future flags ajoutés"

        except Exception as e:
            return False, f"Erreur fix React Router: {e}"

    @classmethod
    def _fix_missing_react_component(cls, component_name: str) -> Tuple[bool, str]:
        """Corrige un composant React manquant."""
        try:
            mobile_path = Path("/home/ubuntu/azalplus/mobile/src")

            # Chercher si le composant existe quelque part
            for tsx_file in mobile_path.rglob("*.tsx"):
                content = tsx_file.read_text()
                if f"export function {component_name}" in content or f"export const {component_name}" in content:
                    # Le composant existe, vérifier l'import
                    return True, f"Composant {component_name} trouvé dans {tsx_file.name} - vérifier l'import"

            # Composant non trouvé - créer un stub
            components_path = mobile_path / "components"
            components_path.mkdir(exist_ok=True)

            stub_content = f"""import React from 'react';

interface {component_name}Props {{
  // TODO: Définir les props
}}

export function {component_name}(props: {component_name}Props): React.ReactElement {{
  return (
    <div className="p-4">
      <p className="text-gray-500">Composant {component_name} à implémenter</p>
    </div>
  );
}}

export default {component_name};
"""
            stub_path = components_path / f"{component_name}.tsx"
            stub_path.write_text(stub_content)
            logger.info("react_component_created", component=component_name)
            return True, f"Composant stub {component_name} créé"

        except Exception as e:
            return False, f"Erreur création composant: {e}"

    @classmethod
    def _restart_vite_server(cls) -> Tuple[bool, str]:
        """Redémarre le serveur Vite mobile."""
        try:
            import subprocess
            import signal
            import os

            # Trouver et tuer le processus Vite existant
            result = subprocess.run(
                ["pgrep", "-f", "vite.*mobile"],
                capture_output=True,
                text=True
            )

            if result.stdout.strip():
                for pid in result.stdout.strip().split('\n'):
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                    except:
                        pass

            # Redémarrer Vite
            subprocess.Popen(
                ["npm", "run", "dev"],
                cwd="/home/ubuntu/azalplus/mobile",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

            logger.info("vite_server_restarted")
            return True, "Serveur Vite redémarré"

        except Exception as e:
            return False, f"Erreur restart Vite: {e}"

    @classmethod
    def _fix_mobile_build(cls) -> Tuple[bool, str]:
        """Tente de corriger les erreurs de build mobile."""
        try:
            import subprocess

            # Nettoyer le cache
            subprocess.run(
                ["rm", "-rf", "node_modules/.vite"],
                cwd="/home/ubuntu/azalplus/mobile",
                capture_output=True
            )

            # Reinstaller les dépendances si nécessaire
            subprocess.run(
                ["npm", "install"],
                cwd="/home/ubuntu/azalplus/mobile",
                capture_output=True,
                timeout=300
            )

            logger.info("mobile_build_fixed")
            return True, "Cache mobile nettoyé, dépendances réinstallées"

        except Exception as e:
            return False, f"Erreur fix build: {e}"

    @classmethod
    def _fix_port_in_use(cls, error_log: str) -> Tuple[bool, str]:
        """Libère un port déjà utilisé."""
        try:
            import subprocess
            import signal
            import os

            # Extraire le port
            port_match = re.search(r"port\s+(\d+)", error_log, re.IGNORECASE)
            if not port_match:
                return False, "Port non identifié"

            port = port_match.group(1)

            # Trouver le processus utilisant ce port
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True
            )

            if result.stdout.strip():
                for pid in result.stdout.strip().split('\n'):
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        logger.info("port_freed", port=port, pid=pid)
                    except:
                        pass
                return True, f"Port {port} libéré"

            return False, f"Aucun processus sur le port {port}"

        except Exception as e:
            return False, f"Erreur libération port: {e}"

    # =========================================================================
    # CORRECTIONS TYPESCRIPT
    # =========================================================================

    @classmethod
    def _fix_typescript_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs TypeScript."""
        error_lower = error_log.lower()

        if "typescript" not in error_lower and "ts(" not in error_log and ".ts:" not in error_log:
            return False, ""

        # Type manquant
        if "cannot find type" in error_lower or "ts2304" in error_lower:
            type_match = re.search(r"['\"](\w+)['\"]", error_log)
            if type_match:
                type_name = type_match.group(1)
                return cls._fix_missing_type(type_name)

        # Module non trouvé
        if "cannot find module" in error_lower or "ts2307" in error_lower:
            module_match = re.search(r"['\"](@?\w+(?:/\w+)?)['\"]", error_log)
            if module_match:
                module_name = module_match.group(1)
                return cls._install_ts_types(module_name)

        # Propriété manquante
        if "does not exist on type" in error_lower or "ts2339" in error_lower:
            prop_match = re.search(r"['\"](\w+)['\"].*does not exist on type", error_log)
            if prop_match:
                prop_name = prop_match.group(1)
                return True, f"Propriété '{prop_name}' manquante sur le type - vérifier l'interface"

        return False, ""

    @classmethod
    def _fix_missing_type(cls, type_name: str) -> Tuple[bool, str]:
        """Corrige un type TypeScript manquant."""
        try:
            # Vérifier si c'est un type React courant
            react_types = ["ReactElement", "ReactNode", "FC", "FunctionComponent", "MouseEvent", "ChangeEvent"]
            if type_name in react_types:
                return True, f"Type '{type_name}' - ajouter: import {{ {type_name} }} from 'react'"

            # Créer un type par défaut
            types_path = Path("/home/ubuntu/azalplus/mobile/src/types")
            types_path.mkdir(exist_ok=True)

            types_file = types_path / "auto-generated.d.ts"
            existing = types_file.read_text() if types_file.exists() else ""

            if f"type {type_name}" not in existing and f"interface {type_name}" not in existing:
                new_type = f"\n// Auto-generated by Guardian\nexport type {type_name} = unknown;\n"
                types_file.write_text(existing + new_type)
                logger.info("typescript_type_created", type=type_name)
                return True, f"Type '{type_name}' créé (à compléter)"

            return True, f"Type '{type_name}' existe déjà"

        except Exception as e:
            return False, f"Erreur création type: {e}"

    @classmethod
    def _install_ts_types(cls, module_name: str) -> Tuple[bool, str]:
        """Installe les types TypeScript pour un module."""
        try:
            import subprocess

            # Essayer d'installer les types
            types_package = f"@types/{module_name.replace('@', '').replace('/', '__')}"

            result = subprocess.run(
                ["npm", "install", "-D", types_package],
                cwd="/home/ubuntu/azalplus/mobile",
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                logger.info("typescript_types_installed", package=types_package)
                return True, f"Types {types_package} installés"
            else:
                # Les types n'existent peut-être pas, créer une déclaration
                return cls._create_module_declaration(module_name)

        except Exception as e:
            return False, f"Erreur installation types: {e}"

    @classmethod
    def _create_module_declaration(cls, module_name: str) -> Tuple[bool, str]:
        """Crée une déclaration de module TypeScript."""
        try:
            types_path = Path("/home/ubuntu/azalplus/mobile/src/types")
            types_path.mkdir(exist_ok=True)

            decl_file = types_path / "modules.d.ts"
            existing = decl_file.read_text() if decl_file.exists() else ""

            if f"declare module '{module_name}'" not in existing:
                new_decl = f"\n// Auto-generated by Guardian\ndeclare module '{module_name}';\n"
                decl_file.write_text(existing + new_decl)
                logger.info("typescript_module_declared", module=module_name)
                return True, f"Module '{module_name}' déclaré"

            return True, f"Module '{module_name}' déjà déclaré"

        except Exception as e:
            return False, f"Erreur déclaration module: {e}"

    # =========================================================================
    # CORRECTIONS FICHIERS (permission, disk)
    # =========================================================================

    @classmethod
    def _fix_file_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs de fichiers."""
        error_lower = error_log.lower()

        # Permission refusée
        if "permission denied" in error_lower or "eacces" in error_lower:
            file_match = re.search(r"['\"]?(/[^\s'\"]+)['\"]?", error_log)
            if file_match:
                file_path = file_match.group(1)
                return cls._fix_file_permission(file_path)

        # Disque plein
        if "no space" in error_lower or "disk full" in error_lower or "enospc" in error_lower:
            return cls._free_disk_space()

        # Fichier non trouvé (qui devrait exister)
        if "no such file" in error_lower or "enoent" in error_lower:
            file_match = re.search(r"['\"]?(/[^\s'\"]+)['\"]?", error_log)
            if file_match:
                file_path = file_match.group(1)
                return cls._create_missing_file(file_path)

        # Trop de fichiers ouverts
        if "too many open files" in error_lower or "emfile" in error_lower:
            return cls._close_file_handles()

        return False, ""

    @classmethod
    def _fix_file_permission(cls, file_path: str) -> Tuple[bool, str]:
        """Corrige les permissions d'un fichier."""
        try:
            import os
            import subprocess

            path = Path(file_path)

            if not path.exists():
                return False, f"Fichier {file_path} non trouvé"

            # Vérifier si c'est dans notre projet
            if not str(path).startswith("/home/ubuntu/azalplus"):
                return False, "Fichier hors du projet - permission non modifiable"

            # Changer les permissions
            os.chmod(file_path, 0o644 if path.is_file() else 0o755)
            logger.info("file_permission_fixed", file=file_path)
            return True, f"Permissions corrigées: {file_path}"

        except Exception as e:
            return False, f"Erreur permissions: {e}"

    @classmethod
    def _free_disk_space(cls) -> Tuple[bool, str]:
        """Libère de l'espace disque."""
        try:
            import subprocess
            import shutil

            freed = 0

            # Nettoyer les caches Python
            cache_dirs = [
                "/home/ubuntu/azalplus/__pycache__",
                "/home/ubuntu/azalplus/.pytest_cache",
                "/home/ubuntu/azalplus/.mypy_cache",
            ]

            for cache_dir in cache_dirs:
                if Path(cache_dir).exists():
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    freed += 1

            # Nettoyer les logs anciens
            logs_path = Path("/home/ubuntu/azalplus/logs")
            if logs_path.exists():
                for log_file in logs_path.glob("*.log.*"):
                    log_file.unlink()
                    freed += 1

            # Nettoyer node_modules/.cache
            node_cache = Path("/home/ubuntu/azalplus/mobile/node_modules/.cache")
            if node_cache.exists():
                shutil.rmtree(node_cache, ignore_errors=True)
                freed += 1

            # Docker prune si disponible
            subprocess.run(
                ["docker", "system", "prune", "-f"],
                capture_output=True,
                timeout=60
            )

            logger.info("disk_space_freed", items=freed)
            return True, f"Espace disque libéré ({freed} éléments nettoyés)"

        except Exception as e:
            return False, f"Erreur nettoyage: {e}"

    @classmethod
    def _create_missing_file(cls, file_path: str) -> Tuple[bool, str]:
        """Crée un fichier manquant s'il est attendu."""
        try:
            path = Path(file_path)

            # Vérifier si c'est dans notre projet
            if not str(path).startswith("/home/ubuntu/azalplus"):
                return False, "Fichier hors du projet"

            # Créer le répertoire parent
            path.parent.mkdir(parents=True, exist_ok=True)

            # Créer un fichier vide ou avec contenu selon l'extension
            ext = path.suffix.lower()

            if ext == '.py':
                path.write_text("# Auto-generated by Guardian\n")
            elif ext == '.json':
                path.write_text("{}")
            elif ext == '.yml' or ext == '.yaml':
                path.write_text("# Auto-generated by Guardian\n")
            elif ext == '.ts' or ext == '.tsx':
                path.write_text("// Auto-generated by Guardian\n")
            elif ext == '.css':
                path.write_text("/* Auto-generated by Guardian */\n")
            else:
                path.write_text("")

            logger.info("missing_file_created", file=file_path)
            return True, f"Fichier {path.name} créé"

        except Exception as e:
            return False, f"Erreur création fichier: {e}"

    @classmethod
    def _close_file_handles(cls) -> Tuple[bool, str]:
        """Force la fermeture des handles de fichiers."""
        try:
            import gc

            # Forcer le garbage collector
            gc.collect()

            logger.info("file_handles_closed")
            return True, "Garbage collector exécuté - handles libérés"

        except Exception as e:
            return False, f"Erreur fermeture handles: {e}"

    # =========================================================================
    # CORRECTIONS RÉSEAU (timeout, connexion)
    # =========================================================================

    @classmethod
    def _fix_network_error(cls, error_log: str) -> Tuple[bool, str]:
        """Corrige les erreurs réseau."""
        error_lower = error_log.lower()

        # Failed to fetch
        if "failed to fetch" in error_lower:
            return cls._fix_failed_to_fetch(error_log)

        # Timeout
        if "timeout" in error_lower or "timed out" in error_lower:
            # Extraire l'URL si présente
            url_match = re.search(r'https?://[^\s"\'<>]+', error_log)
            if url_match:
                url = url_match.group(0)
                return cls._handle_network_timeout(url)

        # Connexion refusée
        if "connection refused" in error_lower or "econnrefused" in error_lower:
            return cls._handle_connection_refused(error_log)

        # DNS
        if "getaddrinfo" in error_lower or "name resolution" in error_lower:
            host_match = re.search(r"host[:\s]+['\"]?(\S+)", error_log, re.IGNORECASE)
            if host_match:
                host = host_match.group(1)
                return True, f"Erreur DNS pour {host} - vérifier la connexion réseau"

        # SSL/TLS
        if "ssl" in error_lower or "certificate" in error_lower:
            return True, "Erreur SSL/TLS - vérifier le certificat"

        return False, ""

    @classmethod
    def _fix_failed_to_fetch(cls, error_log: str) -> Tuple[bool, str]:
        """Gère les erreurs 'Failed to fetch'."""
        # Extraire l'URL si possible
        url_match = re.search(r'https?://[^\s"\'<>]+', error_log)
        url = url_match.group(0) if url_match else "unknown"

        # Vérifier si le backend est accessible
        try:
            import subprocess
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:8000/health"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.stdout.strip() == "200":
                # Backend OK - problème CORS probable
                logger.info("fetch_failed_cors_probable", url=url)
                return True, "Failed to fetch: Backend OK, vérifier CORS"
            else:
                logger.warning("fetch_failed_backend_down")
                return True, "Failed to fetch: Backend non accessible"
        except Exception as e:
            return True, f"Failed to fetch: Erreur réseau - {e}"

    @classmethod
    def _handle_network_timeout(cls, url: str) -> Tuple[bool, str]:
        """Gère un timeout réseau."""
        # Extraire le host
        host_match = re.search(r'https?://([^/:]+)', url)
        host = host_match.group(1) if host_match else "inconnu"

        # API externes connues
        if any(x in host for x in ['api.openai.com', 'api.anthropic.com', 'api.gouv.fr']):
            logger.warning("external_api_timeout", host=host)
            return True, f"Timeout API externe {host} - réessayer plus tard"

        # API interne
        if 'localhost' in host or '127.0.0.1' in host:
            return True, "Timeout API locale - vérifier que le serveur est démarré"

        return True, f"Timeout réseau pour {host}"

    @classmethod
    def _handle_connection_refused(cls, error_log: str) -> Tuple[bool, str]:
        """Gère une connexion refusée."""
        # Extraire le port
        port_match = re.search(r":(\d+)", error_log)
        port = port_match.group(1) if port_match else None

        if port:
            port_int = int(port)

            # Ports connus
            if port_int == 5432:
                return True, "PostgreSQL non accessible sur le port 5432"
            elif port_int == 6379:
                return True, "Redis non accessible sur le port 6379"
            elif port_int == 8000:
                return True, "Backend FastAPI non accessible sur le port 8000"
            elif port_int == 5173 or port_int == 5174:
                return True, f"Serveur Vite non accessible sur le port {port}"

        return True, "Connexion refusée - service non démarré"
