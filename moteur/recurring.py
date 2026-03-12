# =============================================================================
# AZALPLUS - Recurring Invoice Engine
# =============================================================================
"""
Moteur de facturation recurrente (abonnements).

Genere automatiquement des factures a partir des abonnements actifs.

PRINCIPES:
- tenant_id OBLIGATOIRE sur chaque operation
- Audit trail complet
- Execution asynchrone
- Gestion des erreurs robuste
- Pas de double facturation
"""

from typing import Dict, Any, List, Optional
from uuid import UUID, uuid4
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from dataclasses import dataclass, field
import json
import structlog

from .db import Database
from .notifications import EmailService
from .pdf import PDFGenerator
from .constants import get, get_statuts, get_statut_defaut, get_tva

# Constantes locales - Statuts abonnements (config/constants.yml > statuts.abonnements)
STATUT_ACTIF = "ACTIF"
STATUT_BROUILLON = "BROUILLON"
STATUT_SUSPENDU = "SUSPENDU"
STATUT_TERMINE = "TERMINE"
STATUT_ANNULE = "ANNULE"

# Statuts factures (config/constants.yml > statuts.factures)
STATUT_FACTURE_VALIDEE = "VALIDEE"

# Fréquences (config/constants.yml > frequences)
FREQ_HEBDOMADAIRE = "hebdomadaire"
FREQ_MENSUEL = "mensuel"
FREQ_TRIMESTRIEL = "trimestriel"
FREQ_SEMESTRIEL = "semestriel"
FREQ_ANNUEL = "annuel"

# Conditions paiement par défaut (config/constants.yml > conditions_paiement)
CONDITION_NET_30 = "NET_30"

# Devise par défaut (config/constants.yml > devises)
DEVISE_EUR = "EUR"

logger = structlog.get_logger()


# =============================================================================
# Types
# =============================================================================
@dataclass
class RecurringResult:
    """Resultat du traitement d'un abonnement."""
    abonnement_id: UUID
    tenant_id: UUID
    success: bool
    facture_id: Optional[UUID] = None
    facture_numero: Optional[str] = None
    error_message: Optional[str] = None
    email_sent: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)


# =============================================================================
# Calcul des dates
# =============================================================================
class DateCalculator:
    """Calcule les dates de prochaine facturation."""

    @staticmethod
    def calculate_next_invoice_date(
        frequence: str,
        jour_facturation: int,
        current_date: date
    ) -> date:
        """
        Calcule la prochaine date de facturation.

        Args:
            frequence: hebdomadaire, mensuel, trimestriel, semestriel, annuel
            jour_facturation: Jour de facturation (1-28 pour mensuel, 1-7 pour hebdomadaire)
            current_date: Date de reference

        Returns:
            Date de prochaine facturation
        """
        # Assurer que jour_facturation est dans les limites
        jour_facturation = max(1, min(jour_facturation, 28))

        if frequence == FREQ_HEBDOMADAIRE:
            # jour_facturation = jour de la semaine (1=lundi, 7=dimanche)
            jour_semaine = max(1, min(jour_facturation, 7))
            days_ahead = jour_semaine - current_date.isoweekday()
            if days_ahead <= 0:
                days_ahead += 7
            return current_date + timedelta(days=days_ahead)

        elif frequence == FREQ_MENSUEL:
            next_month = current_date + relativedelta(months=1)
            # Ajuster si le jour n'existe pas dans le mois
            day = min(jour_facturation, 28)
            return next_month.replace(day=day)

        elif frequence == FREQ_TRIMESTRIEL:
            next_quarter = current_date + relativedelta(months=3)
            day = min(jour_facturation, 28)
            return next_quarter.replace(day=day)

        elif frequence == FREQ_SEMESTRIEL:
            next_half = current_date + relativedelta(months=6)
            day = min(jour_facturation, 28)
            return next_half.replace(day=day)

        elif frequence == FREQ_ANNUEL:
            next_year = current_date + relativedelta(years=1)
            day = min(jour_facturation, 28)
            return next_year.replace(day=day)

        else:
            # Par defaut: mensuel
            next_month = current_date + relativedelta(months=1)
            day = min(jour_facturation, 28)
            return next_month.replace(day=day)

    @staticmethod
    def calculate_due_date(
        invoice_date: date,
        conditions_paiement: str
    ) -> date:
        """
        Calcule la date d'echeance de paiement.

        Args:
            invoice_date: Date de la facture
            conditions_paiement: COMPTANT, NET_15, CONDITION_NET_30, etc.

        Returns:
            Date d'echeance
        """
        # Charger les conditions de paiement depuis constants.yml
        conditions_config = get("conditions_paiement", {})
        conditions_map = {}
        for code, config in conditions_config.items():
            if isinstance(config, dict):
                jours = config.get("jours")
                conditions_map[code] = jours  # None pour FIN_DE_MOIS
            else:
                conditions_map[code] = config

        days = conditions_map.get(conditions_paiement, 30)

        if days is None:
            # Fin du mois suivant
            next_month = invoice_date + relativedelta(months=1)
            # Dernier jour du mois
            return (next_month.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)

        return invoice_date + timedelta(days=days)


# =============================================================================
# Recurring Service
# =============================================================================
class RecurringService:
    """
    Service de facturation recurrente.

    Usage:
        # Traiter tous les abonnements pour tous les tenants
        results = await RecurringService.process_all_due_subscriptions()

        # Traiter les abonnements d'un tenant specifique
        results = await RecurringService.process_due_subscriptions(tenant_id)

        # Generer une facture manuellement
        result = await RecurringService.generate_invoice_for_subscription(
            tenant_id, abonnement_id
        )
    """

    @classmethod
    async def process_all_due_subscriptions(cls) -> List[RecurringResult]:
        """
        Traite tous les abonnements echus pour tous les tenants.

        Cette methode est appelee par le cron job quotidien.

        Returns:
            Liste des resultats de traitement
        """
        all_results = []

        # Recuperer tous les tenants actifs
        tenants = cls._get_all_active_tenants()

        for tenant in tenants:
            tenant_id = UUID(tenant["id"])
            try:
                results = await cls.process_due_subscriptions(tenant_id)
                all_results.extend(results)
            except Exception as e:
                logger.error(
                    "recurring_tenant_error",
                    tenant_id=str(tenant_id),
                    error=str(e)
                )

        logger.info(
            "recurring_all_processed",
            total_tenants=len(tenants),
            total_invoices=len([r for r in all_results if r.success]),
            total_errors=len([r for r in all_results if not r.success])
        )

        return all_results

    @classmethod
    async def process_due_subscriptions(
        cls,
        tenant_id: UUID
    ) -> List[RecurringResult]:
        """
        Traite tous les abonnements echus pour un tenant.

        Args:
            tenant_id: ID du tenant

        Returns:
            Liste des resultats de traitement
        """
        results = []
        today = date.today()

        # Recuperer les abonnements actifs avec facturation due
        abonnements = cls._get_due_subscriptions(tenant_id, today)

        logger.info(
            "recurring_processing",
            tenant_id=str(tenant_id),
            due_count=len(abonnements)
        )

        for abonnement in abonnements:
            try:
                result = await cls.generate_invoice_for_subscription(
                    tenant_id=tenant_id,
                    abonnement_id=UUID(abonnement["id"])
                )
                results.append(result)
            except Exception as e:
                error_result = RecurringResult(
                    abonnement_id=UUID(abonnement["id"]),
                    tenant_id=tenant_id,
                    success=False,
                    error_message=str(e)
                )
                results.append(error_result)
                logger.error(
                    "recurring_invoice_error",
                    tenant_id=str(tenant_id),
                    abonnement_id=abonnement["id"],
                    error=str(e)
                )

        return results

    @classmethod
    async def generate_invoice_for_subscription(
        cls,
        tenant_id: UUID,
        abonnement_id: UUID,
        user_id: Optional[UUID] = None
    ) -> RecurringResult:
        """
        Genere une facture a partir d'un abonnement.

        Args:
            tenant_id: ID du tenant (OBLIGATOIRE)
            abonnement_id: ID de l'abonnement
            user_id: ID de l'utilisateur (optionnel, pour audit)

        Returns:
            Resultat du traitement
        """
        # Recuperer l'abonnement
        abonnement = Database.get_by_id("abonnements", tenant_id, abonnement_id)

        if not abonnement:
            return RecurringResult(
                abonnement_id=abonnement_id,
                tenant_id=tenant_id,
                success=False,
                error_message="Abonnement non trouve"
            )

        # Verifier que l'abonnement est actif
        if abonnement.get("statut") != STATUT_ACTIF:
            return RecurringResult(
                abonnement_id=abonnement_id,
                tenant_id=tenant_id,
                success=False,
                error_message=f"Abonnement non actif (statut: {abonnement.get('statut')})"
            )

        # Verifier que la date de fin n'est pas depassee
        date_fin = abonnement.get("date_fin")
        if date_fin:
            if isinstance(date_fin, str):
                date_fin = datetime.fromisoformat(date_fin).date()
            if date_fin < date.today():
                return RecurringResult(
                    abonnement_id=abonnement_id,
                    tenant_id=tenant_id,
                    success=False,
                    error_message="Abonnement expire"
                )

        # Creer la facture
        try:
            facture_data = cls._build_invoice_data(abonnement, tenant_id)
            facture = Database.insert("factures", tenant_id, facture_data, user_id)
            facture_id = UUID(facture["id"])
            facture_numero = facture.get("numero", str(facture_id)[:8])

            # Mettre a jour l'abonnement
            prochaine_date = DateCalculator.calculate_next_invoice_date(
                frequence=abonnement.get("frequence", "mensuel"),
                jour_facturation=abonnement.get("jour_facturation", 1),
                current_date=date.today()
            )

            update_data = {
                "prochaine_facture": prochaine_date.isoformat(),
                "derniere_facture": date.today().isoformat(),
                "nb_factures_generees": (abonnement.get("nb_factures_generees", 0) or 0) + 1,
                "total_facture": (abonnement.get("total_facture", 0) or 0) + (abonnement.get("montant_ttc", 0) or 0)
            }

            Database.update("abonnements", tenant_id, abonnement_id, update_data)

            # Envoyer l'email si demande
            email_sent = False
            if abonnement.get("envoyer_email") and abonnement.get("client_email"):
                try:
                    await EmailService.send_facture_email(
                        facture_id=facture_id,
                        recipient=abonnement["client_email"],
                        tenant_id=tenant_id,
                        custom_message=f"Facture automatique pour votre abonnement: {abonnement.get('nom', '')}"
                    )
                    email_sent = True
                except Exception as e:
                    logger.warning(
                        "recurring_email_failed",
                        facture_id=str(facture_id),
                        error=str(e)
                    )

            logger.info(
                "recurring_invoice_created",
                tenant_id=str(tenant_id),
                abonnement_id=str(abonnement_id),
                facture_id=str(facture_id),
                facture_numero=facture_numero,
                email_sent=email_sent
            )

            return RecurringResult(
                abonnement_id=abonnement_id,
                tenant_id=tenant_id,
                success=True,
                facture_id=facture_id,
                facture_numero=facture_numero,
                email_sent=email_sent
            )

        except Exception as e:
            logger.error(
                "recurring_invoice_creation_failed",
                tenant_id=str(tenant_id),
                abonnement_id=str(abonnement_id),
                error=str(e)
            )
            return RecurringResult(
                abonnement_id=abonnement_id,
                tenant_id=tenant_id,
                success=False,
                error_message=str(e)
            )

    # =========================================================================
    # Methodes privees
    # =========================================================================
    @classmethod
    def _get_all_active_tenants(cls) -> List[Dict]:
        """Recupere tous les tenants actifs."""
        with Database.get_session() as session:
            from sqlalchemy import text
            result = session.execute(
                text("SELECT id FROM azalplus.tenants WHERE is_active = true")
            )
            return [{"id": str(row[0])} for row in result]

    @classmethod
    def _get_due_subscriptions(
        cls,
        tenant_id: UUID,
        reference_date: date
    ) -> List[Dict]:
        """
        Recupere les abonnements dont la facturation est due.

        Args:
            tenant_id: ID du tenant
            reference_date: Date de reference (generalement aujourd'hui)

        Returns:
            Liste des abonnements a facturer
        """
        with Database.get_session() as session:
            from sqlalchemy import text
            query = text("""
                SELECT * FROM azalplus.abonnements
                WHERE tenant_id = :tenant_id
                AND deleted_at IS NULL
                AND statut = :statut_actif
                AND actif = true
                AND prochaine_facture <= :reference_date
                AND (date_fin IS NULL OR date_fin >= :reference_date)
                ORDER BY prochaine_facture ASC
            """)
            result = session.execute(query, {
                "tenant_id": str(tenant_id),
                "reference_date": reference_date.isoformat(),
                "statut_actif": STATUT_ACTIF
            })
            return [dict(row._mapping) for row in result]

    @classmethod
    def _build_invoice_data(
        cls,
        abonnement: Dict[str, Any],
        tenant_id: UUID
    ) -> Dict[str, Any]:
        """
        Construit les donnees de facture a partir d'un abonnement.

        Args:
            abonnement: Donnees de l'abonnement
            tenant_id: ID du tenant

        Returns:
            Donnees pour creer la facture
        """
        today = date.today()

        # Calculer la date d'echeance
        conditions = abonnement.get("conditions_paiement", "CONDITION_NET_30")
        due_date = DateCalculator.calculate_due_date(today, conditions)

        # Construire les lignes de facture
        produits = abonnement.get("produits")
        lignes = []

        if produits and isinstance(produits, list):
            for i, produit in enumerate(produits, 1):
                ligne = {
                    "line_number": i,
                    "product_id": produit.get("product_id"),
                    "product_code": produit.get("product_code", ""),
                    "description": produit.get("description", ""),
                    "quantity": produit.get("quantity", 1),
                    "unit": produit.get("unit", "pce"),
                    "unit_price": produit.get("unit_price", 0),
                    "tax_rate": produit.get("tax_rate", get_tva()),
                    "discount_percent": 0,
                    "discount_amount": 0,
                }
                # Calculer les montants
                subtotal = ligne["quantity"] * ligne["unit_price"]
                tax_amount = subtotal * (ligne["tax_rate"] / 100)
                ligne["subtotal"] = subtotal
                ligne["tax_amount"] = tax_amount
                ligne["total"] = subtotal + tax_amount
                lignes.append(ligne)
        else:
            # Pas de produits detailles: creer une ligne unique
            lignes = [{
                "line_number": 1,
                "description": f"Abonnement: {abonnement.get('nom', 'Abonnement')}",
                "quantity": 1,
                "unit": "forfait",
                "unit_price": abonnement.get("montant_ht", 0),
                "tax_rate": abonnement.get("taux_tva", get_tva()),
                "discount_percent": 0,
                "discount_amount": 0,
                "subtotal": abonnement.get("montant_ht", 0),
                "tax_amount": abonnement.get("montant_tva", 0),
                "total": abonnement.get("montant_ttc", 0),
            }]

        # Generer le numero de facture
        numero = Database.next_sequence(tenant_id, "facture")

        return {
            "number": numero,
            "reference": f"ABO-{abonnement.get('reference', str(abonnement['id'])[:8])}",
            "status": STATUT_FACTURE_VALIDEE,  # Auto-valide pour abonnements
            "customer_id": abonnement.get("client_id"),
            "date": today.isoformat(),
            "due_date": due_date.isoformat(),
            "subtotal": abonnement.get("montant_ht", 0),
            "tax_amount": abonnement.get("montant_tva", 0),
            "total": abonnement.get("montant_ttc", 0),
            "currency": abonnement.get("currency", DEVISE_EUR),
            "exchange_rate": 1.0,
            "subtotal_base": abonnement.get("montant_ht", 0),
            "total_base": abonnement.get("montant_ttc", 0),
            "payment_terms": abonnement.get("conditions_paiement", "CONDITION_NET_30"),
            "payment_method": abonnement.get("mode_paiement"),
            "paid_amount": 0,
            "remaining_amount": abonnement.get("montant_ttc", 0),
            "notes": abonnement.get("notes", ""),
            "internal_notes": f"Facture generee automatiquement - Abonnement: {abonnement.get('nom', '')}",
            "lignes": json.dumps(lignes) if isinstance(lignes, list) else lignes,
            "assigned_to": abonnement.get("responsable_id"),
            # Lien vers l'abonnement source
            "subscription_id": str(abonnement["id"]),
        }

    # =========================================================================
    # Gestion des abonnements
    # =========================================================================
    @classmethod
    async def activate_subscription(
        cls,
        tenant_id: UUID,
        abonnement_id: UUID,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Active un abonnement.

        Args:
            tenant_id: ID du tenant
            abonnement_id: ID de l'abonnement
            user_id: ID de l'utilisateur

        Returns:
            Abonnement mis a jour
        """
        abonnement = Database.get_by_id("abonnements", tenant_id, abonnement_id)

        if not abonnement:
            raise ValueError("Abonnement non trouve")

        if abonnement.get("statut") not in [STATUT_BROUILLON, STATUT_SUSPENDU]:
            raise ValueError(f"Impossible d'activer un abonnement avec statut: {abonnement.get('statut')}")

        # Calculer la premiere date de facturation
        date_debut = abonnement.get("date_debut")
        if isinstance(date_debut, str):
            date_debut = datetime.fromisoformat(date_debut).date()

        prochaine_facture = DateCalculator.calculate_next_invoice_date(
            frequence=abonnement.get("frequence", "mensuel"),
            jour_facturation=abonnement.get("jour_facturation", 1),
            current_date=date_debut or date.today()
        )

        update_data = {
            "statut": STATUT_ACTIF,
            "prochaine_facture": prochaine_facture.isoformat(),
        }

        return Database.update("abonnements", tenant_id, abonnement_id, update_data, user_id)

    @classmethod
    async def suspend_subscription(
        cls,
        tenant_id: UUID,
        abonnement_id: UUID,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Suspend un abonnement."""
        return Database.update(
            "abonnements",
            tenant_id,
            abonnement_id,
            {"statut": STATUT_SUSPENDU},
            user_id
        )

    @classmethod
    async def terminate_subscription(
        cls,
        tenant_id: UUID,
        abonnement_id: UUID,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Termine un abonnement."""
        return Database.update(
            "abonnements",
            tenant_id,
            abonnement_id,
            {
                "statut": STATUT_TERMINE,
                "date_fin": date.today().isoformat(),
                "actif": False
            },
            user_id
        )

    @classmethod
    async def cancel_subscription(
        cls,
        tenant_id: UUID,
        abonnement_id: UUID,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Annule un abonnement."""
        return Database.update(
            "abonnements",
            tenant_id,
            abonnement_id,
            {
                "statut": STATUT_ANNULE,
                "actif": False
            },
            user_id
        )


# =============================================================================
# Background Task (pour execution periodique)
# =============================================================================
class RecurringTask:
    """
    Tache de fond pour le traitement periodique des abonnements.

    Peut etre utilisee avec:
    - Cron externe (appel API)
    - APScheduler
    - Celery
    - asyncio.create_task dans le lifespan
    """

    _running: bool = False
    _task = None

    @classmethod
    async def start(cls):
        """Demarre la tache de fond."""
        if cls._running:
            logger.warning("recurring_task_already_running")
            return

        cls._running = True
        logger.info("recurring_task_started")

        import asyncio
        cls._task = asyncio.create_task(cls._run_loop())

    @classmethod
    async def stop(cls):
        """Arrete la tache de fond."""
        cls._running = False
        if cls._task:
            cls._task.cancel()
            try:
                await cls._task
            except asyncio.CancelledError:
                pass
        logger.info("recurring_task_stopped")

    @classmethod
    async def _run_loop(cls):
        """Boucle principale de la tache."""
        import asyncio

        while cls._running:
            try:
                # Executer a minuit (00:05 pour eviter les conflits)
                now = datetime.now()
                next_run = now.replace(hour=0, minute=5, second=0, microsecond=0)
                if now >= next_run:
                    next_run += timedelta(days=1)

                wait_seconds = (next_run - now).total_seconds()
                logger.info(
                    "recurring_task_next_run",
                    next_run=next_run.isoformat(),
                    wait_seconds=wait_seconds
                )

                # Attendre jusqu'a la prochaine execution
                await asyncio.sleep(wait_seconds)

                # Executer le traitement
                if cls._running:
                    results = await RecurringService.process_all_due_subscriptions()
                    logger.info(
                        "recurring_task_completed",
                        invoices_created=len([r for r in results if r.success]),
                        errors=len([r for r in results if not r.success])
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("recurring_task_error", error=str(e))
                # Attendre 1 heure avant de reessayer en cas d'erreur
                await asyncio.sleep(3600)

    @classmethod
    async def run_now(cls):
        """Execute le traitement immediatement."""
        logger.info("recurring_task_manual_run")
        results = await RecurringService.process_all_due_subscriptions()
        return results
