# =============================================================================
# AUTOPILOT - Interface Claude
# =============================================================================
"""
Interface pour que Claude puisse valider les fixes.

Usage dans Claude Code:
    python3 -m moteur.autopilot.claude_interface pending
    python3 -m moteur.autopilot.claude_interface validate <id>
    python3 -m moteur.autopilot.claude_interface reject <id> "explication"
"""

import sys
import json
from pathlib import Path

# Ajouter le path du projet
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def get_autopilot():
    """Récupère une instance AutoPilot connectée à la DB."""
    from moteur.autopilot import AutoPilot, PostgresStorage
    from moteur.db import Database

    # Connecter à la DB
    import asyncio
    asyncio.run(Database.connect())

    storage = PostgresStorage()
    storage.set_session_factory(Database.get_session)

    autopilot = AutoPilot(storage=storage)
    autopilot.initialize()

    return autopilot


def show_pending():
    """Affiche les fixes en attente de validation Claude."""
    autopilot = get_autopilot()
    proposals = autopilot.get_pending_proposals()

    if not proposals:
        print("✓ Aucun fix en attente")
        return

    print(f"=== {len(proposals)} fix(s) en attente de validation ===\n")

    for p in proposals:
        print(f"ID: {p.id}")
        print(f"Type: {p.error_type}")
        print(f"Confiance: {p.confidence:.0%}")
        print(f"Fichier: {p.file_path}:{p.line_number or '?'}")
        print(f"Erreur: {p.error_message[:150]}...")
        print(f"Fix proposé:")
        print(f"  {p.proposed_fix}")
        print("-" * 60)
        print()


def validate_fix(fix_id: str, explanation: str = "Validated by Claude"):
    """Valide un fix."""
    autopilot = get_autopilot()
    result = autopilot.validate(fix_id, approved=True, explanation=explanation)

    if result.success:
        print(f"✓ Fix {fix_id} validé et appliqué")
        print(f"  Status: {result.status.value}")
        print(f"  Message: {result.message}")
    else:
        print(f"✗ Échec: {result.message}")


def reject_fix(fix_id: str, explanation: str):
    """Rejette un fix avec explication (Guardian apprend)."""
    if not explanation:
        print("✗ Explication obligatoire pour un rejet")
        return

    autopilot = get_autopilot()
    result = autopilot.validate(fix_id, approved=False, explanation=explanation)

    print(f"✓ Fix {fix_id} rejeté")
    print(f"  Guardian a appris: {explanation}")


def show_stats():
    """Affiche les statistiques."""
    autopilot = get_autopilot()
    stats = autopilot.get_stats()

    print("=== Stats AutoPilot ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 -m moteur.autopilot.claude_interface pending")
        print("  python3 -m moteur.autopilot.claude_interface validate <id>")
        print("  python3 -m moteur.autopilot.claude_interface reject <id> 'explication'")
        print("  python3 -m moteur.autopilot.claude_interface stats")
        return

    cmd = sys.argv[1]

    if cmd == "pending":
        show_pending()
    elif cmd == "validate" and len(sys.argv) >= 3:
        explanation = sys.argv[3] if len(sys.argv) > 3 else "Validated by Claude"
        validate_fix(sys.argv[2], explanation)
    elif cmd == "reject" and len(sys.argv) >= 4:
        reject_fix(sys.argv[2], sys.argv[3])
    elif cmd == "stats":
        show_stats()
    else:
        print(f"Commande inconnue: {cmd}")


if __name__ == "__main__":
    main()
