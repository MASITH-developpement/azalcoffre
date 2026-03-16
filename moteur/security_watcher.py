#!/usr/bin/env python3
"""
AZALPLUS Security Watcher
Surveillance temps réel des logs avec alertes instantanées
"""

import os
import re
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Optional
import json

# Import du module d'alertes
from security_alerts import (
    SecurityEvent, ATTACK_PATTERNS, LOGS_DIR, ALERT_EMAIL,
    detect_attack_type, send_alert, parse_guardian_log,
    get_abuseipdb_info, report_ip_to_abuseipdb, enrich_ip_with_abuse, get_ip_info
)

# Configuration
WATCH_INTERVAL = 2  # Secondes entre chaque vérification
ALERT_THRESHOLD = 3  # Nombre de tentatives avant alerte
ALERT_COOLDOWN = 300  # Secondes avant de ré-alerter pour la même IP
BLOCKED_IPS_FILE = LOGS_DIR / "blocked_ips.json"
AUTO_REPORT_ABUSEIPDB = True  # Signaler automatiquement les attaques à AbuseIPDB
REPORT_SEVERITY_THRESHOLD = ["CRITIQUE", "HAUTE"]  # Sévérités à signaler

# État
last_positions = {}
alert_history = {}  # {ip: last_alert_timestamp}
attack_counts = defaultdict(lambda: defaultdict(int))  # {ip: {attack_type: count}}


def load_blocked_ips() -> set:
    """Charge la liste des IPs déjà bloquées."""
    if BLOCKED_IPS_FILE.exists():
        with open(BLOCKED_IPS_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_blocked_ip(ip: str):
    """Sauvegarde une IP bloquée."""
    blocked = load_blocked_ips()
    blocked.add(ip)
    with open(BLOCKED_IPS_FILE, "w") as f:
        json.dump(list(blocked), f)


def auto_block_ip(ip: str, reason: str):
    """Bloque automatiquement une IP via UFW."""
    if ip in ["127.0.0.1", "localhost"]:
        return False

    blocked = load_blocked_ips()
    if ip in blocked:
        return False

    try:
        cmd = f'sudo ufw deny from {ip} comment "AZALPLUS Auto-block: {reason}"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            save_blocked_ip(ip)
            log_security_event(f"[AUTO-BLOCK] IP {ip} bloquée: {reason}")
            return True
    except Exception as e:
        log_security_event(f"[ERROR] Échec blocage {ip}: {e}")

    return False


def log_security_event(message: str):
    """Log un événement de sécurité."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"{timestamp} | {message}\n"

    log_file = LOGS_DIR / "security_watcher.log"
    with open(log_file, "a") as f:
        f.write(log_line)

    print(log_line.strip())


def should_alert(ip: str, attack_type: str, severity: str) -> bool:
    """Détermine si on doit envoyer une alerte."""
    now = datetime.now()

    # Toujours alerter pour les attaques critiques réussies
    if severity == "CRITIQUE":
        return True

    # Vérifier le cooldown
    key = f"{ip}:{attack_type}"
    if key in alert_history:
        last_alert = alert_history[key]
        if (now - last_alert).total_seconds() < ALERT_COOLDOWN:
            return False

    # Vérifier le seuil
    attack_counts[ip][attack_type] += 1
    if attack_counts[ip][attack_type] >= ALERT_THRESHOLD:
        alert_history[key] = now
        attack_counts[ip][attack_type] = 0  # Reset
        return True

    return False


def process_new_lines(log_file: Path) -> list[SecurityEvent]:
    """Traite les nouvelles lignes d'un fichier log."""
    events = []

    if not log_file.exists():
        return events

    # Obtenir la position actuelle
    current_size = log_file.stat().st_size
    last_pos = last_positions.get(str(log_file), 0)

    # Si le fichier a été tronqué (rotation), recommencer du début
    if current_size < last_pos:
        last_pos = 0

    if current_size == last_pos:
        return events

    with open(log_file, "r") as f:
        f.seek(last_pos)
        new_lines = f.readlines()
        last_positions[str(log_file)] = f.tell()

    for line in new_lines:
        if "WARNING" not in line and "ERROR" not in line:
            continue

        parsed = parse_guardian_log(line)
        if not parsed:
            continue

        # Ignorer les requêtes locales
        if parsed["ip"] == "127.0.0.1":
            continue

        attack_type, severity = detect_attack_type(
            parsed["path"],
            parsed["status"]
        )

        # Ignorer les événements INFO de faible importance
        if severity == "INFO" and "Inconnu" in attack_type:
            continue

        event = SecurityEvent(
            timestamp=parsed["timestamp"],
            ip=parsed["ip"],
            method=parsed["method"],
            path=parsed["path"],
            status=parsed["status"],
            attack_type=attack_type,
            severity=severity,
            blocked=parsed["status"] in [401, 403, 404]
        )
        events.append(event)

    return events


def watch_logs():
    """Boucle principale de surveillance."""
    log_security_event("[START] AZALPLUS Security Watcher démarré")
    log_security_event(f"[CONFIG] Seuil alerte: {ALERT_THRESHOLD} tentatives")
    log_security_event(f"[CONFIG] Cooldown: {ALERT_COOLDOWN}s")
    log_security_event(f"[CONFIG] Email alertes: {ALERT_EMAIL}")

    log_files = [
        LOGS_DIR / "guardian_requests.log",
        LOGS_DIR / "guardian_errors.log"
    ]

    # Initialiser les positions à la fin des fichiers
    for log_file in log_files:
        if log_file.exists():
            last_positions[str(log_file)] = log_file.stat().st_size

    while True:
        try:
            for log_file in log_files:
                events = process_new_lines(log_file)

                for event in events:
                    # Log l'événement
                    log_security_event(
                        f"[{event.severity}] {event.attack_type} | "
                        f"IP: {event.ip} | Path: {event.path[:50]} | "
                        f"{'BLOQUÉ' if event.blocked else 'PASSÉ'}"
                    )

                    # Auto-bloquer les attaques critiques
                    if event.severity == "CRITIQUE" and not event.blocked:
                        auto_block_ip(event.ip, event.attack_type)

                    # Signalement automatique à AbuseIPDB pour les attaques sévères
                    if AUTO_REPORT_ABUSEIPDB and event.severity in REPORT_SEVERITY_THRESHOLD:
                        if report_ip_to_abuseipdb(event.ip, event.attack_type, event.path):
                            log_security_event(f"[ABUSEIPDB] IP {event.ip} signalée automatiquement")

                    # Envoyer alerte si nécessaire
                    if should_alert(event.ip, event.attack_type, event.severity):
                        log_security_event(f"[ALERT] Envoi alerte pour {event.ip}")
                        send_alert(event)

            time.sleep(WATCH_INTERVAL)

        except KeyboardInterrupt:
            log_security_event("[STOP] Arrêt demandé par l'utilisateur")
            break
        except Exception as e:
            log_security_event(f"[ERROR] {e}")
            time.sleep(10)


if __name__ == "__main__":
    watch_logs()
