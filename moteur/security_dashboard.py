#!/usr/bin/env python3
"""
Génère les données JSON pour le dashboard de sécurité.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

from security_alerts import (
    analyze_logs, get_ip_info, get_ip_flag,
    enrich_ip_with_abuse, LOGS_DIR
)

OUTPUT_FILE = Path("/home/ubuntu/azalplus/docs/security-data.json")


def generate_dashboard_data():
    """Génère les données du dashboard."""
    # Analyser les logs des dernières 24h
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    events_today = analyze_logs(today)
    events_yesterday = analyze_logs(yesterday)
    events = events_today + events_yesterday

    # Filtrer les dernières 24h
    cutoff = datetime.now() - timedelta(hours=24)
    events = [e for e in events if e.timestamp > cutoff]

    # Statistiques
    total = len(events)
    blocked = sum(1 for e in events if e.blocked)
    passed = total - blocked

    # Par IP
    by_ip = defaultdict(int)
    for e in events:
        by_ip[e.ip] += 1

    unique_ips = len(by_ip)

    # Top 10 IPs avec enrichissement
    top_ips_raw = sorted(by_ip.items(), key=lambda x: x[1], reverse=True)[:10]
    top_ips = []

    for ip, count in top_ips_raw:
        if ip == "127.0.0.1":
            continue

        ip_info = get_ip_info(ip)
        ip_info = enrich_ip_with_abuse(ip_info)

        top_ips.append({
            "ip": ip,
            "count": count,
            "country": ip_info.country,
            "city": ip_info.city if ip_info.city != "Inconnu" else "",
            "flag": get_ip_flag(ip_info.country_code),
            "isp": ip_info.isp,
            "is_vpn": ip_info.is_proxy,
            "is_hosting": ip_info.is_hosting,
            "abuse_score": ip_info.abuse_score,
            "abuse_reports": ip_info.abuse_reports,
        })

    # Derniers événements
    events_data = []
    ip_cache = {}

    for e in sorted(events, key=lambda x: x.timestamp, reverse=True)[:100]:
        if e.ip not in ip_cache:
            info = get_ip_info(e.ip)
            ip_cache[e.ip] = get_ip_flag(info.country_code)

        events_data.append({
            "time": e.timestamp.strftime("%H:%M:%S"),
            "ip": e.ip,
            "flag": ip_cache[e.ip],
            "attack_type": e.attack_type,
            "path": e.path[:50],
            "severity": e.severity,
            "blocked": e.blocked,
        })

    # Données finales
    data = {
        "generated_at": datetime.now().isoformat(),
        "total": total,
        "blocked": blocked,
        "passed": passed,
        "unique_ips": unique_ips,
        "top_ips": top_ips,
        "events": events_data,
    }

    # Sauvegarder
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(
        "dashboard_data_generated",
        output_file=str(OUTPUT_FILE),
        total=total,
        blocked=blocked,
        unique_ips=unique_ips
    )

    return data


if __name__ == "__main__":
    generate_dashboard_data()
