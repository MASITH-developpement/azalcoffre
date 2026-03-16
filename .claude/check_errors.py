#!/usr/bin/env python3
"""
Hook Claude Code: Vérifie les erreurs AutoPilot en attente.
Exécuté automatiquement quand Claude démarre une session.
"""

import sys
import os

# Ajouter le chemin du projet
sys.path.insert(0, '/home/ubuntu/azalplus')

def check_errors():
    """Vérifie et affiche les erreurs en attente."""
    try:
        from moteur.autopilot import PostgresStorage
        from moteur.db import Database
        import asyncio

        async def get_errors():
            await Database.connect()
            storage = PostgresStorage()
            storage.set_session_factory(Database.get_session)
            proposals = storage.get_pending_proposals()
            await Database.disconnect()
            return proposals

        proposals = asyncio.run(get_errors())

        if not proposals:
            return

        # Il y a des erreurs - afficher l'alerte
        print("\n" + "="*70)
        print("🚨 ERREURS EN ATTENTE DE CORRECTION")
        print("="*70)
        print(f"📊 {len(proposals)} erreur(s) détectée(s)\n")

        for i, p in enumerate(proposals[:5], 1):
            err = p.error_message[:150] if p.error_message else 'N/A'
            print(f"[{i}] {p.error_type} - Confiance: {p.confidence*100:.0f}%")
            print(f"    {err}...")
            if p.proposed_fix:
                print(f"    Fix: {p.proposed_fix[:80]}...")
            print()

        if len(proposals) > 5:
            print(f"... et {len(proposals) - 5} autres erreurs\n")

        print("="*70)
        print("💡 Claude, corrige ces erreurs avant de continuer.")
        print("="*70 + "\n")

    except Exception as e:
        # Silencieux si erreur (DB pas connectée, etc.)
        pass

if __name__ == "__main__":
    check_errors()
