"""
AZALPLUS - Modèles Chorus Pro
Structures de données pour l'API Chorus Pro
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID


class InvoiceStatus(str, Enum):
    """Statuts de facture Chorus Pro"""
    DRAFT = "BROUILLON"
    SUBMITTED = "DEPOSEE"
    RECEIVED = "RECUE"
    ACCEPTED = "ACCEPTEE"
    REJECTED = "REJETEE"
    SUSPENDED = "SUSPENDUE"
    PAID = "MISE_EN_PAIEMENT"
    CANCELLED = "ANNULEE"


class InvoiceType(str, Enum):
    """Types de facture"""
    INVOICE = "FACTURE"
    CREDIT_NOTE = "AVOIR"
    ADVANCE = "ACOMPTE"


class CadreFacturation(str, Enum):
    """Cadres de facturation Chorus Pro"""
    A1_FOURNISSEUR = "A1_FACTURE_FOURNISSEUR"
    A2_SOUSTRAITANT = "A2_FACTURE_SOUSTRAITANT"
    A3_COTITULAIRE = "A3_FACTURE_COTITULAIRE"
    A4_PRESTATAIRE = "A4_FACTURE_PRESTATAIRE"


@dataclass
class ChorusStructure:
    """Structure Chorus Pro (entreprise/entité publique)"""
    id_cpp: int  # ID interne Chorus Pro
    siret: str
    designation: str
    statut: str = "ACTIVE"
    type_identifiant: str = "SIRET"

    @classmethod
    def from_api(cls, data: dict) -> "ChorusStructure":
        """Crée depuis la réponse API"""
        return cls(
            id_cpp=data["idStructureCPP"],
            siret=data["identifiantStructure"],
            designation=data["designationStructure"],
            statut=data.get("statut", "ACTIVE"),
            type_identifiant=data.get("typeIdentifiantStructure", "SIRET"),
        )


@dataclass
class ChorusInvoiceLine:
    """Ligne de facture Chorus Pro"""
    numero_ligne: int
    designation: str
    quantite: Decimal
    prix_unitaire: Decimal
    montant_ht: Decimal
    taux_tva: Decimal = Decimal("20.00")
    unite: str = "PCE"  # Pièce

    def to_api(self) -> dict:
        """Convertit pour l'API Chorus Pro"""
        return {
            "numeroLigne": self.numero_ligne,
            "designation": self.designation,
            "quantite": float(self.quantite),
            "prixUnitaire": float(self.prix_unitaire),
            "montantHt": float(self.montant_ht),
            "tauxTva": float(self.taux_tva),
            "unite": self.unite,
        }


@dataclass
class ChorusInvoice:
    """Facture Chorus Pro"""
    numero_facture: str
    date_facture: date

    # Parties
    id_fournisseur: int
    siret_fournisseur: str
    id_destinataire: int
    siret_destinataire: str

    # Montants
    montant_ht: Decimal
    montant_tva: Decimal
    montant_ttc: Decimal
    devise: str = "EUR"

    # Lignes
    lignes: list[ChorusInvoiceLine] = field(default_factory=list)

    # Métadonnées
    type_facture: InvoiceType = InvoiceType.INVOICE
    cadre_facturation: CadreFacturation = CadreFacturation.A1_FOURNISSEUR
    mode_depot: str = "SAISIE_API"

    # Référence engagement (optionnel pour secteur public)
    numero_engagement: Optional[str] = None
    code_service_destinataire: Optional[str] = None

    # Statut après soumission
    id_facture_cpp: Optional[int] = None
    statut: InvoiceStatus = InvoiceStatus.DRAFT

    def to_api(self) -> dict:
        """Convertit pour soumission API Chorus Pro"""
        data = {
            "modeDepot": self.mode_depot,
            "destinataire": {
                "codeDestinataire": self.siret_destinataire,
            },
            "fournisseur": {
                "idFournisseur": self.id_fournisseur,
            },
            "cadreDeFacturation": {
                "codeCadreFacturation": self.cadre_facturation.value,
            },
            "references": {
                "deviseFacture": self.devise,
                "typeFacture": self.type_facture.value,
                "numeroFacture": self.numero_facture,
                "dateFacture": self.date_facture.strftime("%Y-%m-%d"),
                "montantHtTotal": float(self.montant_ht),
                "montantTtcTotal": float(self.montant_ttc),
                "montantTvaTotal": float(self.montant_tva),
            },
            "lignesPoste": [ligne.to_api() for ligne in self.lignes],
        }

        if self.code_service_destinataire:
            data["destinataire"]["codeServiceExecutant"] = self.code_service_destinataire

        if self.numero_engagement:
            data["references"]["numeroEngagement"] = self.numero_engagement

        return data
