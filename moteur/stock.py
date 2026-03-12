# =============================================================================
# AZALPLUS - Stock Management Engine
# =============================================================================
"""
Moteur de gestion des stocks.
Gere automatiquement les mouvements de stock lors des evenements metier:
- Validation de facture -> Sortie de stock
- Terminaison d'intervention -> Sortie de stock (pieces utilisees)
- Ajustements manuels
- Alertes de stock bas

IMPORTANT: tenant_id obligatoire sur toutes les operations (AZA-TENANT)
"""

from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
import structlog

from .db import Database
from .tenant import get_current_tenant
from .constants import get_statuts, get_statut_defaut, get

logger = structlog.get_logger()


# =============================================================================
# Enums
# =============================================================================
class TypeMouvement(str, Enum):
    """Types de mouvement de stock."""
    ENTREE = "ENTREE"
    SORTIE = "SORTIE"
    AJUSTEMENT = "AJUSTEMENT"
    TRANSFERT = "TRANSFERT"
    INVENTAIRE = "INVENTAIRE"


class SousTypeMouvement(str, Enum):
    """Sous-types de mouvement."""
    # Entrees
    ACHAT = "ACHAT"
    RETOUR_CLIENT = "RETOUR_CLIENT"
    PRODUCTION = "PRODUCTION"
    TRANSFERT_ENTRANT = "TRANSFERT_ENTRANT"
    AJUSTEMENT_POSITIF = "AJUSTEMENT_POSITIF"
    INVENTAIRE_POSITIF = "INVENTAIRE_POSITIF"
    # Sorties
    VENTE = "VENTE"
    RETOUR_FOURNISSEUR = "RETOUR_FOURNISSEUR"
    CONSOMMATION = "CONSOMMATION"
    PERTE = "PERTE"
    CASSE = "CASSE"
    TRANSFERT_SORTANT = "TRANSFERT_SORTANT"
    AJUSTEMENT_NEGATIF = "AJUSTEMENT_NEGATIF"
    INVENTAIRE_NEGATIF = "INVENTAIRE_NEGATIF"
    INTERVENTION = "INTERVENTION"


class StatutMouvement(str, Enum):
    """Statuts de mouvement.

    DEPRECATED: Utiliser get_statuts("mouvements_stock") depuis moteur.constants
    Ces valeurs doivent correspondre à config/constants.yml > statuts.mouvements_stock
    """
    BROUILLON = "BROUILLON"
    VALIDE = "VALIDE"
    ANNULE = "ANNULE"


class StatutStock(str, Enum):
    """Statuts de stock.

    DEPRECATED: Utiliser get_statuts("stock") depuis moteur.constants
    Ces valeurs doivent correspondre à config/constants.yml > statuts.stock
    """
    EN_STOCK = "EN_STOCK"
    STOCK_BAS = "STOCK_BAS"
    RUPTURE = "RUPTURE"
    NON_GERE = "NON_GERE"


# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class LigneMouvement:
    """Ligne de mouvement de stock."""
    produit_id: UUID
    quantite: Decimal
    cout_unitaire: Optional[Decimal] = None
    lot: Optional[str] = None
    numero_serie: Optional[str] = None
    emplacement: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class AlerteStock:
    """Alerte de stock."""
    produit_id: UUID
    produit_nom: str
    type_alerte: str  # RUPTURE, STOCK_BAS, SEUIL_REAPPRO
    stock_actuel: int
    stock_minimum: int
    message: str


# =============================================================================
# Stock Service
# =============================================================================
class StockService:
    """
    Service de gestion des stocks.
    IMPORTANT: Toutes les methodes requierent tenant_id (multi-tenant).
    """

    def __init__(self, tenant_id: UUID, user_id: Optional[UUID] = None):
        """
        Initialise le service stock.

        Args:
            tenant_id: ID du tenant (OBLIGATOIRE)
            user_id: ID de l'utilisateur effectuant l'operation
        """
        if not tenant_id:
            raise ValueError("tenant_id est obligatoire (AZA-TENANT)")

        self.tenant_id = tenant_id
        self.user_id = user_id

    # =========================================================================
    # Mouvements de stock
    # =========================================================================
    def creer_mouvement(
        self,
        type_mvt: TypeMouvement,
        sous_type: SousTypeMouvement,
        lignes: List[LigneMouvement],
        motif: str,
        reference_type: Optional[str] = None,
        reference_id: Optional[UUID] = None,
        notes: Optional[str] = None,
        valider_auto: bool = True
    ) -> Dict[str, Any]:
        """
        Cree un mouvement de stock.

        Args:
            type_mvt: Type de mouvement (ENTREE, SORTIE, etc.)
            sous_type: Sous-type precis
            lignes: Liste des lignes de mouvement
            motif: Raison du mouvement
            reference_type: Type de document reference (facture, intervention, etc.)
            reference_id: ID du document reference
            notes: Notes complementaires
            valider_auto: Valider immediatement le mouvement

        Returns:
            Dict avec les details du mouvement cree
        """
        logger.info(
            "creation_mouvement_stock",
            tenant_id=str(self.tenant_id),
            type=type_mvt.value,
            sous_type=sous_type.value,
            nb_lignes=len(lignes)
        )

        # Generer numero de mouvement
        numero = self._generer_numero_mouvement(type_mvt)

        # Creer le mouvement en base
        mouvement_data = {
            "id": str(uuid4()),
            "tenant_id": str(self.tenant_id),
            "numero": numero,
            "date": datetime.utcnow().isoformat(),
            "type": type_mvt.value,
            "sous_type": sous_type.value,
            "statut": StatutMouvement.BROUILLON.value,
            "motif": motif,
            "notes": notes,
            "reference_type": reference_type,
            "reference_id": str(reference_id) if reference_id else None,
            "cree_par": str(self.user_id) if self.user_id else None
        }

        mouvement = Database.insert(
            "MouvementStock",
            self.tenant_id,
            mouvement_data,
            self.user_id
        )

        # Creer les lignes
        lignes_creees = []
        for ligne in lignes:
            # Recuperer le stock actuel du produit
            produit = self._get_produit(ligne.produit_id)
            if not produit:
                logger.warning("produit_non_trouve", produit_id=str(ligne.produit_id))
                continue

            # Verifier si gestion stock active
            if not produit.get("gestion_stock", True):
                logger.info("gestion_stock_inactive", produit_id=str(ligne.produit_id))
                continue

            quantite_avant = produit.get("stock_actuel", 0)

            ligne_data = {
                "id": str(uuid4()),
                "tenant_id": str(self.tenant_id),
                "mouvement_id": mouvement["id"],
                "produit_id": str(ligne.produit_id),
                "quantite": float(ligne.quantite),
                "quantite_avant": quantite_avant,
                "quantite_apres": self._calculer_quantite_apres(
                    quantite_avant, ligne.quantite, type_mvt
                ),
                "cout_unitaire": float(ligne.cout_unitaire) if ligne.cout_unitaire else None,
                "lot": ligne.lot,
                "numero_serie": ligne.numero_serie,
                "emplacement": ligne.emplacement,
                "notes": ligne.notes
            }

            lignes_creees.append(ligne_data)

        # Valider automatiquement si demande
        if valider_auto:
            self.valider_mouvement(UUID(mouvement["id"]), lignes_creees)

        return {
            "mouvement": mouvement,
            "lignes": lignes_creees,
            "valide": valider_auto
        }

    def valider_mouvement(
        self,
        mouvement_id: UUID,
        lignes: Optional[List[Dict]] = None
    ) -> bool:
        """
        Valide un mouvement et impacte les stocks.

        Args:
            mouvement_id: ID du mouvement a valider
            lignes: Lignes du mouvement (optionnel si deja en base)

        Returns:
            True si validation reussie
        """
        logger.info(
            "validation_mouvement_stock",
            tenant_id=str(self.tenant_id),
            mouvement_id=str(mouvement_id)
        )

        # Recuperer le mouvement
        mouvement = Database.get_by_id(
            "MouvementStock",
            self.tenant_id,
            mouvement_id
        )

        if not mouvement:
            logger.error("mouvement_non_trouve", mouvement_id=str(mouvement_id))
            return False

        if mouvement.get("statut") != StatutMouvement.BROUILLON.value:
            logger.warning("mouvement_deja_valide", mouvement_id=str(mouvement_id))
            return False

        type_mvt = TypeMouvement(mouvement.get("type"))

        # Recuperer les lignes si non fournies
        if not lignes:
            lignes = Database.query(
                "MouvementStockLigne",
                self.tenant_id,
                filters={"mouvement_id": str(mouvement_id)}
            )

        # Mettre a jour le stock de chaque produit
        alertes = []
        for ligne in lignes:
            produit_id = UUID(ligne["produit_id"])
            quantite = Decimal(str(ligne["quantite"]))

            # Mettre a jour le stock
            nouveau_stock = self._mettre_a_jour_stock(
                produit_id,
                quantite,
                type_mvt
            )

            # Verifier les alertes
            alerte = self._verifier_alertes_stock(produit_id, nouveau_stock)
            if alerte:
                alertes.append(alerte)

        # Marquer le mouvement comme valide
        Database.update(
            "MouvementStock",
            self.tenant_id,
            mouvement_id,
            {
                "statut": StatutMouvement.VALIDE.value,
                "valide_par": str(self.user_id) if self.user_id else None,
                "date_validation": datetime.utcnow().isoformat()
            },
            self.user_id
        )

        # Traiter les alertes
        for alerte in alertes:
            self._emettre_alerte(alerte)

        logger.info(
            "mouvement_valide",
            mouvement_id=str(mouvement_id),
            nb_alertes=len(alertes)
        )

        return True

    # =========================================================================
    # Triggers metier
    # =========================================================================
    def on_facture_validee(self, facture_id: UUID) -> Dict[str, Any]:
        """
        Trigger: Facture validee -> Sortie de stock.

        Args:
            facture_id: ID de la facture validee

        Returns:
            Details du mouvement cree
        """
        logger.info(
            "trigger_facture_validee",
            tenant_id=str(self.tenant_id),
            facture_id=str(facture_id)
        )

        # Recuperer la facture
        facture = Database.get_by_id("Facture", self.tenant_id, facture_id)
        if not facture:
            logger.error("facture_non_trouvee", facture_id=str(facture_id))
            return {"error": "Facture non trouvee"}

        # Recuperer les lignes de la facture
        lignes_facture = facture.get("lignes", [])
        if not lignes_facture:
            logger.info("facture_sans_lignes", facture_id=str(facture_id))
            return {"skipped": True, "reason": "Pas de lignes produit"}

        # Creer les lignes de mouvement
        lignes_mvt = []
        for ligne in lignes_facture:
            produit_id = ligne.get("produit_id") or ligne.get("produit")
            if not produit_id:
                continue

            quantite = ligne.get("quantite", 1)
            prix = ligne.get("prix_unitaire", 0)

            lignes_mvt.append(LigneMouvement(
                produit_id=UUID(produit_id) if isinstance(produit_id, str) else produit_id,
                quantite=Decimal(str(quantite)),
                cout_unitaire=Decimal(str(prix)) if prix else None,
                notes=ligne.get("description")
            ))

        if not lignes_mvt:
            return {"skipped": True, "reason": "Aucun produit avec gestion de stock"}

        # Creer le mouvement de sortie
        return self.creer_mouvement(
            type_mvt=TypeMouvement.SORTIE,
            sous_type=SousTypeMouvement.VENTE,
            lignes=lignes_mvt,
            motif=f"Vente - Facture {facture.get('numero', facture_id)}",
            reference_type="facture",
            reference_id=facture_id,
            valider_auto=True
        )

    def on_intervention_terminee(self, intervention_id: UUID) -> Dict[str, Any]:
        """
        Trigger: Intervention terminee -> Sortie de stock (pieces utilisees).

        Args:
            intervention_id: ID de l'intervention terminee

        Returns:
            Details du mouvement cree
        """
        logger.info(
            "trigger_intervention_terminee",
            tenant_id=str(self.tenant_id),
            intervention_id=str(intervention_id)
        )

        # Recuperer l'intervention
        intervention = Database.get_by_id(
            "Intervention",
            self.tenant_id,
            intervention_id
        )

        if not intervention:
            logger.error("intervention_non_trouvee", intervention_id=str(intervention_id))
            return {"error": "Intervention non trouvee"}

        # Recuperer les pieces utilisees
        pieces = intervention.get("pieces_utilisees", [])
        if not pieces:
            logger.info("intervention_sans_pieces", intervention_id=str(intervention_id))
            return {"skipped": True, "reason": "Pas de pieces utilisees"}

        # Creer les lignes de mouvement
        lignes_mvt = []
        for piece in pieces:
            produit_id = piece.get("produit_id") or piece.get("produit")
            if not produit_id:
                continue

            quantite = piece.get("quantite", 1)

            lignes_mvt.append(LigneMouvement(
                produit_id=UUID(produit_id) if isinstance(produit_id, str) else produit_id,
                quantite=Decimal(str(quantite)),
                notes=f"Utilise lors de l'intervention {intervention.get('numero', intervention_id)}"
            ))

        if not lignes_mvt:
            return {"skipped": True, "reason": "Aucun produit avec gestion de stock"}

        # Creer le mouvement de sortie
        return self.creer_mouvement(
            type_mvt=TypeMouvement.SORTIE,
            sous_type=SousTypeMouvement.INTERVENTION,
            lignes=lignes_mvt,
            motif=f"Pieces intervention {intervention.get('numero', intervention_id)}",
            reference_type="intervention",
            reference_id=intervention_id,
            valider_auto=True
        )

    def ajuster_stock(
        self,
        produit_id: UUID,
        nouvelle_quantite: int,
        motif: str
    ) -> Dict[str, Any]:
        """
        Ajuste le stock d'un produit (inventaire/correction).

        Args:
            produit_id: ID du produit
            nouvelle_quantite: Nouvelle quantite en stock
            motif: Raison de l'ajustement

        Returns:
            Details du mouvement cree
        """
        logger.info(
            "ajustement_stock",
            tenant_id=str(self.tenant_id),
            produit_id=str(produit_id),
            nouvelle_quantite=nouvelle_quantite
        )

        # Recuperer le produit
        produit = self._get_produit(produit_id)
        if not produit:
            return {"error": "Produit non trouve"}

        stock_actuel = produit.get("stock_actuel", 0)
        difference = nouvelle_quantite - stock_actuel

        if difference == 0:
            return {"skipped": True, "reason": "Pas de difference"}

        # Determiner le type de mouvement
        if difference > 0:
            type_mvt = TypeMouvement.AJUSTEMENT
            sous_type = SousTypeMouvement.AJUSTEMENT_POSITIF
        else:
            type_mvt = TypeMouvement.AJUSTEMENT
            sous_type = SousTypeMouvement.AJUSTEMENT_NEGATIF

        # Creer le mouvement
        return self.creer_mouvement(
            type_mvt=type_mvt,
            sous_type=sous_type,
            lignes=[LigneMouvement(
                produit_id=produit_id,
                quantite=Decimal(str(abs(difference)))
            )],
            motif=motif,
            valider_auto=True
        )

    # =========================================================================
    # Alertes
    # =========================================================================
    def get_alertes_stock(self) -> List[AlerteStock]:
        """
        Recupere toutes les alertes de stock actives.

        Returns:
            Liste des alertes
        """
        alertes = []

        # Recuperer les produits avec gestion de stock active
        produits = Database.query(
            "Produit",
            self.tenant_id,
            filters={"gestion_stock": True, "is_active": True}
        )

        for produit in produits:
            stock_actuel = produit.get("stock_actuel", 0)
            stock_minimum = produit.get("stock_minimum", 5)

            alerte = self._verifier_alertes_stock(
                UUID(produit["id"]),
                stock_actuel,
                produit
            )

            if alerte:
                alertes.append(alerte)

        return alertes

    # =========================================================================
    # Methodes privees
    # =========================================================================
    def _get_produit(self, produit_id: UUID) -> Optional[Dict]:
        """Recupere un produit."""
        return Database.get_by_id("Produit", self.tenant_id, produit_id)

    def _generer_numero_mouvement(self, type_mvt: TypeMouvement) -> str:
        """Genere un numero de mouvement unique."""
        prefix_map = {
            TypeMouvement.ENTREE: "MVT-E",
            TypeMouvement.SORTIE: "MVT-S",
            TypeMouvement.AJUSTEMENT: "MVT-A",
            TypeMouvement.TRANSFERT: "MVT-T",
            TypeMouvement.INVENTAIRE: "MVT-I"
        }
        prefix = prefix_map.get(type_mvt, "MVT")
        date_part = datetime.utcnow().strftime("%Y%m")

        # Compter les mouvements du mois
        count = Database.count(
            "MouvementStock",
            self.tenant_id,
            filters={"numero__startswith": f"{prefix}-{date_part}"}
        )

        return f"{prefix}-{date_part}-{(count + 1):05d}"

    def _calculer_quantite_apres(
        self,
        quantite_avant: int,
        quantite_mvt: Decimal,
        type_mvt: TypeMouvement
    ) -> int:
        """Calcule la quantite apres mouvement."""
        if type_mvt in [TypeMouvement.ENTREE]:
            return quantite_avant + int(quantite_mvt)
        elif type_mvt in [TypeMouvement.SORTIE]:
            return max(0, quantite_avant - int(quantite_mvt))
        else:  # AJUSTEMENT, INVENTAIRE
            return quantite_avant + int(quantite_mvt)

    def _mettre_a_jour_stock(
        self,
        produit_id: UUID,
        quantite: Decimal,
        type_mvt: TypeMouvement
    ) -> int:
        """Met a jour le stock d'un produit."""
        produit = self._get_produit(produit_id)
        if not produit:
            return 0

        stock_actuel = produit.get("stock_actuel", 0)
        nouveau_stock = self._calculer_quantite_apres(stock_actuel, quantite, type_mvt)

        # Calculer le statut
        stock_minimum = produit.get("stock_minimum", 5)
        if nouveau_stock <= 0:
            statut = StatutStock.RUPTURE.value
        elif nouveau_stock <= stock_minimum:
            statut = StatutStock.STOCK_BAS.value
        else:
            statut = StatutStock.EN_STOCK.value

        # Mettre a jour le produit
        Database.update(
            "Produit",
            self.tenant_id,
            produit_id,
            {
                "stock_actuel": nouveau_stock,
                "statut_stock": statut
            },
            self.user_id
        )

        logger.info(
            "stock_mis_a_jour",
            produit_id=str(produit_id),
            ancien_stock=stock_actuel,
            nouveau_stock=nouveau_stock,
            statut=statut
        )

        return nouveau_stock

    def _verifier_alertes_stock(
        self,
        produit_id: UUID,
        stock_actuel: int,
        produit: Optional[Dict] = None
    ) -> Optional[AlerteStock]:
        """Verifie si une alerte doit etre emise."""
        if not produit:
            produit = self._get_produit(produit_id)

        if not produit:
            return None

        stock_minimum = produit.get("stock_minimum", 5)
        seuil_reappro = produit.get("seuil_reapprovisionnement")
        produit_nom = produit.get("name") or produit.get("nom", "Produit inconnu")

        if stock_actuel <= 0:
            return AlerteStock(
                produit_id=produit_id,
                produit_nom=produit_nom,
                type_alerte="RUPTURE",
                stock_actuel=stock_actuel,
                stock_minimum=stock_minimum,
                message=f"URGENT - Rupture de stock: {produit_nom}"
            )
        elif stock_actuel <= stock_minimum:
            return AlerteStock(
                produit_id=produit_id,
                produit_nom=produit_nom,
                type_alerte="STOCK_BAS",
                stock_actuel=stock_actuel,
                stock_minimum=stock_minimum,
                message=f"Stock bas: {produit_nom} ({stock_actuel}/{stock_minimum})"
            )
        elif seuil_reappro and stock_actuel <= seuil_reappro:
            return AlerteStock(
                produit_id=produit_id,
                produit_nom=produit_nom,
                type_alerte="SEUIL_REAPPRO",
                stock_actuel=stock_actuel,
                stock_minimum=stock_minimum,
                message=f"Seuil reappro atteint: {produit_nom}"
            )

        return None

    def _emettre_alerte(self, alerte: AlerteStock):
        """Emet une alerte (notification, log, etc.)."""
        logger.warning(
            "alerte_stock",
            tenant_id=str(self.tenant_id),
            type=alerte.type_alerte,
            produit_id=str(alerte.produit_id),
            produit_nom=alerte.produit_nom,
            stock_actuel=alerte.stock_actuel,
            stock_minimum=alerte.stock_minimum,
            message=alerte.message
        )

        # TODO: Integrer avec systeme de notifications
        # - Email si RUPTURE
        # - Notification in-app si STOCK_BAS
        # - Dashboard KPI pour SEUIL_REAPPRO


# =============================================================================
# Hooks pour integration API
# =============================================================================
def hook_facture_validee(tenant_id: UUID, facture_id: UUID, user_id: Optional[UUID] = None):
    """Hook appele lors de la validation d'une facture."""
    service = StockService(tenant_id, user_id)
    return service.on_facture_validee(facture_id)


def hook_intervention_terminee(tenant_id: UUID, intervention_id: UUID, user_id: Optional[UUID] = None):
    """Hook appele lors de la terminaison d'une intervention."""
    service = StockService(tenant_id, user_id)
    return service.on_intervention_terminee(intervention_id)


def hook_ajustement_stock(tenant_id: UUID, produit_id: UUID, nouvelle_quantite: int, motif: str, user_id: Optional[UUID] = None):
    """Hook pour ajustement manuel de stock."""
    service = StockService(tenant_id, user_id)
    return service.ajuster_stock(produit_id, nouvelle_quantite, motif)


def get_alertes_stock(tenant_id: UUID) -> List[AlerteStock]:
    """Recupere les alertes de stock pour un tenant."""
    service = StockService(tenant_id)
    return service.get_alertes_stock()
