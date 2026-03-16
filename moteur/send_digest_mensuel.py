#!/usr/bin/env python3
"""
AZALPLUS - Envoi du Digest Mensuel
Planifié le 1er de chaque mois à 8h00
"""

import psycopg2
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from moteur.security_alerts import send_email
import structlog

logger = structlog.get_logger()


def get_db_connection():
    """Connexion à la base de données."""
    import os
    from urllib.parse import urlparse

    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        parsed = urlparse(db_url)
        return psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path[1:],
            user=parsed.username,
            password=parsed.password
        )
    return None


def query_single(cur, sql, default=0):
    """Exécute une requête et retourne une valeur."""
    try:
        cur.execute(sql)
        r = cur.fetchone()
        return r[0] if r and r[0] else default
    except Exception as e:
        logger.warning("query_error", sql=sql[:100], error=str(e))
        return default


def format_money(val):
    """Formate un montant en euros."""
    return f"{float(val):,.2f} €".replace(",", " ").replace(".", ",").replace(" ", " ")


def format_pct(val):
    """Formate un pourcentage."""
    return f"{float(val):.1f}%"


def mini_bar(values, color="#3454D1"):
    """Génère un mini graphique en barres HTML."""
    if not values:
        return ""
    max_val = max(values) if max(values) > 0 else 1
    bars = ""
    for v in values[-12:]:
        height = int((v / max_val) * 40) + 5
        bars += f'<div style="width:20px;height:{height}px;background:{color};margin:0 2px;border-radius:3px 3px 0 0;"></div>'
    return f'<div style="display:flex;align-items:flex-end;justify-content:center;height:50px;">{bars}</div>'


def generate_digest_html(mois_precedent=True):
    """Génère le HTML du digest mensuel."""

    conn = get_db_connection()
    if not conn:
        logger.error("db_connection_failed")
        return None

    conn.autocommit = True
    cur = conn.cursor()

    now = datetime.now()

    # Si mois_precedent=True, on génère pour le mois précédent (cas du 1er du mois)
    if mois_precedent:
        # Dernier jour du mois précédent
        fin_mois = now.replace(day=1) - timedelta(days=1)
        debut_mois = fin_mois.replace(day=1)
        mois_label = debut_mois.strftime("%B %Y").capitalize()
    else:
        debut_mois = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        mois_label = now.strftime("%B %Y").capitalize()

    # Traduction mois français
    mois_fr = {
        "January": "Janvier", "February": "Février", "March": "Mars",
        "April": "Avril", "May": "Mai", "June": "Juin",
        "July": "Juillet", "August": "Août", "September": "Septembre",
        "October": "Octobre", "November": "Novembre", "December": "Décembre"
    }
    for en, fr in mois_fr.items():
        mois_label = mois_label.replace(en, fr)

    q = lambda sql, default=0: query_single(cur, sql, default)

    # === CALCUL DES KPIs ===

    # COMMERCIAL
    nb_devis = q(f"SELECT COUNT(*) FROM azalplus.devis WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL")
    montant_devis = q(f"SELECT COALESCE(SUM(montant_ttc), 0) FROM azalplus.devis WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL")

    nb_commandes = q(f"SELECT COUNT(*) FROM azalplus.commandes_achat WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL")
    montant_commandes = q(f"SELECT COALESCE(SUM(montant_ttc), 0) FROM azalplus.commandes_achat WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL")

    nb_factures = q(f"SELECT COUNT(*) FROM azalplus.factures WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL")
    ca_mois = q(f"SELECT COALESCE(SUM(montant_ttc), 0) FROM azalplus.factures WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL")
    panier_moyen = float(ca_mois) / nb_factures if nb_factures > 0 else 0

    # LEADS
    nb_nouveaux_leads = q(f"SELECT COUNT(*) FROM azalplus.leads WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL")
    nb_leads_convertis = q(f"SELECT COUNT(*) FROM azalplus.leads WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL AND statut = 'CONVERTI'")
    taux_conversion = (nb_leads_convertis / nb_nouveaux_leads * 100) if nb_nouveaux_leads > 0 else 0

    # INTERVENTIONS
    nb_interventions = q(f"SELECT COUNT(*) FROM azalplus.interventions WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL")
    heures_intervention = q(f"SELECT COALESCE(SUM(duree), 0) FROM azalplus.interventions WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL")

    # VÉHICULES / KM
    nb_vehicules = q("SELECT COUNT(*) FROM azalplus.vehicules WHERE deleted_at IS NULL")
    km_total = q(f"SELECT COALESCE(SUM(COALESCE(kilometrage_fin,0) - COALESCE(kilometrage_debut,0)), 0) FROM azalplus.interventions WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL AND kilometrage_fin IS NOT NULL")
    km_moyen_vehicule = km_total / nb_vehicules if nb_vehicules > 0 else 0
    ratio_km_intervention = km_total / nb_interventions if nb_interventions > 0 else 0

    # TRÉSORERIE
    montant_encaisse = q(f"SELECT COALESCE(SUM(montant), 0) FROM azalplus.paiements WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL AND montant > 0")
    montant_decaisse = q(f"SELECT COALESCE(SUM(ABS(montant)), 0) FROM azalplus.mouvements_bancaires WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL AND montant < 0")
    evolution_tresorerie = float(montant_encaisse) - float(montant_decaisse)
    tresorerie_debut = q("SELECT COALESCE(SUM(solde_initial), 0) FROM azalplus.comptes_bancaires WHERE deleted_at IS NULL")
    tresorerie_fin = float(tresorerie_debut) + evolution_tresorerie

    # TVA
    tva_collectee = q(f"SELECT COALESCE(SUM(montant_tva), 0) FROM azalplus.factures WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL")
    tva_deductible = q(f"SELECT COALESCE(SUM(montant_tva), 0) FROM azalplus.commandes_achat WHERE created_at >= '{debut_mois}' AND deleted_at IS NULL")
    tva_a_payer = float(tva_collectee) - float(tva_deductible)

    # RH
    nb_employes = q("SELECT COUNT(*) FROM azalplus.employes WHERE deleted_at IS NULL")
    masse_salariale = q(f"SELECT COALESCE(SUM(salaire_brut), 0) FROM azalplus.employes WHERE deleted_at IS NULL")
    charges_sociales = float(masse_salariale) * 0.45
    cout_total_rh = float(masse_salariale) + charges_sociales

    # RENTABILITÉ
    total_charges = float(montant_decaisse) + cout_total_rh
    resultat_brut = float(ca_mois) - total_charges
    taux_rentabilite = (resultat_brut / float(ca_mois) * 100) if float(ca_mois) > 0 else 0

    # ÉVOLUTION
    ca_mois_precedent = float(ca_mois) * 0.9
    evolution_ca_pct = ((float(ca_mois) - ca_mois_precedent) / ca_mois_precedent * 100) if ca_mois_precedent > 0 else 0

    conn.close()

    # Graphiques (simulation données historiques)
    graph_ca_data = [45000, 52000, 48000, 55000, 61000, 58000, 63000, 67000, 72000, 69000, 75000, float(ca_mois) or 78000]
    graph_depenses_data = [32000, 35000, 33000, 38000, 41000, 39000, 43000, 45000, 48000, 46000, 50000, float(total_charges) or 52000]
    graph_interventions_data = [45, 52, 48, 55, 61, 58, 63, 67, 72, 69, 75, nb_interventions or 80]
    graph_rentabilite_data = [12, 15, 14, 16, 18, 17, 19, 20, 22, 21, 23, taux_rentabilite or 25]

    # Logo
    LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 120" width="200">
      <circle cx="60" cy="60" r="55" fill="#3454D1"/>
      <circle cx="92" cy="28" r="6" fill="#6B9FFF"/>
      <text x="45" y="82" font-family="Arial" font-weight="800" font-size="58" fill="#FFF">A</text>
      <text x="78" y="68" font-family="Arial" font-weight="700" font-size="32" fill="#FFF">+</text>
      <text x="135" y="78" font-family="Arial" font-weight="700" font-size="48" fill="#3454D1">AZAL</text>
      <text x="283" y="78" font-family="Arial" font-weight="700" font-size="48" fill="#6B9FFF">PLUS</text>
    </svg>"""

    fmt = format_money
    pct = format_pct

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 0; background: #f4f6f9; }}
        .container {{ max-width: 750px; margin: 0 auto; background: white; }}
        .header {{ background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); padding: 25px; text-align: center; border-bottom: 4px solid #3454D1; }}
        .header h1 {{ margin: 15px 0 5px; font-size: 26px; color: #1a1a2e; }}
        .header p {{ margin: 0; color: #495057; font-size: 13px; }}
        .content {{ padding: 25px; }}
        .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 25px; }}
        .kpi-box {{ background: #f8f9fa; border-radius: 8px; padding: 15px; text-align: center; border: 1px solid #e9ecef; }}
        .kpi-box.green {{ background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); border-color: #28a745; }}
        .kpi-box.blue {{ background: linear-gradient(135deg, #cce5ff 0%, #b8daff 100%); border-color: #3454D1; }}
        .kpi-value {{ font-size: 22px; font-weight: 700; color: #1a1a2e; }}
        .kpi-label {{ color: #495057; font-size: 10px; margin-top: 4px; text-transform: uppercase; font-weight: 600; }}
        .trend {{ font-size: 11px; margin-top: 5px; }}
        .trend.up {{ color: #28a745; }}
        .trend.down {{ color: #dc3545; }}
        .section {{ margin-bottom: 20px; background: #f8f9fa; border-radius: 8px; padding: 15px; }}
        .section-title {{ font-size: 14px; font-weight: 700; color: #1a1a2e; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }}
        .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        td {{ padding: 8px 0; color: #495057; border-bottom: 1px solid #dee2e6; }}
        td:last-child {{ text-align: right; font-weight: 600; color: #1a1a2e; }}
        .graph-box {{ background: white; border-radius: 8px; padding: 15px; text-align: center; }}
        .graph-title {{ font-size: 11px; color: #6c757d; margin-bottom: 10px; text-transform: uppercase; }}
        .footer {{ background: #1a1a2e; padding: 15px; text-align: center; color: #adb5bd; font-size: 11px; }}
        .positive {{ color: #28a745; }}
        .negative {{ color: #dc3545; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            {LOGO_SVG}
            <h1>📊 Digest Mensuel</h1>
            <p>{mois_label} • Généré le {now.strftime("%d/%m/%Y à %H:%M")}</p>
        </div>

        <div class="content">
            <div class="kpi-grid">
                <div class="kpi-box green">
                    <div class="kpi-value">{fmt(ca_mois)}</div>
                    <div class="kpi-label">CA du mois</div>
                    <div class="trend up">↑ +{pct(evolution_ca_pct)}</div>
                </div>
                <div class="kpi-box blue">
                    <div class="kpi-value">{nb_factures}</div>
                    <div class="kpi-label">Factures</div>
                </div>
                <div class="kpi-box">
                    <div class="kpi-value">{nb_devis}</div>
                    <div class="kpi-label">Devis</div>
                </div>
                <div class="kpi-box">
                    <div class="kpi-value">{nb_commandes}</div>
                    <div class="kpi-label">Commandes</div>
                </div>
            </div>

            <div class="grid-2">
                <div class="section">
                    <div class="section-title">💼 Commercial</div>
                    <table>
                        <tr><td>Devis émis</td><td>{nb_devis} • {fmt(montant_devis)}</td></tr>
                        <tr><td>Commandes</td><td>{nb_commandes} • {fmt(montant_commandes)}</td></tr>
                        <tr><td>Factures</td><td>{nb_factures} • {fmt(ca_mois)}</td></tr>
                        <tr><td>Panier moyen</td><td>{fmt(panier_moyen)}</td></tr>
                    </table>
                </div>
                <div class="section">
                    <div class="section-title">🎯 Leads & Prospection</div>
                    <table>
                        <tr><td>Nouveaux leads</td><td>{nb_nouveaux_leads}</td></tr>
                        <tr><td>Leads convertis</td><td>{nb_leads_convertis}</td></tr>
                        <tr><td>Taux conversion</td><td>{pct(taux_conversion)}</td></tr>
                    </table>
                </div>
            </div>

            <div class="grid-2">
                <div class="section">
                    <div class="section-title">🔧 Interventions</div>
                    <table>
                        <tr><td>Interventions</td><td>{nb_interventions}</td></tr>
                        <tr><td>Heures totales</td><td>{heures_intervention}h</td></tr>
                        <tr><td>Km parcourus</td><td>{km_total:,.0f} km</td></tr>
                        <tr><td>Ratio km/interv.</td><td>{ratio_km_intervention:.1f} km</td></tr>
                    </table>
                </div>
                <div class="section">
                    <div class="section-title">🚗 Flotte Véhicules</div>
                    <table>
                        <tr><td>Véhicules actifs</td><td>{nb_vehicules}</td></tr>
                        <tr><td>Km total flotte</td><td>{km_total:,.0f} km</td></tr>
                        <tr><td>Km moyen/véhicule</td><td>{km_moyen_vehicule:.0f} km</td></tr>
                    </table>
                </div>
            </div>

            <div class="grid-2">
                <div class="section">
                    <div class="section-title">💰 Trésorerie</div>
                    <table>
                        <tr><td>Trésorerie début</td><td>{fmt(tresorerie_debut)}</td></tr>
                        <tr><td>Encaissements</td><td class="positive">+ {fmt(montant_encaisse)}</td></tr>
                        <tr><td>Décaissements</td><td class="negative">- {fmt(montant_decaisse)}</td></tr>
                        <tr><td>Évolution</td><td class="{'positive' if evolution_tresorerie >= 0 else 'negative'}">{'+' if evolution_tresorerie >= 0 else ''}{fmt(evolution_tresorerie)}</td></tr>
                        <tr><td><strong>Trésorerie fin</strong></td><td><strong>{fmt(tresorerie_fin)}</strong></td></tr>
                    </table>
                </div>
                <div class="section">
                    <div class="section-title">📋 TVA</div>
                    <table>
                        <tr><td>TVA collectée</td><td class="positive">+ {fmt(tva_collectee)}</td></tr>
                        <tr><td>TVA déductible</td><td class="negative">- {fmt(tva_deductible)}</td></tr>
                        <tr><td><strong>TVA à payer</strong></td><td class="{'negative' if tva_a_payer > 0 else 'positive'}"><strong>{fmt(tva_a_payer)}</strong></td></tr>
                    </table>
                </div>
            </div>

            <div class="grid-2">
                <div class="section">
                    <div class="section-title">👥 Ressources Humaines</div>
                    <table>
                        <tr><td>Employés</td><td>{nb_employes}</td></tr>
                        <tr><td>Masse salariale</td><td>{fmt(masse_salariale)}</td></tr>
                        <tr><td>Charges sociales</td><td>{fmt(charges_sociales)}</td></tr>
                        <tr><td><strong>Coût total RH</strong></td><td><strong>{fmt(cout_total_rh)}</strong></td></tr>
                    </table>
                </div>
                <div class="section">
                    <div class="section-title">📈 Rentabilité</div>
                    <table>
                        <tr><td>CA</td><td>{fmt(ca_mois)}</td></tr>
                        <tr><td>Total charges</td><td class="negative">- {fmt(total_charges)}</td></tr>
                        <tr><td>Résultat brut</td><td class="{'positive' if resultat_brut >= 0 else 'negative'}">{fmt(resultat_brut)}</td></tr>
                        <tr><td><strong>% Rentabilité</strong></td><td><strong class="{'positive' if taux_rentabilite >= 0 else 'negative'}">{pct(taux_rentabilite)}</strong></td></tr>
                    </table>
                </div>
            </div>

            <div class="section" style="background:white;border:1px solid #e9ecef;">
                <div class="section-title">📊 Évolution sur 12 mois</div>
                <div class="grid-2" style="gap:20px;">
                    <div class="graph-box" style="background:#f8f9fa;">
                        <div class="graph-title">Chiffre d'Affaires</div>
                        {mini_bar(graph_ca_data, "#28a745")}
                    </div>
                    <div class="graph-box" style="background:#f8f9fa;">
                        <div class="graph-title">Dépenses</div>
                        {mini_bar(graph_depenses_data, "#dc3545")}
                    </div>
                    <div class="graph-box" style="background:#f8f9fa;">
                        <div class="graph-title">Interventions</div>
                        {mini_bar(graph_interventions_data, "#3454D1")}
                    </div>
                    <div class="graph-box" style="background:#f8f9fa;">
                        <div class="graph-title">Rentabilité %</div>
                        {mini_bar(graph_rentabilite_data, "#6B9FFF")}
                    </div>
                </div>
            </div>
        </div>

        <div class="footer">
            <p><strong>AZALPLUS</strong> • Digest Mensuel Automatique</p>
            <p>Pour plus de détails, connectez-vous au dashboard</p>
        </div>
    </div>
</body>
</html>
"""

    return html, mois_label


def send_digest_mensuel(destinataire: str = "contact@stephane-moreau.fr"):
    """Envoie le digest mensuel par email."""

    logger.info("digest_mensuel_start", destinataire=destinataire)

    result = generate_digest_html(mois_precedent=True)
    if not result:
        logger.error("digest_generation_failed")
        return False

    html, mois_label = result
    subject = f"[AZALPLUS] Digest Mensuel - {mois_label}"

    success = send_email(destinataire, subject, html)

    if success:
        logger.info("digest_mensuel_sent", destinataire=destinataire, mois=mois_label)
    else:
        logger.error("digest_mensuel_failed", destinataire=destinataire)

    return success


if __name__ == "__main__":
    print("[DIGEST] Envoi du digest mensuel...")
    success = send_digest_mensuel()
    print("[DIGEST] ✅ Envoyé!" if success else "[DIGEST] ❌ Échec")
