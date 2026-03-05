# =============================================================================
# AUTOPILOT - Interface Claude
# =============================================================================
"""
Interface pour que Claude puisse valider les fixes ET prendre la main
sur les bugs complexes.

Usage dans Claude Code:
    python3 -m moteur.autopilot.claude_interface pending     # Voir tous les bugs
    python3 -m moteur.autopilot.claude_interface complex     # Bugs complexes (NEEDS_CLAUDE)
    python3 -m moteur.autopilot.claude_interface validate <id>
    python3 -m moteur.autopilot.claude_interface reject <id> "explication"
    python3 -m moteur.autopilot.claude_interface fixed <id> "description du fix"
    python3 -m moteur.autopilot.claude_interface stats
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
    from moteur.autopilot.models import FixStatus

    autopilot = get_autopilot()
    proposals = autopilot.get_pending_proposals()

    # Séparer en deux catégories
    simple = [p for p in proposals if p.status == FixStatus.PENDING]
    complex_bugs = [p for p in proposals if p.status == FixStatus.NEEDS_CLAUDE]

    if not proposals:
        print("✓ Aucun bug en attente")
        return

    # Afficher les bugs complexes en premier (prioritaires)
    if complex_bugs:
        print(f"{'='*60}")
        print(f"🔴 {len(complex_bugs)} BUG(S) COMPLEXE(S) - CLAUDE DOIT PRENDRE LA MAIN")
        print(f"{'='*60}\n")

        for p in complex_bugs:
            print(f"ID: {p.id}")
            print(f"Fichier: {p.file_path}:{p.line_number or '?'}")
            print(f"Raison: {p.metadata.get('reason', 'Bug non reconnu')}")
            print(f"\n--- ERREUR COMPLÈTE ---")
            print(p.error_message)
            print(f"\n{'─'*60}\n")

    # Afficher les fixes simples
    if simple:
        print(f"{'='*60}")
        print(f"🟡 {len(simple)} FIX(S) SIMPLE(S) - À VALIDER/REJETER")
        print(f"{'='*60}\n")

        for p in simple:
            print(f"ID: {p.id}")
            print(f"Type: {p.error_type}")
            print(f"Confiance: {p.confidence:.0%}")
            print(f"Fichier: {p.file_path}:{p.line_number or '?'}")
            print(f"Erreur: {p.error_message[:200]}...")
            print(f"\nFix proposé:")
            print(f"  {p.proposed_fix}")
            print(f"\n{'─'*60}\n")


def show_complex():
    """Affiche uniquement les bugs complexes qui nécessitent Claude."""
    from moteur.autopilot.models import FixStatus

    autopilot = get_autopilot()
    proposals = autopilot.get_pending_proposals()
    complex_bugs = [p for p in proposals if p.status == FixStatus.NEEDS_CLAUDE]

    if not complex_bugs:
        print("✓ Aucun bug complexe en attente")
        return

    print(f"{'='*60}")
    print(f"🔴 {len(complex_bugs)} BUG(S) COMPLEXE(S) - CLAUDE DOIT CODER")
    print(f"{'='*60}\n")

    for p in complex_bugs:
        print(f"ID: {p.id}")
        print(f"Fichier: {p.file_path}:{p.line_number or '?'}")
        print(f"Raison: {p.metadata.get('reason', 'Bug non reconnu')}")
        print(f"\n--- ERREUR COMPLÈTE ---")
        print(p.error_message)
        print(f"\n{'─'*60}\n")


def validate_fix(fix_id: str, explanation: str = "Validated by Claude"):
    """Valide un fix simple."""
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


def mark_fixed(fix_id: str, description: str):
    """
    Marque un bug complexe comme corrigé par Claude.
    Utilisé après que Claude ait pris la main et codé le fix.
    """
    from moteur.autopilot.models import FixStatus, Learning

    autopilot = get_autopilot()
    proposal = autopilot._storage.get_proposal(fix_id)

    if not proposal:
        print(f"✗ Bug {fix_id} non trouvé")
        return

    # Mettre à jour le statut
    autopilot._storage.update_proposal_status(fix_id, FixStatus.APPLIED)

    # Créer un apprentissage
    learning = Learning(
        id=Learning.generate_id(proposal.error_type, description),
        error_pattern=proposal.error_type,
        error_message=proposal.error_message,
        fix_template=description,
        status="validated",
        explanation=f"Corrigé manuellement par Claude: {description}",
        file_path=proposal.file_path,
        confidence=0.9,  # Haute confiance car corrigé manuellement
    )
    autopilot._storage.save_learning(learning)

    print(f"✓ Bug {fix_id} marqué comme corrigé")
    print(f"  Description: {description}")
    print(f"  Guardian a appris ce pattern pour le futur")


def show_stats():
    """Affiche les statistiques."""
    autopilot = get_autopilot()
    stats = autopilot.get_stats()

    print("=== Stats AutoPilot ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")


def main():
    if len(sys.argv) < 2:
        print("╔════════════════════════════════════════════════════════════╗")
        print("║           AUTOPILOT - Interface Claude                     ║")
        print("╠════════════════════════════════════════════════════════════╣")
        print("║  pending              Voir tous les bugs en attente        ║")
        print("║  complex              Bugs complexes (Claude doit coder)   ║")
        print("║  validate <id>        Valider un fix simple                ║")
        print("║  reject <id> 'why'    Rejeter avec explication             ║")
        print("║  fixed <id> 'desc'    Marquer comme corrigé par Claude     ║")
        print("║  stats                Statistiques                         ║")
        print("╚════════════════════════════════════════════════════════════╝")
        return

    cmd = sys.argv[1]

    if cmd == "pending":
        show_pending()
    elif cmd == "complex":
        show_complex()
    elif cmd == "validate" and len(sys.argv) >= 3:
        explanation = sys.argv[3] if len(sys.argv) > 3 else "Validated by Claude"
        validate_fix(sys.argv[2], explanation)
    elif cmd == "reject" and len(sys.argv) >= 4:
        reject_fix(sys.argv[2], sys.argv[3])
    elif cmd == "fixed" and len(sys.argv) >= 4:
        mark_fixed(sys.argv[2], sys.argv[3])
    elif cmd == "stats":
        show_stats()
    else:
        print(f"Commande inconnue: {cmd}")


if __name__ == "__main__":
    main()
