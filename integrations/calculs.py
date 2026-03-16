# =============================================================================
# AZALPLUS - Logique Métier et Calculs Automatiques
# =============================================================================
"""
Calculs automatiques pour les modules AZALPLUS.

Gère:
- Calculs de totaux (HT, TVA, TTC)
- Marges et rentabilité
- Stocks et mouvements
- Alertes automatiques (Marceau)
- Écritures comptables

Principe: Les champs `readonly: true` dans les YAML sont calculés automatiquement.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Callable, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


# =============================================================================
# Utilitaires de calcul
# =============================================================================

def money(value: float, decimals: int = 2) -> Decimal:
    """Convertir en Decimal avec arrondi monétaire."""
    return Decimal(str(value)).quantize(
        Decimal(10) ** -decimals,
        rounding=ROUND_HALF_UP
    )


def percentage(value: float, total: float) -> float:
    """Calculer un pourcentage."""
    if total == 0:
        return 0.0
    return round((value / total) * 100, 2)


def tva_rate_to_decimal(tva_code: str) -> Decimal:
    """Convertir un code TVA en décimal."""
    rates = {
        "TVA_20": Decimal("0.20"),
        "TVA_10": Decimal("0.10"),
        "TVA_5_5": Decimal("0.055"),
        "TVA_2_1": Decimal("0.021"),
        "TVA_0": Decimal("0"),
        "EXONERE": Decimal("0"),
    }
    return rates.get(tva_code, Decimal("0.20"))


# =============================================================================
# Calculateurs par module
# =============================================================================

class FactureCalculator:
    """Calculs pour les factures."""

    @staticmethod
    def calculate_ligne(ligne: dict) -> dict:
        """
        Calculer les totaux d'une ligne de facture.

        Input:
            - quantite: float
            - prix_unitaire: float
            - remise_pct: float (optionnel)
            - tva_code: str

        Output:
            - montant_ht: float
            - montant_remise: float
            - montant_tva: float
            - montant_ttc: float
        """
        quantite = Decimal(str(ligne.get("quantite", 1)))
        prix_unitaire = Decimal(str(ligne.get("prix_unitaire", 0)))
        remise_pct = Decimal(str(ligne.get("remise_pct", 0)))
        tva_rate = tva_rate_to_decimal(ligne.get("tva_code", "TVA_20"))

        # Montant brut
        montant_brut = quantite * prix_unitaire

        # Remise
        montant_remise = montant_brut * (remise_pct / Decimal("100"))
        montant_ht = montant_brut - montant_remise

        # TVA
        montant_tva = montant_ht * tva_rate

        # TTC
        montant_ttc = montant_ht + montant_tva

        return {
            "montant_brut": float(money(montant_brut)),
            "montant_remise": float(money(montant_remise)),
            "montant_ht": float(money(montant_ht)),
            "montant_tva": float(money(montant_tva)),
            "montant_ttc": float(money(montant_ttc)),
        }

    @staticmethod
    def calculate_totaux(lignes: list[dict], remise_globale_pct: float = 0) -> dict:
        """
        Calculer les totaux d'une facture.

        Input:
            - lignes: list de lignes calculées
            - remise_globale_pct: remise sur le total

        Output:
            - sous_total_ht: float
            - remise_globale: float
            - total_ht: float
            - total_tva: float (avec détail par taux)
            - total_ttc: float
        """
        sous_total_ht = Decimal("0")
        tva_par_taux = {}

        for ligne in lignes:
            ligne_calc = FactureCalculator.calculate_ligne(ligne)
            sous_total_ht += Decimal(str(ligne_calc["montant_ht"]))

            tva_code = ligne.get("tva_code", "TVA_20")
            if tva_code not in tva_par_taux:
                tva_par_taux[tva_code] = Decimal("0")
            tva_par_taux[tva_code] += Decimal(str(ligne_calc["montant_tva"]))

        # Remise globale
        remise_globale = sous_total_ht * (Decimal(str(remise_globale_pct)) / Decimal("100"))
        total_ht = sous_total_ht - remise_globale

        # Recalculer TVA après remise globale si nécessaire
        ratio_remise = total_ht / sous_total_ht if sous_total_ht > 0 else Decimal("1")
        total_tva = sum(tva * ratio_remise for tva in tva_par_taux.values())

        total_ttc = total_ht + total_tva

        return {
            "sous_total_ht": float(money(sous_total_ht)),
            "remise_globale": float(money(remise_globale)),
            "total_ht": float(money(total_ht)),
            "total_tva": float(money(total_tva)),
            "total_ttc": float(money(total_ttc)),
            "detail_tva": {k: float(money(v * ratio_remise)) for k, v in tva_par_taux.items()}
        }

    @staticmethod
    def calculate_echeance(date_facture: date, conditions: str = "30_JOURS") -> date:
        """Calculer la date d'échéance."""
        delais = {
            "COMPTANT": 0,
            "30_JOURS": 30,
            "45_JOURS": 45,
            "60_JOURS": 60,
            "FIN_MOIS": "fin_mois",
            "45_FIN_MOIS": "45_fin_mois",
        }

        delai = delais.get(conditions, 30)

        if delai == "fin_mois":
            # Fin du mois en cours
            if date_facture.month == 12:
                return date(date_facture.year + 1, 1, 1) - timedelta(days=1)
            return date(date_facture.year, date_facture.month + 1, 1) - timedelta(days=1)

        if delai == "45_fin_mois":
            # 45 jours puis fin de mois
            date_45 = date_facture + timedelta(days=45)
            if date_45.month == 12:
                return date(date_45.year + 1, 1, 1) - timedelta(days=1)
            return date(date_45.year, date_45.month + 1, 1) - timedelta(days=1)

        return date_facture + timedelta(days=delai)


class DevisCalculator:
    """Calculs pour les devis (similaire à facture)."""

    @staticmethod
    def calculate_marge(lignes: list[dict]) -> dict:
        """
        Calculer la marge sur un devis.

        Input:
            - lignes avec prix_unitaire et cout_unitaire

        Output:
            - cout_total: float
            - marge_brute: float
            - marge_pct: float
        """
        total_vente = Decimal("0")
        total_cout = Decimal("0")

        for ligne in lignes:
            quantite = Decimal(str(ligne.get("quantite", 1)))
            prix = Decimal(str(ligne.get("prix_unitaire", 0)))
            cout = Decimal(str(ligne.get("cout_unitaire", 0)))

            total_vente += quantite * prix
            total_cout += quantite * cout

        marge_brute = total_vente - total_cout
        marge_pct = percentage(float(marge_brute), float(total_vente))

        return {
            "total_vente_ht": float(money(total_vente)),
            "cout_total": float(money(total_cout)),
            "marge_brute": float(money(marge_brute)),
            "marge_pct": marge_pct
        }


class StockCalculator:
    """Calculs pour la gestion de stock."""

    @staticmethod
    def calculate_valeur_stock(produits: list[dict], methode: str = "CMP") -> dict:
        """
        Calculer la valeur du stock.

        Méthodes supportées:
            - CMP: Coût Moyen Pondéré
            - FIFO: First In First Out
            - LIFO: Last In First Out (rare)
            - DERNIER_PRIX: Dernier prix d'achat
        """
        valeur_totale = Decimal("0")
        produits_calcules = []

        for produit in produits:
            quantite = Decimal(str(produit.get("quantite", 0)))

            if methode == "CMP":
                prix = Decimal(str(produit.get("cout_moyen", 0)))
            elif methode == "DERNIER_PRIX":
                prix = Decimal(str(produit.get("dernier_prix_achat", 0)))
            else:
                prix = Decimal(str(produit.get("cout_moyen", 0)))

            valeur = quantite * prix
            valeur_totale += valeur

            produits_calcules.append({
                "produit_id": produit.get("id"),
                "quantite": float(quantite),
                "prix_unitaire": float(prix),
                "valeur": float(money(valeur))
            })

        return {
            "methode": methode,
            "valeur_totale": float(money(valeur_totale)),
            "nb_produits": len(produits),
            "detail": produits_calcules
        }

    @staticmethod
    def calculate_cout_moyen_pondere(
        quantite_actuelle: float,
        cout_actuel: float,
        quantite_entree: float,
        cout_entree: float
    ) -> float:
        """
        Calculer le nouveau CMP après une entrée de stock.

        CMP = (Quantité actuelle × Coût actuel + Quantité entrée × Coût entrée) / (Quantité totale)
        """
        qa = Decimal(str(quantite_actuelle))
        ca = Decimal(str(cout_actuel))
        qe = Decimal(str(quantite_entree))
        ce = Decimal(str(cout_entree))

        quantite_totale = qa + qe
        if quantite_totale == 0:
            return 0.0

        valeur_totale = (qa * ca) + (qe * ce)
        nouveau_cmp = valeur_totale / quantite_totale

        return float(money(nouveau_cmp))

    @staticmethod
    def calculate_rotation_stock(
        cout_stock_moyen: float,
        cout_ventes_annuel: float
    ) -> float:
        """
        Calculer le taux de rotation du stock.

        Rotation = Coût des ventes / Stock moyen
        Plus c'est élevé, mieux le stock tourne.
        """
        if cout_stock_moyen == 0:
            return 0.0
        return round(cout_ventes_annuel / cout_stock_moyen, 2)

    @staticmethod
    def calculate_couverture_stock(
        quantite_stock: float,
        consommation_moyenne_jour: float
    ) -> int:
        """
        Calculer le nombre de jours de stock.

        Couverture = Stock / Consommation moyenne journalière
        """
        if consommation_moyenne_jour == 0:
            return 999  # Stock infini
        return int(quantite_stock / consommation_moyenne_jour)


class RentabiliteCalculator:
    """Calculs de rentabilité."""

    @staticmethod
    def calculate_rentabilite_client(
        ca_ht: float,
        marge_brute: float,
        couts_directs: float = 0
    ) -> dict:
        """
        Calculer la rentabilité d'un client.

        Output:
            - marge_brute: float
            - marge_nette: float
            - taux_marge_brute: float (%)
            - taux_marge_nette: float (%)
        """
        marge_nette = marge_brute - couts_directs

        return {
            "ca_ht": ca_ht,
            "marge_brute": marge_brute,
            "marge_nette": marge_nette,
            "taux_marge_brute": percentage(marge_brute, ca_ht),
            "taux_marge_nette": percentage(marge_nette, ca_ht),
            "couts_directs": couts_directs
        }

    @staticmethod
    def calculate_rentabilite_projet(projet: dict) -> dict:
        """
        Calculer la rentabilité d'un projet.

        Input:
            - budget_prevu: float
            - budget_consomme: float
            - ca_facture: float
            - heures_prevues: float
            - heures_realisees: float
        """
        budget_prevu = Decimal(str(projet.get("budget_prevu", 0)))
        budget_consomme = Decimal(str(projet.get("budget_consomme", 0)))
        ca_facture = Decimal(str(projet.get("ca_facture", 0)))
        heures_prevues = Decimal(str(projet.get("heures_prevues", 0)))
        heures_realisees = Decimal(str(projet.get("heures_realisees", 0)))

        # Écart budget
        ecart_budget = budget_prevu - budget_consomme
        ecart_budget_pct = percentage(float(ecart_budget), float(budget_prevu))

        # Rentabilité
        marge = ca_facture - budget_consomme
        taux_marge = percentage(float(marge), float(ca_facture))

        # Productivité
        ecart_heures = heures_prevues - heures_realisees
        productivite = percentage(float(heures_prevues), float(heures_realisees)) if heures_realisees > 0 else 100

        return {
            "budget_prevu": float(budget_prevu),
            "budget_consomme": float(budget_consomme),
            "ecart_budget": float(money(ecart_budget)),
            "ecart_budget_pct": ecart_budget_pct,
            "ca_facture": float(ca_facture),
            "marge": float(money(marge)),
            "taux_marge": taux_marge,
            "heures_prevues": float(heures_prevues),
            "heures_realisees": float(heures_realisees),
            "ecart_heures": float(ecart_heures),
            "productivite": productivite,
            "rentable": float(marge) > 0
        }


class ImmobilierCalculator:
    """Calculs pour la gestion immobilière."""

    @staticmethod
    def calculate_loyer_cc(loyer_hc: float, charges: float) -> float:
        """Loyer charges comprises."""
        return round(loyer_hc + charges, 2)

    @staticmethod
    def calculate_rendement(
        loyer_annuel: float,
        prix_acquisition: float,
        charges_annuelles: float = 0
    ) -> dict:
        """
        Calculer le rendement locatif.

        Output:
            - rendement_brut: float (%)
            - rendement_net: float (%)
        """
        if prix_acquisition == 0:
            return {"rendement_brut": 0, "rendement_net": 0}

        rendement_brut = (loyer_annuel / prix_acquisition) * 100
        rendement_net = ((loyer_annuel - charges_annuelles) / prix_acquisition) * 100

        return {
            "loyer_annuel": loyer_annuel,
            "charges_annuelles": charges_annuelles,
            "revenu_net": loyer_annuel - charges_annuelles,
            "prix_acquisition": prix_acquisition,
            "rendement_brut": round(rendement_brut, 2),
            "rendement_net": round(rendement_net, 2)
        }


# =============================================================================
# Moteur de calculs automatiques
# =============================================================================

class CalculEngine:
    """
    Moteur de calculs automatiques pour AZALPLUS.

    Usage:
        engine = CalculEngine()

        # Avant sauvegarde d'une facture
        facture_data = engine.compute("factures", facture_data)

        # Les champs readonly sont maintenant calculés
    """

    def __init__(self):
        self._calculators: dict[str, Callable] = {
            "factures": self._compute_facture,
            "devis": self._compute_devis,
            "commandes": self._compute_commande,
            "avoirs": self._compute_avoir,
            "produits": self._compute_produit,
            "projets": self._compute_projet,
            "immobilier": self._compute_immobilier,
            "articles": self._compute_article,
        }

    def compute(self, module: str, data: dict) -> dict:
        """
        Calculer les champs readonly d'un enregistrement.

        Args:
            module: Nom du module
            data: Données à calculer

        Returns:
            Données avec champs calculés
        """
        calculator = self._calculators.get(module)
        if calculator:
            return calculator(data)
        return data

    def _compute_facture(self, data: dict) -> dict:
        """Calculer une facture."""
        lignes = data.get("lignes", [])
        remise_globale = data.get("remise_globale_pct", 0)

        totaux = FactureCalculator.calculate_totaux(lignes, remise_globale)

        data["montant_ht"] = totaux["total_ht"]
        data["montant_tva"] = totaux["total_tva"]
        data["montant_ttc"] = totaux["total_ttc"]

        # Échéance
        if data.get("date") and data.get("conditions_paiement"):
            date_facture = data["date"]
            if isinstance(date_facture, str):
                date_facture = date.fromisoformat(date_facture)
            data["date_echeance"] = FactureCalculator.calculate_echeance(
                date_facture,
                data["conditions_paiement"]
            ).isoformat()

        # Reste à payer
        montant_paye = data.get("montant_paye", 0)
        data["reste_a_payer"] = round(totaux["total_ttc"] - montant_paye, 2)

        return data

    def _compute_devis(self, data: dict) -> dict:
        """Calculer un devis."""
        # Mêmes calculs que facture
        data = self._compute_facture(data)

        # Plus: calcul de marge
        lignes = data.get("lignes", [])
        marge = DevisCalculator.calculate_marge(lignes)

        data["marge_brute"] = marge["marge_brute"]
        data["taux_marge"] = marge["marge_pct"]

        return data

    def _compute_commande(self, data: dict) -> dict:
        """Calculer une commande."""
        # Similaire à facture
        return self._compute_facture(data)

    def _compute_avoir(self, data: dict) -> dict:
        """Calculer un avoir."""
        # Similaire à facture, montants négatifs
        data = self._compute_facture(data)
        # Les montants sont déjà positifs mais représentent un crédit
        return data

    def _compute_produit(self, data: dict) -> dict:
        """Calculer un produit."""
        # Marge
        prix_vente = data.get("prix_vente", 0)
        cout_achat = data.get("cout_achat", 0)

        if cout_achat > 0:
            marge = prix_vente - cout_achat
            data["marge_unitaire"] = round(marge, 2)
            data["taux_marge"] = percentage(marge, prix_vente)

        # Valeur stock
        quantite = data.get("quantite_stock", 0)
        cout_moyen = data.get("cout_moyen", cout_achat)
        data["valeur_stock"] = round(quantite * cout_moyen, 2)

        return data

    def _compute_projet(self, data: dict) -> dict:
        """Calculer un projet."""
        rentabilite = RentabiliteCalculator.calculate_rentabilite_projet(data)

        data["ecart_budget"] = rentabilite["ecart_budget"]
        data["ecart_budget_pct"] = rentabilite["ecart_budget_pct"]
        data["marge_projet"] = rentabilite["marge"]
        data["taux_marge"] = rentabilite["taux_marge"]
        data["productivite"] = rentabilite["productivite"]

        # Avancement
        heures_prevues = data.get("heures_prevues", 0)
        heures_realisees = data.get("heures_realisees", 0)
        if heures_prevues > 0:
            data["avancement_pct"] = min(100, round((heures_realisees / heures_prevues) * 100, 1))

        return data

    def _compute_immobilier(self, data: dict) -> dict:
        """Calculer un bien immobilier."""
        # Loyer CC
        loyer_hc = data.get("loyer_hc", 0)
        charges = data.get("charges", 0)
        data["loyer_cc"] = ImmobilierCalculator.calculate_loyer_cc(loyer_hc, charges)

        # Revenus annuels
        data["revenus_annuels"] = loyer_hc * 12

        # Rendement
        prix_acquisition = data.get("prix_acquisition", 0)
        charges_annuelles = data.get("charges_annuelles", 0)

        if prix_acquisition > 0:
            rendement = ImmobilierCalculator.calculate_rendement(
                loyer_hc * 12,
                prix_acquisition,
                charges_annuelles
            )
            data["rendement"] = rendement["rendement_net"]

        return data

    def _compute_article(self, data: dict) -> dict:
        """Calculer un article/nomenclature."""
        composants = data.get("composants", [])

        # Coût des composants
        cout_total = Decimal("0")
        for comp in composants:
            quantite = Decimal(str(comp.get("quantite", 1)))
            cout = Decimal(str(comp.get("cout_unitaire", 0)))
            cout_total += quantite * cout

        data["cout_composants"] = float(money(cout_total))

        # Coût total avec main d'œuvre
        cout_mo = Decimal(str(data.get("cout_main_oeuvre", 0)))
        data["cout_total"] = float(money(cout_total + cout_mo))

        # Prix de vente suggéré
        marge_cible = Decimal(str(data.get("marge_cible", 30))) / Decimal("100")
        if marge_cible < 1:
            prix_suggere = (cout_total + cout_mo) / (Decimal("1") - marge_cible)
            data["prix_vente_suggere"] = float(money(prix_suggere))

        return data


# =============================================================================
# Singleton global
# =============================================================================

_engine: Optional[CalculEngine] = None


def get_calcul_engine() -> CalculEngine:
    """Récupérer l'instance du moteur de calculs."""
    global _engine
    if _engine is None:
        _engine = CalculEngine()
    return _engine
