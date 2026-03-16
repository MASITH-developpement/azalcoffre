# =============================================================================
# AZALPLUS - Tarification AZALCOFFRE
# =============================================================================
"""
Grille tarifaire et quotas pour l'intégration AZALCOFFRE.

CIBLE: TPE (Très Petites Entreprises < 10 salariés)
═══════════════════════════════════════════════════
- Budget logiciel : 0-50€/mois max
- Volume : 5-30 factures/mois, 3-15 signatures/mois
- Besoin : Simple, pas cher, qui marche
- Décision : Le GRATUIT gagne toujours

STRATÉGIE TARIFAIRE TPE:
════════════════════════
1. TOUT CE QUI EST FAISABLE EN INTERNE = GRATUIT
   - ERP complet, Factur-X, PPF, Signature SIMPLE, Backup
2. SEULS LES COÛTS EXTERNES = PAYANTS (au coût réel + marge mini)
   - Signature ADVANCED (Yousign) : 1€
   - Signature QUALIFIED (Certinomis) : 3€
3. Une TPE ne devrait JAMAIS avoir à payer pour usage normal

COÛTS RÉELS (fournisseurs):
═══════════════════════════
- Signature SIMPLE: ~0.02€ (fait maison: email + TSA)
- Signature ADVANCED: ~0.90€ (Yousign API volume)
- Signature QUALIFIED: ~2.80€ (Certinomis)
- Stockage: ~0.03€/Go/mois (S3)
- Horodatage TSA: ~0.02€/timestamp (FreeTSA ou DigiCert)
- Factur-X/PPF: ~0.00€ (API État gratuite)
- Backup quotidien: ~0.15€/mois/TPE

BENCHMARK CONCURRENCE (TPE):
════════════════════════════
- Yousign One: 9€/mois pour 10 signatures
- DocuSign Personal: 11€/mois pour 5 signatures
- Sage Compta: 30€/mois sans Factur-X
- AZALPLUS: 0€/mois, tout inclus ✓
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Plan(str, Enum):
    """Plans AZALCOFFRE disponibles."""
    # TPE = 99% des utilisateurs AZALPLUS
    TPE = "tpe"             # GRATUIT - Tout inclus pour une TPE
    # PME = Besoins plus importants (optionnel)
    PME = "pme"             # 19€/mois - Plus de stockage/backup
    # ETI = Grandes structures (rare sur AZALPLUS)
    ETI = "eti"             # 49€/mois - Illimité + multi-région


@dataclass
class SignaturePricing:
    """Prix des signatures selon contexte."""
    simple: float
    advanced: float
    qualified: float


@dataclass
class BackupConfig:
    """Configuration des sauvegardes."""
    frequency: str              # "daily", "hourly", "realtime"
    retention_days: int         # Durée de rétention
    point_in_time: bool         # Restauration point-in-time
    cross_region: bool          # Réplication multi-région
    download_enabled: bool      # Téléchargement manuel


@dataclass
class PlanLimits:
    """Limites et prix par plan."""
    # Coffre-fort
    documents_per_month: int          # Documents archivables/mois
    storage_gb: float                 # Stockage total
    retention_years: int              # Durée de rétention

    # Signatures incluses
    signatures_included: int          # Signatures SIMPLE incluses/mois

    # Sauvegardes BDD
    backup: BackupConfig              # Configuration backup

    # Factur-X / PDP - TOUJOURS GRATUIT
    facturx_unlimited: bool = True
    pdp_unlimited: bool = True


# =============================================================================
# LIMITES PAR PLAN (identiques quel que soit le contexte)
# =============================================================================

PLAN_LIMITS: dict[Plan, PlanLimits] = {
    # =========================================================================
    # TPE : GRATUIT - Couvre 99% des besoins d'une TPE
    # =========================================================================
    Plan.TPE: PlanLimits(
        documents_per_month=100,      # ~5 docs/jour ouvré = largement suffisant
        storage_gb=2.0,               # ~2000 factures PDF
        retention_years=10,           # Obligation légale factures
        signatures_included=999999,   # SIMPLE illimité (coût ~0.02€, offert)
        backup=BackupConfig(
            frequency="daily",
            retention_days=30,        # 1 mois de backup
            point_in_time=False,
            cross_region=False,
            download_enabled=True,    # Peut télécharger ses backups
        ),
    ),

    # =========================================================================
    # PME : 19€/mois - Pour ceux qui dépassent les limites TPE
    # =========================================================================
    Plan.PME: PlanLimits(
        documents_per_month=1000,     # ~50 docs/jour
        storage_gb=50.0,              # ~50 000 documents
        retention_years=10,
        signatures_included=999999,   # SIMPLE toujours illimité
        backup=BackupConfig(
            frequency="hourly",
            retention_days=90,
            point_in_time=True,       # Restauration à la minute
            cross_region=False,
            download_enabled=True,
        ),
    ),

    # =========================================================================
    # ETI : 49€/mois - Grandes structures (rare sur AZALPLUS)
    # =========================================================================
    Plan.ETI: PlanLimits(
        documents_per_month=999999,   # Illimité
        storage_gb=500.0,
        retention_years=50,           # Archivage légal bulletins paie
        signatures_included=999999,
        backup=BackupConfig(
            frequency="realtime",     # WAL streaming PostgreSQL
            retention_days=365,
            point_in_time=True,
            cross_region=True,        # Réplication multi-datacenter
            download_enabled=True,
        ),
    ),
}

# =============================================================================
# PRIX MENSUELS HT
# =============================================================================
# Note: Via AZALPLUS, les prix sont identiques (pas de standalone pour TPE)

MONTHLY_PRICES: dict[Plan, float] = {
    Plan.TPE: 0.0,      # GRATUIT - Cible principale
    Plan.PME: 19.0,     # Pour ceux qui dépassent les limites TPE
    Plan.ETI: 49.0,     # Grandes structures (rare)
}

# =============================================================================
# PRIX SIGNATURES (identique pour tous les plans)
# =============================================================================
# SIMPLE  : Fait maison (code email + TSA) → Coût réel ~0.02€ → GRATUIT
# ADVANCED: Yousign API → Coût réel ~0.90€ → 1€
# QUALIFIED: Certinomis → Coût réel ~2.80€ → 3€

SIGNATURE_PRICES: SignaturePricing = SignaturePricing(
    simple=0.00,      # GRATUIT ! Coût réel ~0.02€, absorbé
    advanced=1.00,    # Coût ~0.90€, marge 10% (couvre aléas)
    qualified=3.00,   # Coût ~2.80€, marge 7%
)

# Coûts réels pour référence interne
SIGNATURE_COSTS: SignaturePricing = SignaturePricing(
    simple=0.02,      # Email gratuit + TSA ~0.02€
    advanced=0.90,    # Yousign API volume
    qualified=2.80,   # Certinomis
)

# =============================================================================
# PACKS PRÉPAYÉS (pour PME/ETI qui utilisent beaucoup de signatures certifiées)
# =============================================================================
# Note: SIMPLE est gratuit donc pas de pack
# Les packs offrent -20% sur le prix unitaire

@dataclass
class SignaturePack:
    """Pack de signatures prépayé."""
    name: str
    signature_type: str  # "advanced", "qualified"
    quantity: int
    price: float

    @property
    def unit_price(self) -> float:
        return round(self.price / self.quantity, 2)

    @property
    def savings_percent(self) -> int:
        """Économie vs prix unitaire."""
        if self.signature_type == "advanced":
            return round((1 - self.unit_price / SIGNATURE_PRICES.advanced) * 100)
        elif self.signature_type == "qualified":
            return round((1 - self.unit_price / SIGNATURE_PRICES.qualified) * 100)
        return 0


SIGNATURE_PACKS: list[SignaturePack] = [
    # ADVANCED (prix unitaire: 1€)
    SignaturePack("Pack 20 ADVANCED", "advanced", 20, 16.0),    # 0.80€/u (-20%)
    SignaturePack("Pack 50 ADVANCED", "advanced", 50, 35.0),    # 0.70€/u (-30%)
    SignaturePack("Pack 100 ADVANCED", "advanced", 100, 60.0),  # 0.60€/u (-40%)

    # QUALIFIED (prix unitaire: 3€)
    SignaturePack("Pack 10 QUALIFIED", "qualified", 10, 24.0),  # 2.40€/u (-20%)
    SignaturePack("Pack 25 QUALIFIED", "qualified", 25, 52.0),  # 2.08€/u (-30%)
    SignaturePack("Pack 50 QUALIFIED", "qualified", 50, 90.0),  # 1.80€/u (-40%)
]


# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================

def get_plan_limits(plan: Plan) -> PlanLimits:
    """Retourne les limites d'un plan."""
    return PLAN_LIMITS[plan]


def get_monthly_price(plan: Plan) -> float:
    """Retourne le prix mensuel HT."""
    return MONTHLY_PRICES[plan]


def get_signature_prices() -> SignaturePricing:
    """Retourne les prix des signatures."""
    return SIGNATURE_PRICES


def calculate_monthly_bill(
    plan: Plan,
    nb_advanced: int = 0,
    nb_qualified: int = 0,
) -> dict:
    """
    Calcule la facture mensuelle pour une TPE.

    Args:
        plan: Plan souscrit (TPE, PME, ETI)
        nb_advanced: Nombre de signatures ADVANCED utilisées
        nb_qualified: Nombre de signatures QUALIFIED utilisées

    Returns:
        dict avec détail et total

    Note: Les signatures SIMPLE sont gratuites et illimitées.
    """
    base_price = MONTHLY_PRICES[plan]

    # Signatures SIMPLE = gratuites, pas de calcul
    # Seules ADVANCED et QUALIFIED sont facturées
    signature_cost = (
        nb_advanced * SIGNATURE_PRICES.advanced +
        nb_qualified * SIGNATURE_PRICES.qualified
    )

    total_ht = base_price + signature_cost
    tva = total_ht * 0.20
    total_ttc = total_ht + tva

    return {
        "plan": plan.value,
        "abonnement_ht": base_price,
        "signatures": {
            "simple": {"qty": "illimité", "prix": "GRATUIT"},
            "advanced": {"qty": nb_advanced, "unit": SIGNATURE_PRICES.advanced, "total": nb_advanced * SIGNATURE_PRICES.advanced},
            "qualified": {"qty": nb_qualified, "unit": SIGNATURE_PRICES.qualified, "total": nb_qualified * SIGNATURE_PRICES.qualified},
            "total": round(signature_cost, 2),
        },
        "total_ht": round(total_ht, 2),
        "tva_20": round(tva, 2),
        "total_ttc": round(total_ttc, 2),
    }


def estimate_plan_for_usage(
    docs_per_month: int,
    storage_gb_needed: float,
) -> Plan:
    """
    Recommande un plan basé sur l'usage prévu.

    Args:
        docs_per_month: Documents archivés par mois
        storage_gb_needed: Stockage nécessaire en Go

    Returns:
        Plan recommandé
    """
    if docs_per_month <= 100 and storage_gb_needed <= 2.0:
        return Plan.TPE  # GRATUIT
    elif docs_per_month <= 1000 and storage_gb_needed <= 50.0:
        return Plan.PME  # 19€
    else:
        return Plan.ETI  # 49€


def is_tpe_sufficient(
    factures_par_mois: int,
    devis_par_mois: int,
    autres_docs: int = 0,
) -> bool:
    """
    Vérifie si le plan TPE gratuit suffit.

    Args:
        factures_par_mois: Nombre de factures émises
        devis_par_mois: Nombre de devis
        autres_docs: Autres documents à archiver

    Returns:
        True si le plan TPE gratuit suffit
    """
    total_docs = factures_par_mois + devis_par_mois + autres_docs
    return total_docs <= 100  # Limite plan TPE


# =============================================================================
# RÉSUMÉ COMMERCIAL - CIBLE TPE
# =============================================================================
"""
┌─────────────────────────────────────────────────────────────────────────────┐
│              AZALPLUS + AZALCOFFRE - Offre TPE 2026                         │
│                    "Une TPE ne paye JAMAIS"                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  🆓 OFFRE TPE : 100% GRATUIT                                                │
│  ════════════════════════════                                               │
│                                                                             │
│  ERP COMPLET                                                                │
│  ✓ Gestion clients, devis, factures, interventions                         │
│  ✓ Tableaux de bord, statistiques                                          │
│  ✓ Multi-utilisateurs                                                      │
│                                                                             │
│  FACTURATION ÉLECTRONIQUE (obligation 2026)                                 │
│  ✓ Factur-X illimité (XML conforme EN16931)                                │
│  ✓ Envoi PPF illimité (Portail Public de Facturation)                      │
│  ✓ Réception factures fournisseurs                                         │
│                                                                             │
│  SIGNATURE ÉLECTRONIQUE                                                     │
│  ✓ Signature SIMPLE illimitée (code email + preuve légale eIDAS)           │
│    → Devis, bons de commande, CGV, mandats SEPA                            │
│                                                                             │
│  COFFRE-FORT & SAUVEGARDE                                                   │
│  ✓ 100 documents/mois archivés (hash SHA-256 + horodatage TSA)             │
│  ✓ 2 Go de stockage (~2000 factures)                                       │
│  ✓ Backup quotidien, rétention 30 jours                                    │
│  ✓ Téléchargement des sauvegardes                                          │
│                                                                             │
│  💶 COÛT MENSUEL TPE : 0€                                                   │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  💰 OPTIONS PAYANTES (usage exceptionnel)                                   │
│  ═════════════════════════════════════════                                  │
│                                                                             │
│  SIGNATURES CERTIFIÉES (coûts externes Yousign/Certinomis)                  │
│  ┌─────────────────┬──────────┬────────────┬───────────────────────────┐   │
│  │ Niveau          │ Prix     │ Coût réel  │ Usage                     │   │
│  ├─────────────────┼──────────┼────────────┼───────────────────────────┤   │
│  │ SIMPLE          │ GRATUIT  │ 0.02€      │ Devis, CGV (99% cas)      │   │
│  │ ADVANCED        │ 1€       │ 0.90€      │ Contrat > 10K€            │   │
│  │ QUALIFIED       │ 3€       │ 2.80€      │ Acte notarié, réglementé  │   │
│  └─────────────────┴──────────┴────────────┴───────────────────────────┘   │
│                                                                             │
│  ABONNEMENTS (si dépassement limites TPE)                                   │
│  ┌─────────┬──────────┬──────────────────────────────────────────────┐     │
│  │ Plan    │ Prix     │ Inclus                                       │     │
│  ├─────────┼──────────┼──────────────────────────────────────────────┤     │
│  │ TPE     │ GRATUIT  │ 100 docs/mois, 2 Go, backup 30j              │     │
│  │ PME     │ 19€/mois │ 1000 docs/mois, 50 Go, backup horaire 90j    │     │
│  │ ETI     │ 49€/mois │ Illimité, 500 Go, backup temps réel 1 an     │     │
│  └─────────┴──────────┴──────────────────────────────────────────────┘     │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  📊 COMPARATIF CONCURRENCE (TPE 15 factures/mois, 5 signatures)             │
│  ═══════════════════════════════════════════════════════════════            │
│                                                                             │
│  ┌─────────────────────┬──────────────┬─────────────────────────────┐      │
│  │ Solution            │ Coût/mois    │ Ce qui manque               │      │
│  ├─────────────────────┼──────────────┼─────────────────────────────┤      │
│  │ Sage Compta         │ 30€          │ Factur-X, signatures        │      │
│  │ EBP                 │ 25€          │ Factur-X, signatures        │      │
│  │ Yousign seul        │ 9€           │ ERP, Factur-X               │      │
│  │ Sage + Yousign      │ 39€          │ Factur-X                    │      │
│  │ Pennylane           │ 49€          │ Signatures limitées         │      │
│  │ ─────────────────── │ ──────────── │ ─────────────────────────── │      │
│  │ AZALPLUS            │ 0€           │ RIEN, tout inclus ✓         │      │
│  └─────────────────────┴──────────────┴─────────────────────────────┘      │
│                                                                             │
│  💰 ÉCONOMIE ANNUELLE vs Sage+Yousign : 468€                               │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  🎯 PITCH COMMERCIAL (30 secondes)                                          │
│  ═════════════════════════════════                                          │
│                                                                             │
│  "Vous êtes artisan, commerçant, indépendant ?                             │
│                                                                             │
│   AZALPLUS c'est :                                                          │
│   • Votre ERP : GRATUIT                                                    │
│   • Vos factures : GRATUITES                                               │
│   • La facturation électronique 2026 : GRATUITE                            │
│   • Vos devis signés par les clients : GRATUIT                             │
│   • Vos données sauvegardées : GRATUIT                                     │
│                                                                             │
│   Vous avez besoin d'une signature certifiée pour un gros contrat ?        │
│   1 euro. C'est tout.                                                       │
│                                                                             │
│   Les autres vous font payer 40€/mois pour ça."                            │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ⚖️ POURQUOI C'EST POSSIBLE                                                 │
│  ══════════════════════════                                                 │
│                                                                             │
│  • Factur-X : Code, pas de fournisseur → 0€                                │
│  • PPF : API État gratuite → 0€                                            │
│  • Signature SIMPLE : Fait maison (email + TSA) → 0.02€ absorbé            │
│  • Backup : Notre infra, coût marginal → 0.15€/mois absorbé                │
│  • Signature ADVANCED/QUALIFIED : Yousign/Certinomis → Coût réel facturé   │
│                                                                             │
│  On facture UNIQUEMENT ce qui nous coûte cher (prestataires externes).     │
│  Le reste, on l'offre parce que ça ne nous coûte presque rien.             │
│                                                                             │
│  C'est honnête et transparent.                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
"""
