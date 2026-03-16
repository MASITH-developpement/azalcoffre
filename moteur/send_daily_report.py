#!/usr/bin/env python3
"""
Script d'envoi du rapport de sécurité journalier.
Appelé par cron tous les matins à 7h00.
"""

import sys
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from moteur.security_alerts import send_daily_report

if __name__ == "__main__":
    print("[SECURITY] Envoi du rapport journalier...")
    send_daily_report()
    print("[SECURITY] Rapport envoyé avec succès")
