#!/usr/bin/env python3
"""
AZALPLUS Security Alerts System
- Rapport journalier des tentatives d'intrusion
- Alertes en temps réel par email
"""

import os
import re
import smtplib
import json
import urllib.request
import urllib.error
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from collections import defaultdict
from functools import lru_cache
import structlog
from dotenv import load_dotenv

# Charger le .env
load_dotenv(Path(__file__).parent.parent / ".env")

logger = structlog.get_logger()

# Configuration
ALERT_EMAIL = "contact@stephane-moreau.fr"
LOGS_DIR = Path("/home/ubuntu/azalplus/logs")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "security@azalplus.fr")

# AbuseIPDB - Threat Intelligence (gratuit: 1000 req/jour)
ABUSEIPDB_API_KEY = os.getenv("ABUSEIPDB_API_KEY", "")

# Logo AZALPLUS en base64 (SVG) pour les emails
LOGO_BASE64 = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA1MDAgMTIwIj4KICA8IS0tIENlcmNsZSBibGV1IHJvaSAtLT4KICA8Y2lyY2xlIGN4PSI2MCIgY3k9IjYwIiByPSI1NSIgZmlsbD0iIzM0NTREMSIvPgoKICA8IS0tIFBvaW50IGFjY2VudCBibGV1IGNsYWlyIC0tPgogIDxjaXJjbGUgY3g9IjkyIiBjeT0iMjgiIHI9IjYiIGZpbGw9IiM2QjlGRkYiLz4KCiAgPCEtLSBMZXR0cmUgQSsgZGFucyBsZSBjZXJjbGUgLS0+CiAgPHRleHQgeD0iNDUiIHk9IjgyIgogICAgICAgIGZvbnQtZmFtaWx5PSJJbnRlciwgTW9udHNlcnJhdCwgQXJpYWwsIHNhbnMtc2VyaWYiCiAgICAgICAgZm9udC13ZWlnaHQ9IjgwMCIKICAgICAgICBmb250LXNpemU9IjU4IgogICAgICAgIGZpbGw9IiNGRkZGRkYiPkE8L3RleHQ+CiAgPHRleHQgeD0iNzgiIHk9IjY4IgogICAgICAgIGZvbnQtZmFtaWx5PSJJbnRlciwgTW9udHNlcnJhdCwgQXJpYWwsIHNhbnMtc2VyaWYiCiAgICAgICAgZm9udC13ZWlnaHQ9IjcwMCIKICAgICAgICBmb250LXNpemU9IjMyIgogICAgICAgIGZpbGw9IiNGRkZGRkYiPis8L3RleHQ+CgogIDwhLS0gVGV4dGUgQVpBTFBMVVMgLS0+CiAgPHRleHQgeD0iMTM1IiB5PSI3OCIKICAgICAgICBmb250LWZhbWlseT0iSW50ZXIsIE1vbnRzZXJyYXQsIEFyaWFsLCBzYW5zLXNlcmlmIgogICAgICAgIGZvbnQtd2VpZ2h0PSI3MDAiCiAgICAgICAgZm9udC1zaXplPSI0OCIKICAgICAgICBmaWxsPSIjMzQ1NEQxIj5BWkFMPC90ZXh0PgogIDx0ZXh0IHg9IjI4MyIgeT0iNzgiCiAgICAgICAgZm9udC1mYW1pbHk9IkludGVyLCBNb250c2VycmF0LCBBcmlhbCwgc2Fucy1zZXJpZiIKICAgICAgICBmb250LXdlaWdodD0iNzAwIgogICAgICAgIGZvbnQtc2l6ZT0iNDgiCiAgICAgICAgZmlsbD0iIzZCOUZGRiI+UExVUzwvdGV4dD4KPC9zdmc+Cg=="
LOGO_DATA_URI = f"data:image/svg+xml;base64,{LOGO_BASE64}"

# Cache pour les infos IP (évite les requêtes répétées)
IP_CACHE_FILE = Path("/home/ubuntu/azalplus/logs/ip_cache.json")


@dataclass
class IPInfo:
    """Informations enrichies sur une IP."""
    ip: str
    country: str = "Inconnu"
    country_code: str = "??"
    city: str = "Inconnu"
    isp: str = "Inconnu"
    org: str = "Inconnu"
    is_proxy: bool = False
    is_hosting: bool = False
    threat_score: int = 0
    # AbuseIPDB data
    abuse_score: int = 0  # 0-100 (100 = très malveillant)
    abuse_reports: int = 0  # Nombre de signalements
    abuse_last_reported: str = ""  # Date du dernier signalement
    abuse_categories: list = field(default_factory=list)  # Types d'abus signalés


def load_ip_cache() -> dict:
    """Charge le cache des IPs."""
    if IP_CACHE_FILE.exists():
        try:
            with open(IP_CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_ip_cache(cache: dict):
    """Sauvegarde le cache des IPs."""
    with open(IP_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


@lru_cache(maxsize=100)
def get_ip_info(ip: str) -> IPInfo:
    """Récupère les informations géographiques d'une IP via ip-api.com (gratuit)."""
    if ip in ["127.0.0.1", "localhost"]:
        return IPInfo(ip=ip, country="Local", city="Localhost", isp="Local")

    # Vérifier le cache
    cache = load_ip_cache()
    if ip in cache:
        data = cache[ip]
        return IPInfo(
            ip=ip,
            country=data.get("country", "Inconnu"),
            country_code=data.get("countryCode", "??"),
            city=data.get("city", "Inconnu"),
            isp=data.get("isp", "Inconnu"),
            org=data.get("org", "Inconnu"),
            is_proxy=data.get("proxy", False),
            is_hosting=data.get("hosting", False),
        )

    try:
        # API gratuite ip-api.com (limite: 45 req/min)
        url = f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,isp,org,proxy,hosting"
        req = urllib.request.Request(url, headers={"User-Agent": "AZALPLUS-Security/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())

        if data.get("status") == "success":
            # Sauvegarder en cache
            cache[ip] = data
            save_ip_cache(cache)

            return IPInfo(
                ip=ip,
                country=data.get("country", "Inconnu"),
                country_code=data.get("countryCode", "??"),
                city=data.get("city", "Inconnu"),
                isp=data.get("isp", "Inconnu"),
                org=data.get("org", "Inconnu"),
                is_proxy=data.get("proxy", False),
                is_hosting=data.get("hosting", False),
            )
    except Exception as e:
        pass

    return IPInfo(ip=ip)


def get_ip_flag(country_code: str) -> str:
    """Retourne l'emoji drapeau pour un code pays."""
    if country_code == "??" or len(country_code) != 2:
        return "🌐"
    # Convertir le code pays en emoji drapeau
    return "".join(chr(0x1F1E6 + ord(c) - ord('A')) for c in country_code.upper())


# Catégories AbuseIPDB (pour affichage lisible)
ABUSEIPDB_CATEGORIES = {
    1: "DNS Compromise",
    2: "DNS Poisoning",
    3: "Fraud Orders",
    4: "DDoS Attack",
    5: "FTP Brute-Force",
    6: "Ping of Death",
    7: "Phishing",
    8: "Fraud VoIP",
    9: "Open Proxy",
    10: "Web Spam",
    11: "Email Spam",
    12: "Blog Spam",
    13: "VPN IP",
    14: "Port Scan",
    15: "Hacking",
    16: "SQL Injection",
    17: "Spoofing",
    18: "Brute-Force",
    19: "Bad Web Bot",
    20: "Exploited Host",
    21: "Web App Attack",
    22: "SSH",
    23: "IoT Targeted",
}


def get_abuseipdb_info(ip: str) -> dict:
    """
    Interroge AbuseIPDB pour obtenir le score de réputation d'une IP.
    Retourne: {abuse_score, abuse_reports, abuse_last_reported, abuse_categories}
    """
    if not ABUSEIPDB_API_KEY:
        return {}

    if ip in ["127.0.0.1", "localhost"] or ip.startswith("192.168.") or ip.startswith("10."):
        return {}

    try:
        url = f"https://api.abuseipdb.com/api/v2/check?ipAddress={ip}&maxAgeInDays=90"
        req = urllib.request.Request(url, headers={
            "Key": ABUSEIPDB_API_KEY,
            "Accept": "application/json",
            "User-Agent": "AZALPLUS-Security/1.0"
        })

        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())

        if "data" in data:
            d = data["data"]
            categories = [ABUSEIPDB_CATEGORIES.get(c, f"Cat-{c}") for c in d.get("reports", [{}])[0].get("categories", []) if d.get("reports")]
            # Extraire les catégories des derniers rapports
            all_categories = set()
            for report in d.get("reports", [])[:5]:  # 5 derniers rapports
                for cat_id in report.get("categories", []):
                    all_categories.add(ABUSEIPDB_CATEGORIES.get(cat_id, f"Cat-{cat_id}"))

            return {
                "abuse_score": d.get("abuseConfidenceScore", 0),
                "abuse_reports": d.get("totalReports", 0),
                "abuse_last_reported": d.get("lastReportedAt", ""),
                "abuse_categories": list(all_categories)[:5],  # Max 5 catégories
            }
    except Exception as e:
        pass

    return {}


def enrich_ip_with_abuse(ip_info: IPInfo) -> IPInfo:
    """Enrichit les infos IP avec les données AbuseIPDB."""
    abuse_data = get_abuseipdb_info(ip_info.ip)
    if abuse_data:
        ip_info.abuse_score = abuse_data.get("abuse_score", 0)
        ip_info.abuse_reports = abuse_data.get("abuse_reports", 0)
        ip_info.abuse_last_reported = abuse_data.get("abuse_last_reported", "")
        ip_info.abuse_categories = abuse_data.get("abuse_categories", [])
    return ip_info


# Mapping des types d'attaques AZALPLUS vers catégories AbuseIPDB
ATTACK_TO_ABUSEIPDB_CATEGORIES = {
    "PHPUnit RCE (CVE-2017-9841)": [15, 21],  # Hacking, Web App Attack
    "SQL Injection": [16],  # SQL Injection
    "XSS Attack": [21],  # Web App Attack
    "Path Traversal": [15, 21],  # Hacking, Web App Attack
    "Admin Panel Scan": [19, 21],  # Bad Web Bot, Web App Attack
    "Brute Force Login": [18],  # Brute-Force
    "Accès Pages Fictives (Arnaque)": [7, 21],  # Phishing, Web App Attack
    "Scan de reconnaissance": [14],  # Port Scan
    "Accès non autorisé": [18, 21],  # Brute-Force, Web App Attack
}

# Cache des signalements déjà effectués (évite les doublons)
REPORTED_IPS_CACHE = set()


def report_ip_to_abuseipdb(ip: str, attack_type: str, path: str) -> bool:
    """
    Signale une IP malveillante à AbuseIPDB.
    Retourne True si le signalement a réussi.
    """
    if not ABUSEIPDB_API_KEY:
        return False

    # Éviter les signalements en double
    cache_key = f"{ip}:{attack_type}"
    if cache_key in REPORTED_IPS_CACHE:
        return False

    # Ne pas signaler les IPs locales/privées
    if ip in ["127.0.0.1", "localhost"] or ip.startswith("192.168.") or ip.startswith("10."):
        return False

    # Catégories AbuseIPDB pour ce type d'attaque
    categories = ATTACK_TO_ABUSEIPDB_CATEGORIES.get(attack_type, [21])  # Default: Web App Attack
    categories_str = ",".join(str(c) for c in categories)

    # Commentaire du signalement
    comment = f"AZALPLUS Guardian WAF: {attack_type} detected. Path: {path[:100]}"

    try:
        url = "https://api.abuseipdb.com/api/v2/report"
        data = urllib.parse.urlencode({
            "ip": ip,
            "categories": categories_str,
            "comment": comment
        }).encode()

        req = urllib.request.Request(url, data=data, headers={
            "Key": ABUSEIPDB_API_KEY,
            "Accept": "application/json",
            "User-Agent": "AZALPLUS-Security/1.0"
        })

        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode())

        if "data" in result:
            REPORTED_IPS_CACHE.add(cache_key)
            logger.info("abuseipdb_reported", ip=ip, score=result['data'].get('abuseConfidenceScore', '?'))
            return True

    except Exception as e:
        logger.error("abuseipdb_report_error", ip=ip, error=str(e))

    return False


def get_abuse_score_badge(score: int) -> str:
    """Génère un badge HTML coloré selon le score AbuseIPDB."""
    if score == 0:
        return "<span style='background:#28a745;color:white;padding:2px 8px;border-radius:3px;'>✓ Clean</span>"
    elif score < 25:
        return f"<span style='background:#ffc107;color:black;padding:2px 8px;border-radius:3px;'>⚠ {score}%</span>"
    elif score < 75:
        return f"<span style='background:#fd7e14;color:white;padding:2px 8px;border-radius:3px;'>⚠ {score}%</span>"
    else:
        return f"<span style='background:#dc3545;color:white;padding:2px 8px;border-radius:3px;'>🚨 {score}%</span>"


def format_ip_info_html(info: IPInfo) -> str:
    """Formate les infos IP en HTML."""
    flag = get_ip_flag(info.country_code)
    warnings = []
    if info.is_proxy:
        warnings.append("🔒 VPN/Proxy")
    if info.is_hosting:
        warnings.append("🖥️ Hébergeur")

    warning_html = f" <span style='color:#dc3545;'>{' | '.join(warnings)}</span>" if warnings else ""

    return f"""
    <div style="background:#f8f9fa;padding:10px;border-radius:4px;margin:5px 0;">
        <strong>{flag} {info.country}</strong> - {info.city}<br>
        <span style="color:#666;">FAI: {info.isp}</span><br>
        <span style="color:#666;">Org: {info.org}</span>{warning_html}
    </div>
    """


# Patterns d'attaques connues
ATTACK_PATTERNS = {
    "phpunit_rce": {
        "pattern": r"phpunit.*eval-stdin\.php",
        "name": "PHPUnit RCE (CVE-2017-9841)",
        "severity": "CRITIQUE",
        "action": "Bloquer l'IP avec: sudo ufw deny from {ip}"
    },
    "sql_injection": {
        "pattern": r"(union.*select|or\s+1\s*=\s*1|drop\s+table)",
        "name": "SQL Injection",
        "severity": "CRITIQUE",
        "action": "Bloquer l'IP avec: sudo ufw deny from {ip}"
    },
    "xss_attack": {
        "pattern": r"(<script|javascript:|onerror\s*=)",
        "name": "XSS Attack",
        "severity": "HAUTE",
        "action": "Bloquer l'IP avec: sudo ufw deny from {ip}"
    },
    "path_traversal": {
        "pattern": r"\.\./|\.\.\\",
        "name": "Path Traversal",
        "severity": "HAUTE",
        "action": "Bloquer l'IP avec: sudo ufw deny from {ip}"
    },
    "admin_scan": {
        "pattern": r"(wp-admin|phpmyadmin|admin\.php|boaform)",
        "name": "Admin Panel Scan",
        "severity": "MOYENNE",
        "action": "Surveiller l'IP: {ip}"
    },
    "brute_force": {
        "pattern": r"401.*login|401.*auth",
        "name": "Brute Force Login",
        "severity": "HAUTE",
        "action": "Bloquer l'IP avec: sudo ufw deny from {ip}"
    },
    "fake_pages": {
        "pattern": r"(hello\.html|connexion\.html)",
        "name": "Accès Pages Fictives (Arnaque)",
        "severity": "INFO",
        "action": "IP suspecte à surveiller: {ip}"
    }
}


@dataclass
class SecurityEvent:
    timestamp: datetime
    ip: str
    method: str
    path: str
    status: int
    attack_type: str
    severity: str
    blocked: bool


def parse_guardian_log(line: str) -> Optional[dict]:
    """Parse une ligne de log Guardian."""
    # Format: 2026-03-10T21:16:48.610497 | WARNING  | GET:401 | 103.218.243.42 | GET /path
    pattern = r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)\s*\|\s*(\w+)\s*\|\s*(\w+):(\d+)\s*\|\s*([\d\.]+)\s*\|\s*(\w+)\s+(.+)"
    match = re.match(pattern, line)
    if match:
        return {
            "timestamp": datetime.fromisoformat(match.group(1)),
            "level": match.group(2),
            "method": match.group(3),
            "status": int(match.group(4)),
            "ip": match.group(5),
            "request_method": match.group(6),
            "path": match.group(7).strip()
        }
    return None


def detect_attack_type(path: str, status: int) -> tuple[str, str]:
    """Détecte le type d'attaque basé sur le chemin."""
    path_lower = path.lower()
    for attack_id, attack_info in ATTACK_PATTERNS.items():
        if re.search(attack_info["pattern"], path_lower, re.IGNORECASE):
            return attack_info["name"], attack_info["severity"]

    if status in [401, 403]:
        return "Accès non autorisé", "INFO"
    elif status == 404:
        return "Scan de reconnaissance", "BASSE"

    return "Inconnu", "INFO"


def get_action_for_attack(attack_type: str, ip: str) -> str:
    """Retourne l'action recommandée pour un type d'attaque."""
    for attack_info in ATTACK_PATTERNS.values():
        if attack_info["name"] == attack_type:
            return attack_info["action"].format(ip=ip)
    return f"Surveiller l'IP: {ip}"


def analyze_logs(date: datetime = None) -> list[SecurityEvent]:
    """Analyse les logs pour une date donnée."""
    if date is None:
        date = datetime.now()

    events = []
    date_str = date.strftime("%Y-%m-%d")

    log_files = [
        LOGS_DIR / "guardian_requests.log",
        LOGS_DIR / "guardian_errors.log"
    ]

    for log_file in log_files:
        if not log_file.exists():
            continue

        with open(log_file, "r") as f:
            for line in f:
                if date_str not in line:
                    continue

                if "WARNING" not in line and "ERROR" not in line:
                    continue

                parsed = parse_guardian_log(line)
                if not parsed:
                    continue

                attack_type, severity = detect_attack_type(
                    parsed["path"],
                    parsed["status"]
                )

                # Ignorer les requêtes locales légitimes
                if parsed["ip"] == "127.0.0.1" and severity == "INFO":
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


def generate_daily_report(date: datetime = None) -> str:
    """Génère le rapport journalier HTML."""
    if date is None:
        date = datetime.now() - timedelta(days=1)

    events = analyze_logs(date)
    date_str = date.strftime("%d/%m/%Y")

    # Statistiques
    total_attacks = len(events)
    blocked = sum(1 for e in events if e.blocked)
    successful = total_attacks - blocked

    # Par type d'attaque
    by_type = defaultdict(int)
    for e in events:
        by_type[e.attack_type] += 1

    # Par IP
    by_ip = defaultdict(int)
    for e in events:
        by_ip[e.ip] += 1

    # Top 10 IPs
    top_ips = sorted(by_ip.items(), key=lambda x: x[1], reverse=True)[:10]

    # Attaques bloquées (pour le résumé)
    blocked_events = [e for e in events if e.blocked]
    blocked_by_type = defaultdict(list)
    for e in blocked_events:
        blocked_by_type[e.attack_type].append(e)

    # Unique IPs
    unique_ips = len(set(e.ip for e in events if e.ip != "127.0.0.1"))

    # Déterminer le statut de sécurité
    if successful == 0:
        security_status = "secure"
        security_title = "🛡️ SYSTÈME SÉCURISÉ"
        security_message = f"Aucune intrusion détectée. Guardian a bloqué {blocked} tentative{'s' if blocked > 1 else ''} malveillante{'s' if blocked > 1 else ''} provenant de {unique_ips} IP{'s' if unique_ips > 1 else ''} différente{'s' if unique_ips > 1 else ''}."
    elif successful <= 3:
        security_status = "warning"
        security_title = "⚠️ ATTENTION REQUISE"
        security_message = f"{successful} requête{'s' if successful > 1 else ''} suspecte{'s' if successful > 1 else ''} non bloquée{'s' if successful > 1 else ''}. Vérifiez les détails ci-dessous. {blocked} tentative{'s' if blocked > 1 else ''} bloquée{'s' if blocked > 1 else ''}."
    else:
        security_status = "danger"
        security_title = "🚨 ALERTE SÉCURITÉ"
        security_message = f"{successful} tentatives potentiellement réussies détectées ! Action immédiate recommandée."

    # Génération HTML
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 10px; }}
        h2 {{ color: #16213e; margin-top: 30px; }}
        .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
        .stat-box {{ flex: 1; padding: 20px; border-radius: 8px; text-align: center; }}
        .stat-box.total {{ background: #e8f4fd; }}
        .stat-box.blocked {{ background: #d4edda; }}
        .stat-box.success {{ background: #f8d7da; }}
        .stat-number {{ font-size: 36px; font-weight: bold; }}
        .stat-label {{ color: #666; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #16213e; color: white; }}
        tr:hover {{ background: #f5f5f5; }}
        .severity-CRITIQUE {{ color: #dc3545; font-weight: bold; }}
        .severity-HAUTE {{ color: #fd7e14; font-weight: bold; }}
        .severity-MOYENNE {{ color: #ffc107; }}
        .severity-BASSE {{ color: #6c757d; }}
        .severity-INFO {{ color: #17a2b8; }}
        .blocked {{ color: #28a745; }}
        .success {{ color: #dc3545; font-weight: bold; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }}
        .action {{ background: #fff3cd; padding: 10px; border-radius: 4px; margin: 5px 0; font-family: monospace; }}
        .analysis-box {{ padding: 20px; border-radius: 8px; margin: 25px 0; }}
        .analysis-box.secure {{ background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); border-left: 5px solid #28a745; }}
        .analysis-box.warning {{ background: linear-gradient(135deg, #fff3cd 0%, #ffeeba 100%); border-left: 5px solid #ffc107; }}
        .analysis-box.danger {{ background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%); border-left: 5px solid #dc3545; }}
        .analysis-title {{ font-size: 20px; font-weight: bold; margin-bottom: 10px; }}
        .analysis-box.secure .analysis-title {{ color: #155724; }}
        .analysis-box.warning .analysis-title {{ color: #856404; }}
        .analysis-box.danger .analysis-title {{ color: #721c24; }}
        .analysis-summary {{ color: #333; line-height: 1.6; }}
        .blocked-attacks {{ background: #f8f9fa; border-radius: 8px; padding: 15px; margin-top: 20px; }}
        .blocked-attacks h3 {{ color: #28a745; margin-top: 0; font-size: 16px; }}
        .attack-item {{ display: flex; align-items: center; padding: 8px 0; border-bottom: 1px solid #dee2e6; }}
        .attack-item:last-child {{ border-bottom: none; }}
        .attack-time {{ color: #6c757d; font-size: 12px; width: 60px; }}
        .attack-type {{ background: #e9ecef; padding: 3px 8px; border-radius: 4px; font-size: 12px; margin: 0 10px; }}
        .attack-type.sql {{ background: #dc3545; color: white; }}
        .attack-type.xss {{ background: #fd7e14; color: white; }}
        .attack-type.cmd {{ background: #6f42c1; color: white; }}
        .attack-type.scan {{ background: #17a2b8; color: white; }}
        .attack-ip {{ font-family: monospace; font-size: 12px; color: #495057; }}
        .attack-status {{ margin-left: auto; font-size: 12px; color: #28a745; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <div style="text-align: center; margin-bottom: 20px;">
            <img src="__LOGO_URL__" alt="AZALPLUS" style="height: 60px;">
        </div>
        <h1 style="text-align: center;">Rapport Sécurité AZALPLUS</h1>
        <p><strong>Date :</strong> {date_str}</p>
        <p><strong>Généré le :</strong> {datetime.now().strftime("%d/%m/%Y à %H:%M")}</p>

        <div class="stats">
            <div class="stat-box total">
                <div class="stat-number">{total_attacks}</div>
                <div class="stat-label">Tentatives totales</div>
            </div>
            <div class="stat-box blocked">
                <div class="stat-number">{blocked}</div>
                <div class="stat-label">✅ Bloquées</div>
            </div>
            <div class="stat-box success">
                <div class="stat-number">{successful}</div>
                <div class="stat-label">{'⚠️ Réussies' if successful > 0 else '✅ Réussies'}</div>
            </div>
        </div>

        <!-- ANALYSE DE SÉCURITÉ 24H -->
        <div class="analysis-box {security_status}">
            <div class="analysis-title">{security_title}</div>
            <div class="analysis-summary">{security_message}</div>
        </div>

        <!-- ATTAQUES BLOQUÉES (Résumé) -->
        <div class="blocked-attacks">
            <h3>🛡️ Attaques Bloquées par Guardian</h3>
"""

    # Ajouter les 10 dernières attaques bloquées
    recent_blocked = sorted(blocked_events, key=lambda x: x.timestamp, reverse=True)[:10]
    for e in recent_blocked:
        attack_class = "sql" if "SQL" in e.attack_type.upper() else "xss" if "XSS" in e.attack_type.upper() else "cmd" if "COMMAND" in e.attack_type.upper() else "scan"
        html += f"""            <div class="attack-item">
                <span class="attack-time">{e.timestamp.strftime("%H:%M")}</span>
                <span class="attack-type {attack_class}">{e.attack_type[:20]}</span>
                <span class="attack-ip">{e.ip}</span>
                <span class="attack-status">✓ BLOQUÉ</span>
            </div>
"""

    if len(blocked_events) > 10:
        html += f"""            <div style="text-align:center;padding:10px;color:#6c757d;font-size:12px;">
                ... et {len(blocked_events) - 10} autres attaques bloquées
            </div>
"""

    html += """        </div>

        <h2>📊 Par type d'attaque</h2>
        <table>
            <tr><th>Type</th><th>Nombre</th></tr>
"""

    for attack_type, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
        html += f"            <tr><td>{attack_type}</td><td>{count}</td></tr>\n"

    html += """
        </table>

        <h2>🌐 Top 10 IPs suspectes</h2>
        <table>
            <tr><th>IP</th><th>Localisation</th><th>Réputation</th><th>Tentatives</th><th>Action</th></tr>
"""

    for ip, count in top_ips:
        if ip != "127.0.0.1":
            # Enrichissement IP avec géolocalisation
            ip_info = get_ip_info(ip)
            # Enrichissement avec AbuseIPDB
            ip_info = enrich_ip_with_abuse(ip_info)

            flag = get_ip_flag(ip_info.country_code)
            location = f"{flag} {ip_info.country}"
            if ip_info.city != "Inconnu":
                location += f", {ip_info.city}"

            # Indicateurs de risque (VPN/Proxy/Hébergeur)
            risk_badges = ""
            if ip_info.is_proxy:
                risk_badges += " <span style='background:#dc3545;color:white;padding:2px 6px;border-radius:3px;font-size:10px;'>VPN/Proxy</span>"
            if ip_info.is_hosting:
                risk_badges += " <span style='background:#fd7e14;color:white;padding:2px 6px;border-radius:3px;font-size:10px;'>Hébergeur</span>"

            # Score AbuseIPDB
            abuse_badge = get_abuse_score_badge(ip_info.abuse_score)
            abuse_details = ""
            if ip_info.abuse_reports > 0:
                abuse_details = f"<br><small style='color:#666;'>{ip_info.abuse_reports} signalement{'s' if ip_info.abuse_reports > 1 else ''}"
                if ip_info.abuse_categories:
                    abuse_details += f"<br>({', '.join(ip_info.abuse_categories[:3])})"
                abuse_details += "</small>"

            html += f"""            <tr>
                <td><strong>{ip}</strong><br><small style="color:#666;">{ip_info.isp}</small></td>
                <td>{location}{risk_badges}</td>
                <td>{abuse_badge}{abuse_details}</td>
                <td style="text-align:center;"><strong>{count}</strong></td>
                <td><code>sudo ufw deny from {ip}</code></td>
            </tr>\n"""

    html += """
        </table>

        <h2>📋 Détail des événements</h2>
        <table>
            <tr><th>Heure</th><th>IP</th><th>Pays</th><th>Chemin</th><th>Type</th><th>Sévérité</th><th>Status</th></tr>
"""

    # Cache local pour éviter les requêtes répétées dans le même rapport
    ip_cache_local = {}

    # Limiter à 50 événements dans le rapport
    for event in events[:50]:
        status_class = "blocked" if event.blocked else "success"
        status_text = "Bloqué" if event.blocked else "⚠️ RÉUSSI"

        # Récupérer les infos IP (avec cache local)
        if event.ip not in ip_cache_local:
            ip_cache_local[event.ip] = get_ip_info(event.ip)
        ip_info = ip_cache_local[event.ip]
        flag = get_ip_flag(ip_info.country_code)

        html += f"""            <tr>
                <td>{event.timestamp.strftime("%H:%M:%S")}</td>
                <td>{event.ip}</td>
                <td>{flag}</td>
                <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;">{event.path[:50]}</td>
                <td>{event.attack_type}</td>
                <td class="severity-{event.severity}">{event.severity}</td>
                <td class="{status_class}">{status_text}</td>
            </tr>\n"""

    if len(events) > 50:
        html += f"            <tr><td colspan='6'><em>... et {len(events) - 50} autres événements</em></td></tr>\n"

    html += f"""
        </table>

        <div class="footer">
            <p><img src="__LOGO_URL__" alt="AZALPLUS" style="height: 24px; vertical-align: middle;"> AZALPLUS Security System - Guardian WAF</p>
            <p>Ce rapport est généré automatiquement. Pour toute question : contact@masith.fr</p>
        </div>
    </div>
</body>
</html>
"""
    return html


def generate_alert_email(event: SecurityEvent) -> str:
    """Génère l'email d'alerte pour une attaque."""
    action = get_action_for_attack(event.attack_type, event.ip)
    status = "🚫 BLOQUÉE" if event.blocked else "⚠️ ATTENTION: POSSIBLE INTRUSION"

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .alert {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ background: {'#dc3545' if not event.blocked else '#28a745'}; color: white; padding: 20px; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .content {{ padding: 20px; }}
        .field {{ margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 4px; }}
        .field-label {{ font-weight: bold; color: #333; }}
        .field-value {{ color: #666; margin-top: 5px; font-family: monospace; }}
        .action-box {{ background: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 4px; margin-top: 20px; }}
        .action-box h3 {{ margin-top: 0; color: #856404; }}
        .action-code {{ background: #1a1a2e; color: #00ff00; padding: 10px; border-radius: 4px; font-family: monospace; margin-top: 10px; }}
        .severity {{ display: inline-block; padding: 5px 10px; border-radius: 4px; font-weight: bold; }}
        .severity-CRITIQUE {{ background: #dc3545; color: white; }}
        .severity-HAUTE {{ background: #fd7e14; color: white; }}
        .severity-MOYENNE {{ background: #ffc107; color: black; }}
        .footer {{ padding: 15px; background: #f8f9fa; text-align: center; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="alert">
        <div class="header">
            <div style="margin-bottom: 10px;">
                <img src="__LOGO_URL__" alt="AZALPLUS" style="height: 40px;">
            </div>
            <h1>ALERTE SÉCURITÉ AZALPLUS</h1>
            <p>{status}</p>
        </div>
        <div class="content">
            <h2>{event.attack_type}</h2>
            <span class="severity severity-{event.severity}">{event.severity}</span>

            <div class="field">
                <div class="field-label">📅 Date/Heure</div>
                <div class="field-value">{event.timestamp.strftime("%d/%m/%Y à %H:%M:%S")}</div>
            </div>

            <div class="field">
                <div class="field-label">🌐 IP Attaquant</div>
                <div class="field-value">{event.ip}</div>
            </div>

            <div class="field">
                <div class="field-label">🔗 Chemin ciblé</div>
                <div class="field-value">{event.path}</div>
            </div>

            <div class="field">
                <div class="field-label">📊 Méthode HTTP</div>
                <div class="field-value">{event.method} → Status {event.status}</div>
            </div>

            <div class="action-box">
                <h3>🛠️ Action recommandée</h3>
                <p>{action}</p>
                <div class="action-code">sudo ufw deny from {event.ip} comment "Blocked by AZALPLUS Security - {event.attack_type}"</div>
            </div>
        </div>
        <div class="footer">
            <img src="__LOGO_URL__" alt="AZALPLUS" style="height: 20px; vertical-align: middle;"> AZALPLUS Security System - Alerte automatique
        </div>
    </div>
</body>
</html>
"""
    return html


def send_email(to: str, subject: str, html_content: str) -> bool:
    """Envoie un email avec logo intégré."""
    from email.mime.image import MIMEImage
    import base64

    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("smtp_not_configured", subject=subject)
        backup_path = LOGS_DIR / f"email_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        with open(backup_path, "w") as f:
            f.write(html_content)
        logger.info("email_saved_locally", path=str(backup_path))
        return False

    try:
        # Utiliser "related" pour permettre les images intégrées
        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to

        # Remplacer les références au logo par le CID
        html_content = html_content.replace("__LOGO_URL__", "cid:azalplus_logo")

        # Créer la partie HTML
        html_part = MIMEMultipart("alternative")
        html_part.attach(MIMEText(html_content, "html"))
        msg.attach(html_part)

        # Attacher le logo PNG (dynamique selon APP_NAME)
        app_name = os.environ.get("APP_NAME", "AZALPLUS")
        app_name_lower = app_name.lower()
        # Chercher le logo dans plusieurs emplacements possibles
        logo_paths = [
            Path(f"/home/ubuntu/{app_name_lower}/assets/logo.png"),
            Path(f"/home/ubuntu/{app_name_lower}/static/logo.png"),
            Path(f"/home/ubuntu/{app_name_lower}/docs/logo-{app_name_lower}-full.png"),
            Path("/home/ubuntu/azalplus/static/logo.png"),
            Path("/home/ubuntu/azalplus/docs/logo-azalplus-full.png"),
        ]
        logo_path = None
        for path in logo_paths:
            if path.exists():
                logo_path = path
                break
        if logo_path and logo_path.exists():
            with open(logo_path, "rb") as f:
                logo_data = f.read()
            logo_img = MIMEImage(logo_data, _subtype="png")
            logo_img.add_header("Content-ID", "<azalplus_logo>")
            logo_img.add_header("Content-Disposition", "inline", filename=f"logo-{app_name_lower}.png")
            msg.attach(logo_img)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, to, msg.as_string())

        logger.info("email_sent", to=to, subject=subject)
        return True
    except Exception as e:
        logger.error("email_send_failed", to=to, subject=subject, error=str(e))
        return False


def send_daily_report():
    """Envoie le rapport journalier."""
    yesterday = datetime.now() - timedelta(days=1)
    report = generate_daily_report(yesterday)
    subject = f"[AZALPLUS] Rapport Sécurité - {yesterday.strftime('%d/%m/%Y')}"
    send_email(ALERT_EMAIL, subject, report)


def send_alert(event: SecurityEvent):
    """Envoie une alerte pour un événement."""
    alert = generate_alert_email(event)
    status = "BLOQUÉE" if event.blocked else "⚠️ INTRUSION"
    subject = f"[AZALPLUS ALERT] {event.severity} - {event.attack_type} ({status})"
    send_email(ALERT_EMAIL, subject, alert)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python security_alerts.py [daily|test|watch]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "daily":
        send_daily_report()
    elif command == "test":
        # Test avec les données d'aujourd'hui
        report = generate_daily_report(datetime.now())
        print(report)
    elif command == "watch":
        print("Mode surveillance non implémenté dans ce script.")
        print("Utilisez security_watcher.py pour la surveillance temps réel.")
    else:
        print(f"Commande inconnue: {command}")
