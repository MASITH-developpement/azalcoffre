#!/usr/bin/env python3
# =============================================================================
# AUTOPILOT - Claude Agent: Superviseur des corrections Guardian
# =============================================================================
"""
Claude Agent: Supervise et valide les corrections proposées par Guardian/AutoPilot.

Flux:
1. Guardian détecte une erreur et propose un fix
2. Claude Agent valide ou rejette la proposition
3. Si validé → Guardian applique le fix et APPREND le pattern
4. Si rejeté → Guardian APPREND à ne pas refaire cette erreur

L'apprentissage est central: Guardian devient plus intelligent avec le temps.

Usage:
    python -m moteur.autopilot.claude_agent
"""

import asyncio
import os
import sys
import json
import structlog
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

# Ajouter le chemin du projet
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = structlog.get_logger()

# Configuration
CHECK_INTERVAL = 15  # Vérifier toutes les 15 secondes
CLAUDE_MODEL = "claude-sonnet-4-20250514"


class ClaudeAgent:
    """
    Agent superviseur qui valide les corrections de Guardian.

    Guardian propose → Claude valide → Guardian apprend
    """

    def __init__(self):
        self.client = None
        self.storage = None
        self.running = False
        self.stats = {"validated": 0, "rejected": 0, "applied": 0}

    async def initialize(self):
        """Initialise l'agent."""
        # Charger la clé API
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            env_file = Path(__file__).parent.parent.parent / ".env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"\'')
                        break

        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY non configuré")

        # Initialiser le client Anthropic
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)

        # Initialiser DB et storage
        from moteur.db import Database
        from moteur.autopilot import PostgresStorage
        from moteur.autopilot.auto_fixer import AutoFixer

        await Database.connect()
        self.storage = PostgresStorage()
        self.storage.set_session_factory(Database.get_session)
        AutoFixer.initialize(Database.get_session)

        print("\n" + "="*60, flush=True)
        print("🤖 CLAUDE AGENT - Superviseur Guardian", flush=True)
        print("="*60, flush=True)
        print(f"📡 Surveillance toutes les {CHECK_INTERVAL}s", flush=True)
        print(f"🧠 Modèle: {CLAUDE_MODEL}", flush=True)
        print("🎯 Rôle: Valider les corrections de Guardian", flush=True)
        print("="*60 + "\n", flush=True)

        logger.info("claude_agent_initialized")

    async def start(self):
        """Démarre la surveillance."""
        self.running = True
        logger.info("claude_agent_started", interval=CHECK_INTERVAL)

        while self.running:
            try:
                await self._process_proposals()
            except Exception as e:
                logger.error("claude_agent_error", error=str(e))
                print(f"❌ Erreur: {e}", flush=True)

            await asyncio.sleep(CHECK_INTERVAL)

    async def stop(self):
        """Arrête l'agent."""
        self.running = False
        from moteur.db import Database
        await Database.disconnect()
        print(f"\n📊 Stats: {self.stats}", flush=True)
        logger.info("claude_agent_stopped", stats=self.stats)

    async def _process_proposals(self):
        """Traite les propositions Guardian en attente."""
        proposals = self.storage.get_pending_proposals()

        if not proposals:
            return

        print(f"\n📋 {len(proposals)} proposition(s) à traiter", flush=True)

        for proposal in proposals:
            print(f"\n{'─'*50}", flush=True)
            print(f"🔍 {proposal.error_type} (confiance: {proposal.confidence*100:.0f}%)", flush=True)

            # Demander à Claude de valider
            decision = await self._ask_claude_to_validate(proposal)

            if decision["approved"]:
                # Appliquer le fix
                success, message = await self._apply_fix(proposal, decision)

                if success:
                    self.stats["applied"] += 1
                    print(f"✅ Appliqué: {message}", flush=True)

                    # APPRENTISSAGE: Guardian retient ce pattern
                    self._learn_success(proposal, decision)
                else:
                    print(f"⚠️ Échec application: {message}", flush=True)

                self.stats["validated"] += 1
            else:
                # Rejeté mais Claude peut avoir fourni un meilleur fix
                fix_override = decision.get("fix_override")

                if fix_override and fix_override != "null":
                    # Claude a proposé un fix - l'appliquer
                    print(f"🔄 Rejeté mais Claude propose: {fix_override[:60]}...", flush=True)
                    success, message = await self._execute_sql(fix_override)

                    if success:
                        self.stats["applied"] += 1
                        print(f"✅ Fix Claude appliqué: {message}", flush=True)
                        # Apprendre le succès avec le fix de Claude
                        decision["fix_override"] = fix_override
                        self._learn_success(proposal, decision)
                    else:
                        print(f"⚠️ Échec fix Claude: {message}", flush=True)
                        self._learn_rejection(proposal, decision)
                else:
                    # Pas de fix proposé
                    self.stats["rejected"] += 1
                    print(f"❌ Rejeté: {decision.get('reason', 'Pas de raison')}", flush=True)
                    self._learn_rejection(proposal, decision)

            # Mettre à jour le status
            from moteur.autopilot.models import FixStatus
            new_status = FixStatus.APPLIED if decision["approved"] else FixStatus.REJECTED
            self.storage.update_proposal_status(proposal.id, new_status)

    async def _ask_claude_to_validate(self, proposal) -> Dict[str, Any]:
        """
        Demande à Claude de valider une proposition Guardian.

        Returns:
            {"approved": bool, "reason": str, "fix_override": str|None}
        """
        prompt = f"""Tu supervises Guardian, le système d'auto-correction d'AZALPLUS (ERP Python/FastAPI/PostgreSQL).

Guardian a détecté cette erreur et propose un fix. Valide ou rejette.

═══════════════════════════════════════════════════════════════
ERREUR DÉTECTÉE PAR GUARDIAN
═══════════════════════════════════════════════════════════════
Type: {proposal.error_type}
Confiance Guardian: {proposal.confidence*100:.0f}%
Fichier: {proposal.file_path or 'N/A'}

Message d'erreur:
{proposal.error_message[:800] if proposal.error_message else 'N/A'}

Fix proposé par Guardian:
{proposal.proposed_fix or 'Aucun fix proposé'}
═══════════════════════════════════════════════════════════════

DÉCISION REQUISE:
1. Si le fix Guardian est correct (confiance >= 80%) → approved: true
2. Si le fix est incorrect MAIS tu peux corriger → approved: true + fix_override
3. Si impossible à corriger → approved: false, fix_override: null

TYPES DE FIX SUPPORTÉS:

1. ERREURS SQL (base de données):
   - NOT NULL violation → ALTER TABLE azalplus.TABLE ALTER COLUMN COL SET DEFAULT 'valeur'
   - Colonne manquante → ALTER TABLE azalplus.TABLE ADD COLUMN COL TYPE

2. ERREURS JAVASCRIPT (frontend ui.py):
   - ReferenceError: X is not defined → CODE_JS_ADD:X
     function X(...) {{ ... }}

3. ERREURS FICHIER (création/modification):
   - Route manquante, page manquante, endpoint manquant → FILE_EDIT:chemin/fichier.ext
     <<<SEARCH
     code existant à trouver
     ===
     code de remplacement
     >>>

4. ERREURS CONFIG (CORS, CSRF, permissions):
   - CORS bloqué → FILE_EDIT:/home/ubuntu/azalplus/moteur/core.py ou csrf.py
   - Route exemption → Ajouter au tableau des exemptions

ARCHITECTURE AZALPLUS:
- Backend: /home/ubuntu/azalplus/moteur/ (Python FastAPI)
- Mobile: /home/ubuntu/azalplus/mobile/src/ (React TypeScript)
- Modules: /home/ubuntu/azalplus/modules/ (YAML)

IMPORTANT:
- Tu peux corriger N'IMPORTE QUELLE erreur en proposant FILE_EDIT
- Si confiance >= 80% et fix cohérent → approuve
- Fournis TOUJOURS un fix_override quand tu peux corriger

Réponds en JSON strict:
{{"approved": true/false, "reason": "explication courte", "fix_override": "ALTER TABLE... ou CODE_JS_ADD:... ou FILE_EDIT:... ou null"}}"""

        try:
            response = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1500,
                system="Tu es un superviseur technique expert. Réponds uniquement en JSON valide.",
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text

            # Parser le JSON
            import re
            json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return json.loads(response_text)

        except json.JSONDecodeError:
            # Si pas de JSON valide, rejeter par sécurité
            return {"approved": False, "reason": "Réponse Claude non parsable"}
        except Exception as e:
            logger.error("claude_validation_error", error=str(e))
            return {"approved": False, "reason": f"Erreur API: {e}"}

    async def _apply_fix(self, proposal, decision: Dict) -> Tuple[bool, str]:
        """Applique le fix validé par Claude."""
        # Utiliser le fix override de Claude si fourni
        fix_to_apply = decision.get("fix_override") or proposal.proposed_fix

        if not fix_to_apply:
            # Pas de fix explicite, essayer AutoFixer
            from moteur.autopilot.auto_fixer import AutoFixer
            return AutoFixer.try_fix(proposal.error_message or "")

        # Fix JavaScript - ajouter fonction dans ui.py
        if fix_to_apply.startswith("CODE_JS_ADD:"):
            return await self._apply_js_fix(fix_to_apply)

        # Fix fichier - modifier n'importe quel fichier
        if fix_to_apply.startswith("FILE_EDIT:"):
            return await self._apply_file_edit(fix_to_apply)

        # Appliquer le fix SQL
        if any(kw in fix_to_apply.upper() for kw in ["ALTER", "CREATE", "UPDATE", "INSERT"]):
            return await self._execute_sql(fix_to_apply)

        return False, "Type de fix non supporté"

    async def _apply_file_edit(self, fix: str) -> Tuple[bool, str]:
        """Applique une modification de fichier."""
        try:
            # Parser le fix: FILE_EDIT:path\n<<<SEARCH\nold\n===\nnew\n>>>
            lines = fix.split("\n", 1)
            header = lines[0]  # FILE_EDIT:/path/to/file.ext
            file_path = header.replace("FILE_EDIT:", "").strip()
            edit_content = lines[1] if len(lines) > 1 else ""

            if not edit_content or not file_path:
                return False, "Contenu de modification vide"

            path = Path(file_path)
            if not path.exists():
                # Créer le fichier si c'est une création
                if "<<<SEARCH" not in edit_content:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(edit_content)
                    logger.info("guardian_file_created", path=file_path)
                    return True, f"Fichier créé: {path.name}"
                return False, f"Fichier non trouvé: {file_path}"

            content = path.read_text()

            # Parser SEARCH/REPLACE
            if "<<<SEARCH" in edit_content and "===" in edit_content and ">>>" in edit_content:
                import re
                match = re.search(r'<<<SEARCH\n(.*?)\n===\n(.*?)\n>>>', edit_content, re.DOTALL)
                if match:
                    search = match.group(1)
                    replace = match.group(2)
                    if search in content:
                        new_content = content.replace(search, replace, 1)
                        path.write_text(new_content)
                        logger.info("guardian_file_edited", path=file_path)
                        return True, f"Modifié: {path.name}"
                    return False, "Pattern non trouvé dans le fichier"
            else:
                # Append mode
                content += "\n" + edit_content
                path.write_text(content)
                logger.info("guardian_file_appended", path=file_path)
                return True, f"Ajouté à: {path.name}"

        except Exception as e:
            logger.error("file_edit_error", error=str(e))
            return False, f"Erreur: {e}"

    async def _apply_js_fix(self, fix: str) -> Tuple[bool, str]:
        """Applique un fix JavaScript dans ui.py."""
        try:
            # Parser le fix: CODE_JS_ADD:func_name\ncode...
            lines = fix.split("\n", 1)
            header = lines[0]  # CODE_JS_ADD:handleRowClick
            func_name = header.replace("CODE_JS_ADD:", "").strip()
            js_code = lines[1] if len(lines) > 1 else ""

            if not js_code:
                return False, "Code JS vide"

            # Lire ui.py
            ui_path = Path("/home/ubuntu/azalplus/moteur/ui.py")
            content = ui_path.read_text()

            # Vérifier si la fonction existe déjà
            if f"function {func_name}" in content:
                return True, f"Fonction {func_name} existe déjà"

            # Chercher le bloc <script> principal pour y insérer le code
            # On cherche le pattern: </script> à la fin du HTML généré
            # et on insère avant

            # Chercher le marker d'insertion (fin du bloc script commun)
            insert_marker = "// === FIN FONCTIONS COMMUNES ==="

            if insert_marker in content:
                # Insérer après le marker
                content = content.replace(
                    insert_marker,
                    f"{insert_marker}\n\n        {js_code.replace(chr(10), chr(10) + '        ')}"
                )
            else:
                # Chercher la dernière occurrence de </script> dans le template
                # et insérer le code JS juste avant
                script_end = "    </script>"
                if script_end in content:
                    # Ajouter le marker et le code
                    new_code = f'''
        // === FIN FONCTIONS COMMUNES ===

        {js_code.replace(chr(10), chr(10) + '        ')}

    </script>'''
                    # Remplacer seulement la première occurrence de </script>
                    # dans le bon contexte (après les fonctions JS)
                    # On cherche un endroit approprié
                    pass  # TODO: logique plus complexe

                # Fallback: écrire dans un fichier JS séparé
                js_path = Path("/home/ubuntu/azalplus/assets/js/guardian_fixes.js")
                js_path.parent.mkdir(parents=True, exist_ok=True)

                existing = js_path.read_text() if js_path.exists() else "// Guardian Auto-Generated Functions\n"
                if f"function {func_name}" not in existing:
                    js_path.write_text(existing + f"\n\n{js_code}")
                    logger.info("guardian_js_fix_applied", function=func_name, file=str(js_path))
                    return True, f"JS: {func_name} ajouté dans guardian_fixes.js"

            ui_path.write_text(content)
            logger.info("guardian_js_fix_applied", function=func_name)
            return True, f"JS: {func_name}"

        except Exception as e:
            logger.error("js_fix_error", error=str(e))
            return False, f"Erreur JS fix: {e}"

    async def _execute_sql(self, sql: str) -> Tuple[bool, str]:
        """Exécute un fix SQL."""
        # Sécurité: refuser les opérations destructives
        sql_upper = sql.upper()
        if any(danger in sql_upper for danger in ["DROP", "DELETE", "TRUNCATE"]):
            return False, "Opération destructive refusée"

        try:
            from moteur.db import Database
            with Database.get_session() as session:
                from sqlalchemy import text
                session.execute(text(sql))
                session.commit()

            logger.info("guardian_fix_applied", sql=sql[:100])
            return True, sql[:80]

        except Exception as e:
            return False, str(e)

    def _learn_success(self, proposal, decision: Dict):
        """Guardian apprend d'un fix validé."""
        from moteur.autopilot.models import Learning

        error_pattern = self._extract_pattern(proposal.error_message)
        fix_template = decision.get("fix_override") or proposal.proposed_fix or ""

        learning = Learning(
            id=Learning.generate_id(error_pattern, fix_template),
            error_pattern=error_pattern,
            error_message=proposal.error_message[:500] if proposal.error_message else "",
            fix_template=fix_template,
            status="validated",
            confidence=min(proposal.confidence + 0.1, 1.0),
            explanation=decision.get("reason", "Validé par Claude"),
            times_applied=1,
            created_at=datetime.now()
        )

        self.storage.save_learning(learning)
        logger.info("guardian_learned_success", pattern=error_pattern[:50])

    def _learn_rejection(self, proposal, decision: Dict):
        """Guardian apprend d'un rejet."""
        from moteur.autopilot.models import Learning

        error_pattern = self._extract_pattern(proposal.error_message)
        fix_template = proposal.proposed_fix or ""

        learning = Learning(
            id=Learning.generate_id(error_pattern, fix_template),
            error_pattern=error_pattern,
            error_message=proposal.error_message[:500] if proposal.error_message else "",
            fix_template=fix_template,
            status="rejected",
            confidence=max(proposal.confidence - 0.2, 0.0),
            explanation=decision.get("reason", "Rejeté par Claude"),
            times_applied=0,
            created_at=datetime.now()
        )

        self.storage.save_learning(learning)
        logger.info("guardian_learned_rejection",
                   pattern=error_pattern[:50],
                   reason=decision.get("reason", "")[:100])

    def _extract_pattern(self, error_message: str) -> str:
        """Extrait un pattern générique de l'erreur pour l'apprentissage."""
        if not error_message:
            return ""

        # Normaliser: enlever les valeurs spécifiques
        import re
        pattern = error_message[:200]

        # Remplacer les UUIDs
        pattern = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
                        '<UUID>', pattern, flags=re.IGNORECASE)
        # Remplacer les nombres
        pattern = re.sub(r'\b\d+\b', '<N>', pattern)
        # Remplacer les URLs
        pattern = re.sub(r'http[s]?://[^\s]+', '<URL>', pattern)

        return pattern


async def main():
    """Point d'entrée principal."""
    agent = ClaudeAgent()

    try:
        await agent.initialize()
        await agent.start()
    except KeyboardInterrupt:
        print("\n⏹️  Arrêt demandé...", flush=True)
    except Exception as e:
        print(f"❌ Erreur fatale: {e}", flush=True)
        import traceback
        traceback.print_exc()
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
