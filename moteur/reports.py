# =============================================================================
# AZALPLUS - Reporting Engine
# =============================================================================
"""
Moteur de rapports et statistiques.
- Rapports de ventes (CA, factures, devis)
- Rapports clients (acquisition, top clients)
- Rapports interventions (statistiques par statut, technicien)
- Export PDF et CSV
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID as PyUUID
import csv
import io
import structlog

from .db import Database
from sqlalchemy import text

logger = structlog.get_logger()


# =============================================================================
# ReportEngine Class
# =============================================================================
class ReportEngine:
    """Moteur de generation de rapports avec isolation tenant."""

    def __init__(self, tenant_id: PyUUID):
        """
        Initialise le moteur de rapports.

        Args:
            tenant_id: ID du tenant (isolation obligatoire)
        """
        self.tenant_id = tenant_id

    # =========================================================================
    # Rapport Ventes
    # =========================================================================
    def generate_sales_report(
        self,
        date_from: date,
        date_to: date
    ) -> Dict[str, Any]:
        """
        Genere un rapport de ventes complet.

        Args:
            date_from: Date de debut
            date_to: Date de fin

        Returns:
            Dict contenant:
            - revenue: Chiffre d'affaires total
            - invoices: Stats factures
            - quotes: Stats devis
            - revenue_by_month: CA par mois
            - top_products: Produits les plus vendus
        """
        with Database.get_session() as session:
            # --- Chiffre d'affaires (factures payees) ---
            revenue_query = text('''
                SELECT
                    COALESCE(SUM(CAST(total_ttc AS NUMERIC)), 0) as total_revenue,
                    COUNT(*) as total_invoices,
                    COALESCE(SUM(CASE WHEN statut = 'PAYEE' THEN CAST(total_ttc AS NUMERIC) ELSE 0 END), 0) as paid_revenue,
                    COUNT(CASE WHEN statut = 'PAYEE' THEN 1 END) as paid_count,
                    COUNT(CASE WHEN statut = 'ENVOYEE' THEN 1 END) as pending_count,
                    COALESCE(SUM(CASE WHEN statut = 'ENVOYEE' THEN CAST(total_ttc AS NUMERIC) ELSE 0 END), 0) as pending_amount
                FROM azalplus.factures
                WHERE tenant_id = :tenant_id
                AND deleted_at IS NULL
                AND date >= :date_from
                AND date <= :date_to
            ''')

            revenue_result = session.execute(revenue_query, {
                "tenant_id": str(self.tenant_id),
                "date_from": date_from,
                "date_to": date_to
            }).fetchone()

            # --- Stats devis ---
            quotes_query = text('''
                SELECT
                    COUNT(*) as total_quotes,
                    COUNT(CASE WHEN statut = 'ACCEPTE' THEN 1 END) as accepted_count,
                    COUNT(CASE WHEN statut = 'REFUSE' THEN 1 END) as refused_count,
                    COUNT(CASE WHEN statut = 'ENVOYE' THEN 1 END) as sent_count,
                    COUNT(CASE WHEN statut = 'BROUILLON' THEN 1 END) as draft_count,
                    COALESCE(SUM(CAST(total_ttc AS NUMERIC)), 0) as total_amount,
                    COALESCE(SUM(CASE WHEN statut = 'ACCEPTE' THEN CAST(total_ttc AS NUMERIC) ELSE 0 END), 0) as accepted_amount
                FROM azalplus.devis
                WHERE tenant_id = :tenant_id
                AND deleted_at IS NULL
                AND date >= :date_from
                AND date <= :date_to
            ''')

            quotes_result = session.execute(quotes_query, {
                "tenant_id": str(self.tenant_id),
                "date_from": date_from,
                "date_to": date_to
            }).fetchone()

            # --- CA par mois ---
            monthly_query = text('''
                SELECT
                    DATE_TRUNC('month', date) as month,
                    COALESCE(SUM(CAST(total_ttc AS NUMERIC)), 0) as revenue,
                    COUNT(*) as invoice_count
                FROM azalplus.factures
                WHERE tenant_id = :tenant_id
                AND deleted_at IS NULL
                AND date >= :date_from
                AND date <= :date_to
                AND statut IN ('PAYEE', 'ENVOYEE', 'VALIDEE')
                GROUP BY DATE_TRUNC('month', date)
                ORDER BY month
            ''')

            monthly_result = session.execute(monthly_query, {
                "tenant_id": str(self.tenant_id),
                "date_from": date_from,
                "date_to": date_to
            }).fetchall()

            # Calcul du taux de conversion devis
            total_quotes = quotes_result.total_quotes if quotes_result else 0
            accepted_quotes = quotes_result.accepted_count if quotes_result else 0
            conversion_rate = (accepted_quotes / total_quotes * 100) if total_quotes > 0 else 0

            return {
                "period": {
                    "from": date_from.isoformat(),
                    "to": date_to.isoformat()
                },
                "revenue": {
                    "total": float(revenue_result.total_revenue or 0),
                    "paid": float(revenue_result.paid_revenue or 0),
                    "pending": float(revenue_result.pending_amount or 0)
                },
                "invoices": {
                    "total": revenue_result.total_invoices or 0,
                    "paid": revenue_result.paid_count or 0,
                    "pending": revenue_result.pending_count or 0
                },
                "quotes": {
                    "total": total_quotes,
                    "accepted": accepted_quotes,
                    "refused": quotes_result.refused_count if quotes_result else 0,
                    "pending": quotes_result.sent_count if quotes_result else 0,
                    "draft": quotes_result.draft_count if quotes_result else 0,
                    "total_amount": float(quotes_result.total_amount or 0),
                    "accepted_amount": float(quotes_result.accepted_amount or 0),
                    "conversion_rate": round(conversion_rate, 1)
                },
                "revenue_by_month": [
                    {
                        "month": row.month.strftime("%Y-%m") if row.month else "",
                        "month_label": row.month.strftime("%b %Y") if row.month else "",
                        "revenue": float(row.revenue or 0),
                        "invoice_count": row.invoice_count or 0
                    }
                    for row in monthly_result
                ]
            }

    # =========================================================================
    # Rapport Clients
    # =========================================================================
    def generate_client_report(self) -> Dict[str, Any]:
        """
        Genere un rapport sur les clients.

        Returns:
            Dict contenant:
            - total_clients: Nombre total de clients
            - new_clients_this_month: Nouveaux clients ce mois
            - top_clients: Top 10 clients par CA
            - clients_by_type: Repartition par type
            - acquisition_by_month: Acquisition par mois
        """
        today = date.today()
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        with Database.get_session() as session:
            # --- Comptage total clients ---
            count_query = text('''
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN actif = true THEN 1 END) as active,
                    COUNT(CASE WHEN type = 'PROFESSIONNEL' THEN 1 END) as pro,
                    COUNT(CASE WHEN type = 'PARTICULIER' THEN 1 END) as particulier,
                    COUNT(CASE WHEN created_at >= :month_start THEN 1 END) as new_this_month,
                    COUNT(CASE WHEN created_at >= :year_start THEN 1 END) as new_this_year
                FROM azalplus.clients
                WHERE tenant_id = :tenant_id
                AND deleted_at IS NULL
            ''')

            count_result = session.execute(count_query, {
                "tenant_id": str(self.tenant_id),
                "month_start": month_start,
                "year_start": year_start
            }).fetchone()

            # --- Top clients par CA ---
            top_query = text('''
                SELECT
                    c.id,
                    c.nom,
                    c.raison_sociale,
                    c.email,
                    c.type,
                    COALESCE(SUM(CAST(f.total_ttc AS NUMERIC)), 0) as total_ca,
                    COUNT(f.id) as invoice_count
                FROM azalplus.clients c
                LEFT JOIN azalplus.factures f ON f.client = c.id
                    AND f.tenant_id = c.tenant_id
                    AND f.deleted_at IS NULL
                    AND f.statut IN ('PAYEE', 'ENVOYEE', 'VALIDEE')
                WHERE c.tenant_id = :tenant_id
                AND c.deleted_at IS NULL
                GROUP BY c.id, c.nom, c.raison_sociale, c.email, c.type
                ORDER BY total_ca DESC
                LIMIT 10
            ''')

            top_result = session.execute(top_query, {
                "tenant_id": str(self.tenant_id)
            }).fetchall()

            # --- Acquisition par mois (12 derniers mois) ---
            acquisition_query = text('''
                SELECT
                    DATE_TRUNC('month', created_at) as month,
                    COUNT(*) as new_clients
                FROM azalplus.clients
                WHERE tenant_id = :tenant_id
                AND deleted_at IS NULL
                AND created_at >= :start_date
                GROUP BY DATE_TRUNC('month', created_at)
                ORDER BY month
            ''')

            acquisition_result = session.execute(acquisition_query, {
                "tenant_id": str(self.tenant_id),
                "start_date": today - timedelta(days=365)
            }).fetchall()

            return {
                "summary": {
                    "total": count_result.total or 0,
                    "active": count_result.active or 0,
                    "new_this_month": count_result.new_this_month or 0,
                    "new_this_year": count_result.new_this_year or 0
                },
                "by_type": {
                    "professionnel": count_result.pro or 0,
                    "particulier": count_result.particulier or 0
                },
                "top_clients": [
                    {
                        "id": str(row.id),
                        "nom": row.raison_sociale or row.nom or "N/A",
                        "email": row.email,
                        "type": row.type,
                        "total_ca": float(row.total_ca or 0),
                        "invoice_count": row.invoice_count or 0
                    }
                    for row in top_result
                ],
                "acquisition_by_month": [
                    {
                        "month": row.month.strftime("%Y-%m") if row.month else "",
                        "month_label": row.month.strftime("%b %Y") if row.month else "",
                        "new_clients": row.new_clients or 0
                    }
                    for row in acquisition_result
                ]
            }

    # =========================================================================
    # Rapport Interventions
    # =========================================================================
    def generate_intervention_report(
        self,
        date_from: date,
        date_to: date
    ) -> Dict[str, Any]:
        """
        Genere un rapport sur les interventions.

        Args:
            date_from: Date de debut
            date_to: Date de fin

        Returns:
            Dict contenant:
            - total_interventions: Nombre total
            - by_status: Repartition par statut
            - by_type: Repartition par type
            - by_priority: Repartition par priorite
            - by_technician: Stats par technicien
            - average_duration: Duree moyenne
        """
        with Database.get_session() as session:
            # --- Stats globales ---
            global_query = text('''
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN statut = 'TERMINEE' THEN 1 END) as completed,
                    COUNT(CASE WHEN statut = 'EN_COURS' THEN 1 END) as in_progress,
                    COUNT(CASE WHEN statut = 'PLANIFIEE' THEN 1 END) as planned,
                    COUNT(CASE WHEN statut = 'A_PLANIFIER' THEN 1 END) as to_plan,
                    COUNT(CASE WHEN statut = 'BLOQUEE' THEN 1 END) as blocked,
                    COUNT(CASE WHEN statut = 'ANNULEE' THEN 1 END) as cancelled,
                    AVG(CAST(duree_reelle AS NUMERIC)) as avg_duration,
                    SUM(CAST(duree_reelle AS NUMERIC)) as total_duration
                FROM azalplus.interventions
                WHERE tenant_id = :tenant_id
                AND deleted_at IS NULL
                AND (date_debut >= :date_from OR date_souhaitee >= :date_from)
                AND (date_debut <= :date_to OR date_souhaitee <= :date_to)
            ''')

            global_result = session.execute(global_query, {
                "tenant_id": str(self.tenant_id),
                "date_from": date_from,
                "date_to": date_to
            }).fetchone()

            # --- Par type ---
            type_query = text('''
                SELECT
                    COALESCE(type, 'AUTRE') as type,
                    COUNT(*) as count
                FROM azalplus.interventions
                WHERE tenant_id = :tenant_id
                AND deleted_at IS NULL
                AND (date_debut >= :date_from OR date_souhaitee >= :date_from)
                AND (date_debut <= :date_to OR date_souhaitee <= :date_to)
                GROUP BY type
                ORDER BY count DESC
            ''')

            type_result = session.execute(type_query, {
                "tenant_id": str(self.tenant_id),
                "date_from": date_from,
                "date_to": date_to
            }).fetchall()

            # --- Par priorite ---
            priority_query = text('''
                SELECT
                    COALESCE(priorite, 'NORMALE') as priorite,
                    COUNT(*) as count
                FROM azalplus.interventions
                WHERE tenant_id = :tenant_id
                AND deleted_at IS NULL
                AND (date_debut >= :date_from OR date_souhaitee >= :date_from)
                AND (date_debut <= :date_to OR date_souhaitee <= :date_to)
                GROUP BY priorite
                ORDER BY
                    CASE priorite
                        WHEN 'URGENTE' THEN 1
                        WHEN 'HAUTE' THEN 2
                        WHEN 'NORMALE' THEN 3
                        WHEN 'BASSE' THEN 4
                        ELSE 5
                    END
            ''')

            priority_result = session.execute(priority_query, {
                "tenant_id": str(self.tenant_id),
                "date_from": date_from,
                "date_to": date_to
            }).fetchall()

            # --- Interventions par mois ---
            monthly_query = text('''
                SELECT
                    DATE_TRUNC('month', COALESCE(date_debut, date_souhaitee)) as month,
                    COUNT(*) as total,
                    COUNT(CASE WHEN statut = 'TERMINEE' THEN 1 END) as completed
                FROM azalplus.interventions
                WHERE tenant_id = :tenant_id
                AND deleted_at IS NULL
                AND (date_debut >= :date_from OR date_souhaitee >= :date_from)
                AND (date_debut <= :date_to OR date_souhaitee <= :date_to)
                AND COALESCE(date_debut, date_souhaitee) IS NOT NULL
                GROUP BY DATE_TRUNC('month', COALESCE(date_debut, date_souhaitee))
                ORDER BY month
            ''')

            monthly_result = session.execute(monthly_query, {
                "tenant_id": str(self.tenant_id),
                "date_from": date_from,
                "date_to": date_to
            }).fetchall()

            # Calcul du taux de completion
            total = global_result.total or 0
            completed = global_result.completed or 0
            completion_rate = (completed / total * 100) if total > 0 else 0

            return {
                "period": {
                    "from": date_from.isoformat(),
                    "to": date_to.isoformat()
                },
                "summary": {
                    "total": total,
                    "completed": completed,
                    "in_progress": global_result.in_progress or 0,
                    "planned": global_result.planned or 0,
                    "to_plan": global_result.to_plan or 0,
                    "blocked": global_result.blocked or 0,
                    "cancelled": global_result.cancelled or 0,
                    "completion_rate": round(completion_rate, 1)
                },
                "duration": {
                    "average": float(global_result.avg_duration or 0),
                    "total": float(global_result.total_duration or 0)
                },
                "by_status": {
                    "TERMINEE": global_result.completed or 0,
                    "EN_COURS": global_result.in_progress or 0,
                    "PLANIFIEE": global_result.planned or 0,
                    "A_PLANIFIER": global_result.to_plan or 0,
                    "BLOQUEE": global_result.blocked or 0,
                    "ANNULEE": global_result.cancelled or 0
                },
                "by_type": [
                    {"type": row.type, "count": row.count or 0}
                    for row in type_result
                ],
                "by_priority": [
                    {"priority": row.priorite, "count": row.count or 0}
                    for row in priority_result
                ],
                "by_month": [
                    {
                        "month": row.month.strftime("%Y-%m") if row.month else "",
                        "month_label": row.month.strftime("%b %Y") if row.month else "",
                        "total": row.total or 0,
                        "completed": row.completed or 0
                    }
                    for row in monthly_result
                ]
            }

    # =========================================================================
    # Export CSV
    # =========================================================================
    def export_sales_csv(self, date_from: date, date_to: date) -> str:
        """Exporte le rapport de ventes en CSV."""
        report = self.generate_sales_report(date_from, date_to)

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')

        # En-tete
        writer.writerow(['Rapport de Ventes'])
        writer.writerow([f'Periode: {date_from} - {date_to}'])
        writer.writerow([])

        # Resume
        writer.writerow(['Resume'])
        writer.writerow(['Chiffre d\'affaires total', report['revenue']['total']])
        writer.writerow(['CA encaisse', report['revenue']['paid']])
        writer.writerow(['CA en attente', report['revenue']['pending']])
        writer.writerow([])

        # Factures
        writer.writerow(['Factures'])
        writer.writerow(['Total', report['invoices']['total']])
        writer.writerow(['Payees', report['invoices']['paid']])
        writer.writerow(['En attente', report['invoices']['pending']])
        writer.writerow([])

        # Devis
        writer.writerow(['Devis'])
        writer.writerow(['Total', report['quotes']['total']])
        writer.writerow(['Acceptes', report['quotes']['accepted']])
        writer.writerow(['Refuses', report['quotes']['refused']])
        writer.writerow(['Taux de conversion', f"{report['quotes']['conversion_rate']}%"])
        writer.writerow([])

        # CA par mois
        writer.writerow(['CA par mois'])
        writer.writerow(['Mois', 'CA', 'Nb Factures'])
        for row in report['revenue_by_month']:
            writer.writerow([row['month_label'], row['revenue'], row['invoice_count']])

        return output.getvalue()

    def export_clients_csv(self) -> str:
        """Exporte le rapport clients en CSV."""
        report = self.generate_client_report()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')

        # En-tete
        writer.writerow(['Rapport Clients'])
        writer.writerow([])

        # Resume
        writer.writerow(['Resume'])
        writer.writerow(['Total clients', report['summary']['total']])
        writer.writerow(['Clients actifs', report['summary']['active']])
        writer.writerow(['Nouveaux ce mois', report['summary']['new_this_month']])
        writer.writerow(['Nouveaux cette annee', report['summary']['new_this_year']])
        writer.writerow([])

        # Par type
        writer.writerow(['Par type'])
        writer.writerow(['Professionnels', report['by_type']['professionnel']])
        writer.writerow(['Particuliers', report['by_type']['particulier']])
        writer.writerow([])

        # Top clients
        writer.writerow(['Top 10 Clients'])
        writer.writerow(['Nom', 'Email', 'Type', 'CA Total', 'Nb Factures'])
        for client in report['top_clients']:
            writer.writerow([
                client['nom'],
                client['email'],
                client['type'],
                client['total_ca'],
                client['invoice_count']
            ])

        return output.getvalue()

    def export_interventions_csv(self, date_from: date, date_to: date) -> str:
        """Exporte le rapport interventions en CSV."""
        report = self.generate_intervention_report(date_from, date_to)

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')

        # En-tete
        writer.writerow(['Rapport Interventions'])
        writer.writerow([f'Periode: {date_from} - {date_to}'])
        writer.writerow([])

        # Resume
        writer.writerow(['Resume'])
        writer.writerow(['Total interventions', report['summary']['total']])
        writer.writerow(['Terminees', report['summary']['completed']])
        writer.writerow(['En cours', report['summary']['in_progress']])
        writer.writerow(['Planifiees', report['summary']['planned']])
        writer.writerow(['A planifier', report['summary']['to_plan']])
        writer.writerow(['Bloquees', report['summary']['blocked']])
        writer.writerow(['Taux de completion', f"{report['summary']['completion_rate']}%"])
        writer.writerow([])

        # Par type
        writer.writerow(['Par type'])
        writer.writerow(['Type', 'Nombre'])
        for row in report['by_type']:
            writer.writerow([row['type'], row['count']])
        writer.writerow([])

        # Par priorite
        writer.writerow(['Par priorite'])
        writer.writerow(['Priorite', 'Nombre'])
        for row in report['by_priority']:
            writer.writerow([row['priority'], row['count']])

        return output.getvalue()
