# =============================================================================
# AZALPLUS - Simulateur Statut Juridique
# =============================================================================
"""
Moteur de simulation pour le choix du statut juridique.
Basé sur les critères URSSAF et règles fiscales/sociales françaises 2026.
"""

from typing import Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger()


# =============================================================================
# Constantes 2026
# =============================================================================
class SeuilsMicro2026:
    """Seuils micro-entreprise 2026."""
    VENTE_MARCHANDISES = 188_700
    PRESTATIONS_SERVICES = 77_700
    LIBERALES = 77_700


class TauxCharges2026:
    """Taux de charges sociales 2026."""
    MICRO_VENTE = 12.3
    MICRO_SERVICES_BIC = 21.2
    MICRO_SERVICES_BNC = 21.1
    MICRO_LIBERALES = 21.2

    TNS_MINIMUM = 45  # % sur rémunération
    ASSIMILE_SALARIE = 65  # % sur rémunération brute (charges patronales + salariales)


class StatutJuridique(Enum):
    """Statuts juridiques disponibles."""
    MICRO = "Micro-entreprise"
    EI = "EI (Entreprise Individuelle)"
    EURL = "EURL"
    SARL = "SARL"
    SASU = "SASU"
    SAS = "SAS"


@dataclass
class ResultatSimulation:
    """Résultat d'une simulation."""
    statut_recommande: StatutJuridique
    score: int  # 0-100
    alternatives: List[Dict[str, Any]]
    avantages: List[str]
    inconvenients: List[str]
    charges_estimees: Dict[str, Any]
    regime_fiscal: str
    regime_tva: str
    explications: str
    points_vigilance: List[str]
    prochaines_etapes: List[str]


# =============================================================================
# Moteur de simulation
# =============================================================================
class SimulateurStatut:
    """Simulateur de statut juridique."""

    def __init__(self, donnees: Dict[str, Any]):
        """
        Initialise le simulateur.

        Args:
            donnees: Données du formulaire de simulation
        """
        self.donnees = donnees
        self.scores: Dict[StatutJuridique, int] = {s: 50 for s in StatutJuridique}
        self.raisons: Dict[StatutJuridique, List[str]] = {s: [] for s in StatutJuridique}

    def simuler(self) -> ResultatSimulation:
        """
        Lance la simulation et retourne le résultat.

        Returns:
            ResultatSimulation avec le statut recommandé
        """
        # Appliquer les règles
        self._evaluer_nombre_associes()
        self._evaluer_chiffre_affaires()
        self._evaluer_protection_patrimoine()
        self._evaluer_couverture_sociale()
        self._evaluer_mode_remuneration()
        self._evaluer_croissance()
        self._evaluer_investisseurs()
        self._evaluer_activite()
        self._evaluer_situation_personnelle()

        # Trouver le meilleur statut
        statut_recommande = max(self.scores, key=self.scores.get)
        score_max = self.scores[statut_recommande]

        # Construire les alternatives
        alternatives = []
        for statut, score in sorted(self.scores.items(), key=lambda x: x[1], reverse=True):
            if statut != statut_recommande and score >= 40:
                alternatives.append({
                    "statut": statut.value,
                    "score": score,
                    "raisons": self.raisons[statut][:3]
                })

        # Générer les détails
        avantages = self._get_avantages(statut_recommande)
        inconvenients = self._get_inconvenients(statut_recommande)
        charges = self._calculer_charges(statut_recommande)
        regime_fiscal = self._get_regime_fiscal(statut_recommande)
        regime_tva = self._get_regime_tva()
        explications = self._generer_explications(statut_recommande)
        vigilance = self._get_points_vigilance(statut_recommande)
        etapes = self._get_prochaines_etapes(statut_recommande)

        result = ResultatSimulation(
            statut_recommande=statut_recommande,
            score=score_max,
            alternatives=alternatives[:3],
            avantages=avantages,
            inconvenients=inconvenients,
            charges_estimees=charges,
            regime_fiscal=regime_fiscal,
            regime_tva=regime_tva,
            explications=explications,
            points_vigilance=vigilance,
            prochaines_etapes=etapes
        )

        logger.info("simulation_statut_complete",
                    statut=statut_recommande.value,
                    score=score_max)

        return result

    def _evaluer_nombre_associes(self):
        """Évalue selon le nombre d'associés."""
        nb = self.donnees.get('nombre_associes', '1 (seul)')

        if nb == '1 (seul)':
            self.scores[StatutJuridique.MICRO] += 20
            self.scores[StatutJuridique.EI] += 15
            self.scores[StatutJuridique.EURL] += 15
            self.scores[StatutJuridique.SASU] += 15
            self.raisons[StatutJuridique.MICRO].append("Adapté aux entrepreneurs solo")
            # Exclure SARL et SAS
            self.scores[StatutJuridique.SARL] -= 50
            self.scores[StatutJuridique.SAS] -= 50
        elif nb == '2':
            self.scores[StatutJuridique.SARL] += 20
            self.scores[StatutJuridique.SAS] += 20
            self.raisons[StatutJuridique.SARL].append("Idéal pour 2 associés")
            # Exclure les formes unipersonnelles
            self.scores[StatutJuridique.MICRO] -= 50
            self.scores[StatutJuridique.EI] -= 50
            self.scores[StatutJuridique.EURL] -= 50
            self.scores[StatutJuridique.SASU] -= 50
        else:
            self.scores[StatutJuridique.SARL] += 15
            self.scores[StatutJuridique.SAS] += 25
            self.raisons[StatutJuridique.SAS].append("Flexible pour plusieurs associés")
            # Exclure les formes unipersonnelles
            self.scores[StatutJuridique.MICRO] -= 50
            self.scores[StatutJuridique.EI] -= 50
            self.scores[StatutJuridique.EURL] -= 50
            self.scores[StatutJuridique.SASU] -= 50

    def _evaluer_chiffre_affaires(self):
        """Évalue selon le CA prévisionnel."""
        ca = self.donnees.get('ca_previsionnel', '< 10 000 €')
        type_activite = self.donnees.get('type_activite', 'Prestation de services commerciale (BIC)')

        # Déterminer le seuil applicable
        if 'Vente' in type_activite:
            seuil = SeuilsMicro2026.VENTE_MARCHANDISES
        else:
            seuil = SeuilsMicro2026.PRESTATIONS_SERVICES

        # Évaluer si micro possible
        if ca in ['< 10 000 €', '10 000 € - 36 800 €', '36 800 € - 77 700 €']:
            self.scores[StatutJuridique.MICRO] += 25
            self.raisons[StatutJuridique.MICRO].append(f"CA sous le seuil micro ({seuil:,} €)")
        elif ca == '77 700 € - 188 700 €':
            if 'Vente' in type_activite:
                self.scores[StatutJuridique.MICRO] += 15
                self.raisons[StatutJuridique.MICRO].append("CA sous le seuil vente")
            else:
                self.scores[StatutJuridique.MICRO] -= 30
                self.scores[StatutJuridique.EURL] += 20
                self.scores[StatutJuridique.SASU] += 20
                self.raisons[StatutJuridique.EURL].append("CA au-delà du seuil micro services")
        else:  # > 188 700 €
            self.scores[StatutJuridique.MICRO] -= 50
            self.scores[StatutJuridique.EURL] += 15
            self.scores[StatutJuridique.SASU] += 20
            self.scores[StatutJuridique.SAS] += 15
            self.raisons[StatutJuridique.SASU].append("CA important - structure société recommandée")

    def _evaluer_protection_patrimoine(self):
        """Évalue selon le besoin de protection du patrimoine."""
        protection = self.donnees.get('protection_patrimoine', 'Pas importante')

        if protection == 'Prioritaire':
            self.scores[StatutJuridique.EURL] += 20
            self.scores[StatutJuridique.SASU] += 25
            self.scores[StatutJuridique.SARL] += 20
            self.scores[StatutJuridique.SAS] += 20
            self.raisons[StatutJuridique.SASU].append("Responsabilité limitée aux apports")
            # Pénaliser EI et Micro
            self.scores[StatutJuridique.MICRO] -= 15
            self.scores[StatutJuridique.EI] -= 15
        elif protection == 'Importante':
            self.scores[StatutJuridique.EURL] += 15
            self.scores[StatutJuridique.SASU] += 15
            self.raisons[StatutJuridique.EURL].append("Protection du patrimoine personnel")

    def _evaluer_couverture_sociale(self):
        """Évalue selon le niveau de couverture sociale souhaité."""
        couverture = self.donnees.get('couverture_sociale', 'Équilibrée')

        if couverture == 'Maximale (salarié)':
            self.scores[StatutJuridique.SASU] += 30
            self.scores[StatutJuridique.SAS] += 25
            self.raisons[StatutJuridique.SASU].append("Régime général de la Sécurité sociale")
            # Pénaliser les TNS
            self.scores[StatutJuridique.MICRO] -= 10
            self.scores[StatutJuridique.EURL] -= 10
            self.scores[StatutJuridique.SARL] -= 10
        elif couverture == 'Minimale (coûts bas)':
            self.scores[StatutJuridique.MICRO] += 25
            self.scores[StatutJuridique.EURL] += 15
            self.scores[StatutJuridique.SARL] += 15
            self.raisons[StatutJuridique.MICRO].append("Charges sociales réduites")
            # Pénaliser assimilés salariés
            self.scores[StatutJuridique.SASU] -= 15
            self.scores[StatutJuridique.SAS] -= 15

    def _evaluer_mode_remuneration(self):
        """Évalue selon le mode de rémunération préféré."""
        remuneration = self.donnees.get('mode_remuneration', 'Peu importe')

        if remuneration == 'Dividendes principalement':
            self.scores[StatutJuridique.SASU] += 25
            self.scores[StatutJuridique.SAS] += 20
            self.raisons[StatutJuridique.SASU].append("Dividendes sans charges sociales (hors PFU)")
            # Pénaliser les autres
            self.scores[StatutJuridique.MICRO] -= 20
            self.scores[StatutJuridique.SARL] -= 10  # Dividendes soumis à charges > 10% capital
        elif remuneration == 'Salaire principalement':
            self.scores[StatutJuridique.SASU] += 15
            self.scores[StatutJuridique.SAS] += 15
            self.raisons[StatutJuridique.SAS].append("Rémunération en salaire possible")

    def _evaluer_croissance(self):
        """Évalue selon les perspectives de croissance."""
        croissance = self.donnees.get('croissance_prevue', 'Stable / Activité solo')

        if croissance == 'Levée de fonds envisagée':
            self.scores[StatutJuridique.SAS] += 30
            self.scores[StatutJuridique.SASU] += 25
            self.raisons[StatutJuridique.SAS].append("Structure adaptée aux investisseurs")
            # Exclure les autres
            self.scores[StatutJuridique.MICRO] -= 30
            self.scores[StatutJuridique.EI] -= 30
            self.scores[StatutJuridique.EURL] -= 10
            self.scores[StatutJuridique.SARL] -= 15
        elif croissance == 'Forte croissance':
            self.scores[StatutJuridique.SASU] += 20
            self.scores[StatutJuridique.SAS] += 20
            self.scores[StatutJuridique.EURL] += 10
            self.raisons[StatutJuridique.SASU].append("Évolutif vers SAS")
        elif croissance == 'Stable / Activité solo':
            self.scores[StatutJuridique.MICRO] += 20
            self.scores[StatutJuridique.EI] += 15
            self.raisons[StatutJuridique.MICRO].append("Simplicité pour activité stable")

    def _evaluer_investisseurs(self):
        """Évalue selon la présence d'investisseurs."""
        investisseurs = self.donnees.get('investisseurs_exterieurs', False)

        if investisseurs:
            self.scores[StatutJuridique.SAS] += 25
            self.scores[StatutJuridique.SASU] += 20
            self.raisons[StatutJuridique.SAS].append("Entrée d'investisseurs facilitée")
            # Exclure micro et EI
            self.scores[StatutJuridique.MICRO] -= 40
            self.scores[StatutJuridique.EI] -= 40

    def _evaluer_activite(self):
        """Évalue selon le type d'activité."""
        activite = self.donnees.get('type_activite', '')
        reglementee = self.donnees.get('activite_reglementee', False)

        if 'libérale réglementée' in activite.lower():
            self.scores[StatutJuridique.EI] += 15
            self.scores[StatutJuridique.SASU] += 10
            self.raisons[StatutJuridique.EI].append("Adapté aux professions libérales")
            # Certaines professions ne peuvent pas être en société

        if reglementee:
            self.scores[StatutJuridique.EURL] += 10
            self.scores[StatutJuridique.SASU] += 10
            self.raisons[StatutJuridique.EURL].append("Structure crédible pour activité réglementée")

    def _evaluer_situation_personnelle(self):
        """Évalue selon la situation personnelle du créateur."""
        situation = self.donnees.get('situation_actuelle', '')
        chomage = self.donnees.get('droits_chomage', False)
        maintien = self.donnees.get('maintien_activite_salariee', False)

        if chomage:
            # ARCE ou maintien ARE
            self.scores[StatutJuridique.SASU] += 15
            self.raisons[StatutJuridique.SASU].append("Compatible avec maintien ARE (pas de rémunération)")

        if maintien:
            self.scores[StatutJuridique.MICRO] += 15
            self.scores[StatutJuridique.SASU] += 10
            self.raisons[StatutJuridique.MICRO].append("Cumul emploi salarié facilité")

    def _get_avantages(self, statut: StatutJuridique) -> List[str]:
        """Retourne les avantages du statut."""
        avantages = {
            StatutJuridique.MICRO: [
                "Simplicité de création et de gestion",
                "Pas de comptabilité complexe",
                "Charges sociales proportionnelles au CA",
                "Franchise de TVA possible",
                "Déclaration de CA mensuelle ou trimestrielle"
            ],
            StatutJuridique.EI: [
                "Création simple et rapide",
                "Pas de capital minimum",
                "Option IS possible",
                "Patrimoine professionnel distinct (depuis 2022)",
                "Souplesse de gestion"
            ],
            StatutJuridique.EURL: [
                "Responsabilité limitée aux apports",
                "Crédibilité auprès des partenaires",
                "Option IS possible",
                "Facilement transformable en SARL",
                "Patrimoine personnel protégé"
            ],
            StatutJuridique.SARL: [
                "Responsabilité limitée aux apports",
                "Cadre juridique bien connu",
                "Cession de parts encadrée",
                "Gérant majoritaire TNS (charges réduites)",
                "Adapté aux entreprises familiales"
            ],
            StatutJuridique.SASU: [
                "Responsabilité limitée aux apports",
                "Grande flexibilité statutaire",
                "Président assimilé salarié (régime général)",
                "Dividendes sans charges sociales",
                "Facilement transformable en SAS"
            ],
            StatutJuridique.SAS: [
                "Grande liberté statutaire",
                "Facilité d'entrée d'investisseurs",
                "Dirigeants assimilés salariés",
                "Image moderne et dynamique",
                "Adaptée à la croissance"
            ]
        }
        return avantages.get(statut, [])

    def _get_inconvenients(self, statut: StatutJuridique) -> List[str]:
        """Retourne les inconvénients du statut."""
        inconvenients = {
            StatutJuridique.MICRO: [
                "Plafonds de CA limitants",
                "Pas de déduction des charges",
                "Pas de TVA récupérable (franchise)",
                "Crédibilité limitée pour certains clients",
                "Pas d'associés possibles"
            ],
            StatutJuridique.EI: [
                "Responsabilité sur patrimoine professionnel",
                "Cotisations sociales minimales même sans CA",
                "Image moins professionnelle",
                "Pas d'associés possibles"
            ],
            StatutJuridique.EURL: [
                "Formalisme juridique",
                "Coût de création et gestion",
                "Comptabilité obligatoire",
                "Cotisations minimales même sans rémunération"
            ],
            StatutJuridique.SARL: [
                "Rigidité statutaire",
                "Formalisme des décisions",
                "Dividendes soumis à charges si > 10% capital",
                "Cession de parts complexe"
            ],
            StatutJuridique.SASU: [
                "Charges sociales élevées sur rémunération",
                "Coût de création",
                "Comptabilité obligatoire",
                "Formalisme juridique"
            ],
            StatutJuridique.SAS: [
                "Charges sociales élevées",
                "Coûts de fonctionnement",
                "Complexité statutaire possible",
                "Rédaction des statuts délicate"
            ]
        }
        return inconvenients.get(statut, [])

    def _calculer_charges(self, statut: StatutJuridique) -> Dict[str, Any]:
        """Calcule une estimation des charges."""
        benefice = self.donnees.get('benefice_previsionnel', '10 000 € - 30 000 €')

        # Estimer le bénéfice moyen
        benefice_map = {
            '< 10 000 €': 5000,
            '10 000 € - 30 000 €': 20000,
            '30 000 € - 50 000 €': 40000,
            '50 000 € - 100 000 €': 75000,
            '> 100 000 €': 120000
        }
        montant = benefice_map.get(benefice, 20000)

        # Calculer selon le statut
        if statut == StatutJuridique.MICRO:
            type_activite = self.donnees.get('type_activite', '')
            if 'Vente' in type_activite:
                taux = TauxCharges2026.MICRO_VENTE
            else:
                taux = TauxCharges2026.MICRO_SERVICES_BIC
            charges_sociales = montant * taux / 100
            impot = montant * 0.11  # Versement libératoire estimé
        elif statut in [StatutJuridique.SASU, StatutJuridique.SAS]:
            # Assimilé salarié - estimation sur 70% du bénéfice en salaire
            salaire_brut = montant * 0.7
            charges_sociales = salaire_brut * TauxCharges2026.ASSIMILE_SALARIE / 100
            impot = (montant - charges_sociales) * 0.15  # IS 15% première tranche
        else:
            # TNS
            charges_sociales = montant * TauxCharges2026.TNS_MINIMUM / 100
            impot = (montant - charges_sociales) * 0.11  # IR estimé

        return {
            "charges_sociales_pct": round(charges_sociales / montant * 100, 1) if montant else 0,
            "charges_sociales_eur": round(charges_sociales),
            "impot_estime_eur": round(impot),
            "total_annuel": round(charges_sociales + impot),
            "net_estime": round(montant - charges_sociales - impot)
        }

    def _get_regime_fiscal(self, statut: StatutJuridique) -> str:
        """Détermine le régime fiscal recommandé."""
        benefice = self.donnees.get('benefice_previsionnel', '')

        if statut == StatutJuridique.MICRO:
            return "Micro-fiscal (versement libératoire possible)"
        elif statut in [StatutJuridique.SASU, StatutJuridique.SAS]:
            return "IS (Impôt sur les Sociétés)"
        elif statut == StatutJuridique.EI:
            if benefice in ['> 100 000 €', '50 000 € - 100 000 €']:
                return "IS recommandé (option)"
            return "IR (Impôt sur le Revenu) - BIC/BNC"
        elif statut in [StatutJuridique.EURL, StatutJuridique.SARL]:
            if benefice in ['> 100 000 €', '50 000 € - 100 000 €']:
                return "IS recommandé"
            return "IR possible (transparence fiscale) ou IS"
        return "À déterminer avec un expert"

    def _get_regime_tva(self) -> str:
        """Détermine le régime TVA recommandé."""
        ca = self.donnees.get('ca_previsionnel', '')

        if ca in ['< 10 000 €', '10 000 € - 36 800 €']:
            return "Franchise en base de TVA"
        elif ca in ['36 800 € - 77 700 €', '77 700 € - 188 700 €']:
            return "Réel simplifié"
        else:
            return "Réel normal"

    def _generer_explications(self, statut: StatutJuridique) -> str:
        """Génère les explications détaillées."""
        raisons = self.raisons.get(statut, [])
        score = self.scores[statut]

        texte = f"Le statut {statut.value} obtient un score de {score}/100 pour votre situation.\n\n"
        texte += "Raisons principales :\n"
        for raison in raisons[:5]:
            texte += f"• {raison}\n"

        return texte

    def _get_points_vigilance(self, statut: StatutJuridique) -> List[str]:
        """Retourne les points de vigilance."""
        vigilance = []

        if statut == StatutJuridique.MICRO:
            vigilance.append("Surveiller le dépassement des seuils de CA")
            vigilance.append("Pas de déduction des charges réelles")

        if statut in [StatutJuridique.SASU, StatutJuridique.SAS]:
            vigilance.append("Charges sociales élevées - optimiser la répartition salaire/dividendes")

        if self.donnees.get('emprunt_bancaire'):
            vigilance.append("L'emprunt peut nécessiter une caution personnelle")

        if self.donnees.get('activite_reglementee'):
            vigilance.append("Vérifier les conditions d'exercice de l'activité réglementée")

        return vigilance

    def _get_prochaines_etapes(self, statut: StatutJuridique) -> List[str]:
        """Retourne les prochaines étapes."""
        etapes = [
            "Valider le choix avec un expert-comptable",
            "Rédiger ou faire rédiger les statuts" if statut not in [StatutJuridique.MICRO, StatutJuridique.EI] else "Préparer le dossier d'immatriculation",
            "Déposer le capital social" if statut not in [StatutJuridique.MICRO, StatutJuridique.EI] else None,
            "Publier l'annonce légale" if statut not in [StatutJuridique.MICRO, StatutJuridique.EI] else None,
            "Immatriculer sur le guichet unique (INPI)",
            "Ouvrir un compte bancaire professionnel",
            "Souscrire les assurances obligatoires",
            "Contacter CMA/CCI/BGE pour accompagnement"
        ]
        return [e for e in etapes if e]


# =============================================================================
# Fonction raccourci
# =============================================================================
def simuler_statut(donnees: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lance une simulation de statut juridique.

    Args:
        donnees: Données du formulaire

    Returns:
        Dict avec les résultats de la simulation
    """
    simulateur = SimulateurStatut(donnees)
    resultat = simulateur.simuler()

    return {
        "statut_recommande": resultat.statut_recommande.value,
        "statut_score": resultat.score,
        "statuts_alternatifs": resultat.alternatives,
        "avantages": resultat.avantages,
        "inconvenients": resultat.inconvenients,
        "charges_estimees": resultat.charges_estimees,
        "regime_fiscal": resultat.regime_fiscal,
        "regime_tva": resultat.regime_tva,
        "explications": resultat.explications,
        "points_vigilance": resultat.points_vigilance,
        "prochaines_etapes": resultat.prochaines_etapes
    }
