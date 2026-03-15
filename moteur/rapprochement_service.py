# =============================================================================
# AZALPLUS - Service de Rapprochement Bancaire Automatique
# =============================================================================
"""
Rapprochement bancaire automatique 100% pour TPE.

ALGORITHME DE MATCHING (5 niveaux):
1. FINTECTURE_METADATA - payment_id dans métadonnées → facture directe
2. REFERENCE_EXACTE - Référence facture dans libellé bancaire
3. REGLE_APPRISE - Pattern libellé/tiers déjà vu → même affectation
4. MONTANT_UNIQUE - 1 seule facture ouverte du même montant exact
5. IA_PREDICTION - Score IA ≥ 95% → rapprochement auto

PRINCIPES:
- tenant_id OBLIGATOIRE sur chaque opération
- Tolérance montant: 0% (exact match requis)
- Pas d'option "ignorer" (illégal en compta française)
- Mouvements non rapprochés → compte 471 (attente)
- Alertes persistantes jusqu'à résolution
"""

import re
import json
import hashlib
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID, uuid4
from dataclasses import dataclass, field
from enum import Enum
import structlog

from .db import Database
from .tenant import TenantContext

logger = structlog.get_logger()


# =============================================================================
# Types et Constantes
# =============================================================================
class MethodeRapprochement(str, Enum):
    FINTECTURE_METADATA = "FINTECTURE_METADATA"
    REFERENCE_EXACTE = "REFERENCE_EXACTE"
    REGLE_APPRISE = "REGLE_APPRISE"
    MONTANT_UNIQUE = "MONTANT_UNIQUE"
    IA_PREDICTION = "IA_PREDICTION"
    MANUEL = "MANUEL"


class TypeAnomalie(str, Enum):
    DOUBLON_POTENTIEL = "DOUBLON_POTENTIEL"
    IBAN_MODIFIE = "IBAN_MODIFIE"
    MONTANT_INHABITUEL = "MONTANT_INHABITUEL"
    TIERS_INCONNU = "TIERS_INCONNU"
    DEBIT_NON_AUTORISE = "DEBIT_NON_AUTORISE"


@dataclass
class ResultatRapprochement:
    """Résultat d'un rapprochement."""
    succes: bool
    mouvement_id: UUID
    methode: Optional[MethodeRapprochement] = None
    confiance: int = 0
    document_type: Optional[str] = None
    document_id: Optional[str] = None
    compte_comptable: Optional[str] = None
    message: str = ""
    anomalie: Optional[TypeAnomalie] = None


@dataclass
class RegleApprise:
    """Règle de rapprochement apprise."""
    id: str
    pattern_libelle: str
    pattern_tiers: Optional[str]
    compte_comptable: str
    document_type: Optional[str]
    confiance: int
    utilisations: int = 0
    derniere_utilisation: Optional[datetime] = None


# =============================================================================
# Service Principal
# =============================================================================
class RapprochementService:
    """
    Service de rapprochement bancaire automatique.

    Usage:
        service = RapprochementService(tenant_id)
        resultat = await service.rapprocher_mouvement(mouvement_id)

        # Ou traiter tous les mouvements en attente
        resultats = await service.rapprocher_tous()
    """

    # Seuil de confiance IA pour auto-rapprochement
    SEUIL_CONFIANCE_IA = 95

    # Patterns pour extraction référence facture
    PATTERNS_REFERENCE = [
        r'FAC[-_]?(\d{4}[-_]?\d+)',      # FAC-2026-0001
        r'F[-_]?(\d{4}[-_]?\d+)',         # F-2026-0001
        r'INV[-_]?(\d+)',                  # INV-123456
        r'REF[-_:]?\s*([A-Z0-9-]+)',       # REF: ABC-123
        r'N[°o]?\s*(\d{6,})',              # N° 123456
    ]

    def __init__(self, tenant_id: UUID):
        """
        Initialise le service.

        Args:
            tenant_id: ID du tenant (OBLIGATOIRE)
        """
        if not tenant_id:
            raise ValueError("tenant_id est obligatoire")

        self.tenant_id = tenant_id
        self._regles_cache: Dict[str, List[RegleApprise]] = {}

    # =========================================================================
    # API Publique
    # =========================================================================

    async def rapprocher_mouvement(self, mouvement_id: UUID) -> ResultatRapprochement:
        """
        Rapproche un mouvement bancaire unique.

        Applique les 5 niveaux de matching dans l'ordre.

        Args:
            mouvement_id: ID du mouvement à rapprocher

        Returns:
            ResultatRapprochement avec le résultat
        """
        # Récupérer le mouvement
        mouvement = Database.get_by_id(
            "Mouvements_Bancaires",
            self.tenant_id,
            mouvement_id
        )

        if not mouvement:
            logger.warning("mouvement_not_found", mouvement_id=str(mouvement_id))
            return ResultatRapprochement(
                succes=False,
                mouvement_id=mouvement_id,
                message="Mouvement non trouvé"
            )

        # Vérifier si déjà rapproché
        if mouvement.get("statut") == "RAPPROCHE":
            return ResultatRapprochement(
                succes=True,
                mouvement_id=mouvement_id,
                methode=MethodeRapprochement(mouvement.get("methode_rapprochement", "MANUEL")),
                confiance=mouvement.get("confiance", 100),
                message="Déjà rapproché"
            )

        # Détecter les anomalies d'abord
        anomalie = await self._detecter_anomalies(mouvement)
        if anomalie:
            await self._marquer_anomalie(mouvement_id, anomalie)

        # Appliquer les 5 niveaux de matching
        resultat = await self._niveau1_fintecture(mouvement)
        if resultat.succes:
            return await self._finaliser_rapprochement(mouvement_id, resultat)

        resultat = await self._niveau2_reference_exacte(mouvement)
        if resultat.succes:
            return await self._finaliser_rapprochement(mouvement_id, resultat)

        resultat = await self._niveau3_regle_apprise(mouvement)
        if resultat.succes:
            return await self._finaliser_rapprochement(mouvement_id, resultat)

        resultat = await self._niveau4_montant_unique(mouvement)
        if resultat.succes:
            return await self._finaliser_rapprochement(mouvement_id, resultat)

        resultat = await self._niveau5_ia_prediction(mouvement)
        if resultat.succes:
            return await self._finaliser_rapprochement(mouvement_id, resultat)

        # Aucun match trouvé → reste en A_TRAITER
        logger.info(
            "rapprochement_no_match",
            mouvement_id=str(mouvement_id),
            montant=mouvement.get("montant"),
            libelle=mouvement.get("libelle", "")[:50]
        )

        return ResultatRapprochement(
            succes=False,
            mouvement_id=mouvement_id,
            message="Aucune correspondance trouvée",
            anomalie=anomalie
        )

    async def rapprocher_tous(self, compte_id: Optional[UUID] = None) -> List[ResultatRapprochement]:
        """
        Rapproche tous les mouvements en attente.

        Args:
            compte_id: Optionnel, limiter à un compte

        Returns:
            Liste des résultats
        """
        filters = {"statut": "A_TRAITER"}
        if compte_id:
            filters["compte_id"] = str(compte_id)

        mouvements = Database.query(
            "Mouvements_Bancaires",
            self.tenant_id,
            filters=filters,
            limit=500  # Traiter par batch
        )

        resultats = []
        rapproches = 0

        for mouvement in mouvements:
            mouvement_id = UUID(str(mouvement["id"]))
            resultat = await self.rapprocher_mouvement(mouvement_id)
            resultats.append(resultat)

            if resultat.succes:
                rapproches += 1

        # Mettre à jour les stats du compte
        if compte_id:
            await self._update_stats_compte(compte_id)

        logger.info(
            "rapprochement_batch_complete",
            tenant_id=str(self.tenant_id),
            total=len(mouvements),
            rapproches=rapproches
        )

        return resultats

    async def apprendre_regle(
        self,
        mouvement_id: UUID,
        compte_comptable: str,
        document_type: Optional[str] = None
    ) -> bool:
        """
        Apprend une règle depuis un rapprochement manuel.

        Appelé quand l'utilisateur valide un rapprochement pour
        mémoriser le pattern.

        Args:
            mouvement_id: ID du mouvement source
            compte_comptable: Compte comptable choisi
            document_type: Type de document si applicable

        Returns:
            True si règle créée
        """
        mouvement = Database.get_by_id(
            "Mouvements_Bancaires",
            self.tenant_id,
            mouvement_id
        )

        if not mouvement:
            return False

        libelle = mouvement.get("libelle", "")
        tiers = mouvement.get("tiers_libelle", "")
        compte_id = mouvement.get("compte_id")

        # Créer pattern depuis le libellé (normaliser)
        pattern_libelle = self._normaliser_pour_pattern(libelle)
        pattern_tiers = self._normaliser_pour_pattern(tiers) if tiers else None

        # Récupérer les règles existantes du compte
        compte = Database.get_by_id("Comptes_Bancaires", self.tenant_id, UUID(compte_id))
        regles_existantes = compte.get("regles_rapprochement", {}) if compte else {}

        if not isinstance(regles_existantes, dict):
            regles_existantes = {}

        # Ajouter ou mettre à jour la règle
        regle_id = hashlib.md5(f"{pattern_libelle}:{pattern_tiers}".encode()).hexdigest()[:12]

        regles_existantes[regle_id] = {
            "pattern_libelle": pattern_libelle,
            "pattern_tiers": pattern_tiers,
            "compte_comptable": compte_comptable,
            "document_type": document_type,
            "confiance": 90,  # Confiance initiale
            "utilisations": 1,
            "cree_le": datetime.utcnow().isoformat(),
            "derniere_utilisation": datetime.utcnow().isoformat()
        }

        # Sauvegarder
        Database.update(
            "Comptes_Bancaires",
            self.tenant_id,
            UUID(compte_id),
            {"regles_rapprochement": regles_existantes}
        )

        # Invalider le cache
        self._regles_cache.pop(compte_id, None)

        logger.info(
            "regle_apprise",
            regle_id=regle_id,
            pattern=pattern_libelle,
            compte_comptable=compte_comptable
        )

        return True

    # =========================================================================
    # Niveaux de Matching
    # =========================================================================

    async def _niveau1_fintecture(self, mouvement: Dict) -> ResultatRapprochement:
        """
        Niveau 1: Métadonnées Fintecture.

        Si le mouvement vient de Fintecture, le payment_id permet
        de retrouver directement la facture.
        """
        mouvement_id = UUID(str(mouvement["id"]))

        if mouvement.get("source") != "FINTECTURE":
            return ResultatRapprochement(succes=False, mouvement_id=mouvement_id)

        provider_data = mouvement.get("provider_data", {})
        if not isinstance(provider_data, dict):
            try:
                provider_data = json.loads(provider_data) if provider_data else {}
            except:
                provider_data = {}

        payment_id = provider_data.get("payment_id") or provider_data.get("session_id")

        if not payment_id:
            return ResultatRapprochement(succes=False, mouvement_id=mouvement_id)

        # Chercher dans paiements_openbanking
        paiements = Database.query(
            "Paiements_Open_Banking",
            self.tenant_id,
            filters={"provider_payment_id": payment_id}
        )

        if paiements and len(paiements) == 1:
            paiement = paiements[0]
            facture_id = paiement.get("facture_id")

            if facture_id:
                return ResultatRapprochement(
                    succes=True,
                    mouvement_id=mouvement_id,
                    methode=MethodeRapprochement.FINTECTURE_METADATA,
                    confiance=100,
                    document_type="FACTURE",
                    document_id=facture_id,
                    message="Correspondance Fintecture directe"
                )

        return ResultatRapprochement(succes=False, mouvement_id=mouvement_id)

    async def _niveau2_reference_exacte(self, mouvement: Dict) -> ResultatRapprochement:
        """
        Niveau 2: Référence exacte dans le libellé.

        Cherche un pattern de référence facture dans le libellé bancaire.
        """
        mouvement_id = UUID(str(mouvement["id"]))
        libelle = mouvement.get("libelle", "") + " " + mouvement.get("libelle_complementaire", "")
        libelle = libelle.upper()

        # Chercher des patterns de référence
        for pattern in self.PATTERNS_REFERENCE:
            match = re.search(pattern, libelle, re.IGNORECASE)
            if match:
                reference = match.group(1) if match.groups() else match.group(0)
                reference = reference.replace("-", "").replace("_", "")

                # Chercher la facture avec cette référence
                factures = Database.query(
                    "Factures",
                    self.tenant_id,
                    filters={"status": ["SENT", "VALIDATED", "PENDING"]}
                )

                for facture in factures:
                    numero = str(facture.get("number", "")).replace("-", "").replace("_", "")
                    if reference in numero or numero in reference:
                        # Vérifier que le montant correspond exactement
                        montant_mvt = float(mouvement.get("montant", 0))
                        montant_fac = float(facture.get("total", 0))

                        if abs(montant_mvt - montant_fac) < 0.01:  # Tolérance 1 centime
                            return ResultatRapprochement(
                                succes=True,
                                mouvement_id=mouvement_id,
                                methode=MethodeRapprochement.REFERENCE_EXACTE,
                                confiance=98,
                                document_type="FACTURE",
                                document_id=str(facture["id"]),
                                message=f"Référence {reference} trouvée"
                            )

        return ResultatRapprochement(succes=False, mouvement_id=mouvement_id)

    async def _niveau3_regle_apprise(self, mouvement: Dict) -> ResultatRapprochement:
        """
        Niveau 3: Règles apprises.

        Cherche si le pattern libellé/tiers correspond à une règle déjà apprise.
        """
        mouvement_id = UUID(str(mouvement["id"]))
        compte_id = mouvement.get("compte_id")

        if not compte_id:
            return ResultatRapprochement(succes=False, mouvement_id=mouvement_id)

        # Charger les règles (avec cache)
        regles = await self._charger_regles(compte_id)

        if not regles:
            return ResultatRapprochement(succes=False, mouvement_id=mouvement_id)

        libelle_norm = self._normaliser_pour_pattern(mouvement.get("libelle", ""))
        tiers_norm = self._normaliser_pour_pattern(mouvement.get("tiers_libelle", ""))

        meilleure_regle = None
        meilleur_score = 0

        for regle_id, regle in regles.items():
            score = 0

            # Match libellé
            pattern_lib = regle.get("pattern_libelle", "")
            if pattern_lib and pattern_lib in libelle_norm:
                score += 60
            elif pattern_lib and self._similarite(pattern_lib, libelle_norm) > 0.7:
                score += 40

            # Match tiers
            pattern_tiers = regle.get("pattern_tiers")
            if pattern_tiers and tiers_norm:
                if pattern_tiers in tiers_norm:
                    score += 30
                elif self._similarite(pattern_tiers, tiers_norm) > 0.7:
                    score += 20

            # Bonus confiance et utilisations
            score += min(regle.get("utilisations", 0), 10)  # Max +10

            if score > meilleur_score:
                meilleur_score = score
                meilleure_regle = (regle_id, regle)

        if meilleure_regle and meilleur_score >= 70:
            regle_id, regle = meilleure_regle

            # Mettre à jour les stats de la règle
            await self._incrementer_utilisation_regle(compte_id, regle_id)

            return ResultatRapprochement(
                succes=True,
                mouvement_id=mouvement_id,
                methode=MethodeRapprochement.REGLE_APPRISE,
                confiance=min(meilleur_score, 95),
                compte_comptable=regle.get("compte_comptable"),
                document_type=regle.get("document_type"),
                message=f"Règle '{regle_id}' appliquée"
            )

        return ResultatRapprochement(succes=False, mouvement_id=mouvement_id)

    async def _niveau4_montant_unique(self, mouvement: Dict) -> ResultatRapprochement:
        """
        Niveau 4: Montant unique.

        Si une seule facture ouverte a exactement ce montant, c'est elle.
        """
        mouvement_id = UUID(str(mouvement["id"]))
        montant = float(mouvement.get("montant", 0))
        sens = mouvement.get("sens")

        # Crédits = paiements clients (factures)
        if sens != "CREDIT":
            return ResultatRapprochement(succes=False, mouvement_id=mouvement_id)

        # Chercher factures ouvertes avec ce montant exact
        factures = Database.query(
            "Factures",
            self.tenant_id,
            filters={"status": ["SENT", "VALIDATED", "PENDING"]}
        )

        factures_match = []
        for facture in factures:
            total = float(facture.get("total", 0))
            remaining = float(facture.get("remaining_amount", total))

            if abs(remaining - montant) < 0.01:  # Exact match
                factures_match.append(facture)

        if len(factures_match) == 1:
            facture = factures_match[0]
            return ResultatRapprochement(
                succes=True,
                mouvement_id=mouvement_id,
                methode=MethodeRapprochement.MONTANT_UNIQUE,
                confiance=92,
                document_type="FACTURE",
                document_id=str(facture["id"]),
                message=f"Montant unique {montant}€"
            )

        return ResultatRapprochement(succes=False, mouvement_id=mouvement_id)

    async def _niveau5_ia_prediction(self, mouvement: Dict) -> ResultatRapprochement:
        """
        Niveau 5: Prédiction IA.

        Utilise un modèle ML pour prédire le rapprochement.
        Pour l'instant: heuristiques avancées.
        """
        mouvement_id = UUID(str(mouvement["id"]))

        # TODO: Implémenter vrai modèle ML
        # Pour l'instant: heuristiques combinées

        libelle = mouvement.get("libelle", "").upper()
        tiers = mouvement.get("tiers_libelle", "").upper()
        montant = float(mouvement.get("montant", 0))
        sens = mouvement.get("sens")

        # Heuristiques pour charges courantes
        charges_patterns = {
            r"EDF|ENGIE|ENERGIE": ("606100", "CHARGE", 90),
            r"ORANGE|SFR|BOUYGUES|FREE": ("626000", "CHARGE", 88),
            r"ASSUR": ("616000", "CHARGE", 85),
            r"LOYER|BAIL": ("613200", "CHARGE", 85),
            r"URSSAF|CPAM": ("645000", "CHARGE", 95),
            r"IMPOT|FISC|TRESOR": ("635000", "CHARGE", 90),
        }

        if sens == "DEBIT":
            for pattern, (compte, doc_type, conf) in charges_patterns.items():
                if re.search(pattern, libelle) or re.search(pattern, tiers):
                    if conf >= self.SEUIL_CONFIANCE_IA:
                        return ResultatRapprochement(
                            succes=True,
                            mouvement_id=mouvement_id,
                            methode=MethodeRapprochement.IA_PREDICTION,
                            confiance=conf,
                            compte_comptable=compte,
                            document_type=doc_type,
                            message=f"Pattern '{pattern}' détecté"
                        )

        # Pas de prédiction fiable
        return ResultatRapprochement(succes=False, mouvement_id=mouvement_id)

    # =========================================================================
    # Détection Anomalies
    # =========================================================================

    async def _detecter_anomalies(self, mouvement: Dict) -> Optional[TypeAnomalie]:
        """Détecte les anomalies sur un mouvement."""

        # 1. Doublon potentiel
        hash_check = self._calculer_hash_doublon(mouvement)
        existing = Database.query(
            "Mouvements_Bancaires",
            self.tenant_id,
            filters={"hash_doublon": hash_check}
        )
        if len(existing) > 1:
            return TypeAnomalie.DOUBLON_POTENTIEL

        # 2. IBAN modifié (si tiers connu)
        tiers = mouvement.get("tiers_libelle")
        iban = mouvement.get("tiers_iban")
        if tiers and iban:
            # Chercher historique
            historique = Database.query(
                "Mouvements_Bancaires",
                self.tenant_id,
                filters={"tiers_libelle": tiers, "statut": "RAPPROCHE"},
                limit=10
            )
            ibans_connus = set(m.get("tiers_iban") for m in historique if m.get("tiers_iban"))
            if ibans_connus and iban not in ibans_connus:
                return TypeAnomalie.IBAN_MODIFIE

        # 3. Montant inhabituel (> 3x la moyenne)
        montant = float(mouvement.get("montant", 0))
        if montant > 0:
            historique = Database.query(
                "Mouvements_Bancaires",
                self.tenant_id,
                filters={"sens": mouvement.get("sens"), "statut": "RAPPROCHE"},
                limit=100
            )
            if len(historique) >= 10:
                moyenne = sum(float(m.get("montant", 0)) for m in historique) / len(historique)
                if montant > moyenne * 3:
                    return TypeAnomalie.MONTANT_INHABITUEL

        return None

    async def _marquer_anomalie(self, mouvement_id: UUID, anomalie: TypeAnomalie):
        """Marque un mouvement comme anomalie."""
        messages = {
            TypeAnomalie.DOUBLON_POTENTIEL: "Doublon potentiel détecté",
            TypeAnomalie.IBAN_MODIFIE: "IBAN du tiers modifié",
            TypeAnomalie.MONTANT_INHABITUEL: "Montant inhabituellement élevé",
            TypeAnomalie.TIERS_INCONNU: "Tiers non reconnu",
            TypeAnomalie.DEBIT_NON_AUTORISE: "Débit non autorisé",
        }

        Database.update(
            "Mouvements_Bancaires",
            self.tenant_id,
            mouvement_id,
            {
                "anomalie": True,
                "type_anomalie": anomalie.value,
                "anomalie_message": messages.get(anomalie, str(anomalie)),
                "anomalie_resolue": False
            }
        )

        logger.warning(
            "anomalie_detectee",
            mouvement_id=str(mouvement_id),
            type=anomalie.value
        )

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _finaliser_rapprochement(
        self,
        mouvement_id: UUID,
        resultat: ResultatRapprochement
    ) -> ResultatRapprochement:
        """Finalise un rapprochement réussi."""

        update_data = {
            "statut": "RAPPROCHE",
            "methode_rapprochement": resultat.methode.value if resultat.methode else None,
            "confiance": resultat.confiance,
            "date_rapprochement": datetime.utcnow().isoformat(),
            "rapproche_par": "AUTO"
        }

        if resultat.document_type:
            update_data["document_type"] = resultat.document_type
        if resultat.document_id:
            update_data["document_id"] = resultat.document_id
            # Si c'est une facture, lier directement
            if resultat.document_type == "FACTURE":
                update_data["facture_id"] = resultat.document_id
        if resultat.compte_comptable:
            update_data["compte_comptable"] = resultat.compte_comptable

        Database.update(
            "Mouvements_Bancaires",
            self.tenant_id,
            mouvement_id,
            update_data
        )

        logger.info(
            "rapprochement_succes",
            mouvement_id=str(mouvement_id),
            methode=resultat.methode.value if resultat.methode else None,
            confiance=resultat.confiance
        )

        return resultat

    async def _charger_regles(self, compte_id: str) -> Dict[str, Dict]:
        """Charge les règles d'un compte avec cache."""
        if compte_id in self._regles_cache:
            return self._regles_cache[compte_id]

        compte = Database.get_by_id(
            "Comptes_Bancaires",
            self.tenant_id,
            UUID(compte_id)
        )

        if not compte:
            return {}

        regles = compte.get("regles_rapprochement", {})
        if not isinstance(regles, dict):
            try:
                regles = json.loads(regles) if regles else {}
            except:
                regles = {}

        self._regles_cache[compte_id] = regles
        return regles

    async def _incrementer_utilisation_regle(self, compte_id: str, regle_id: str):
        """Incrémente le compteur d'utilisation d'une règle."""
        compte = Database.get_by_id(
            "Comptes_Bancaires",
            self.tenant_id,
            UUID(compte_id)
        )

        if not compte:
            return

        regles = compte.get("regles_rapprochement", {})
        if not isinstance(regles, dict):
            return

        if regle_id in regles:
            regles[regle_id]["utilisations"] = regles[regle_id].get("utilisations", 0) + 1
            regles[regle_id]["derniere_utilisation"] = datetime.utcnow().isoformat()

            # Augmenter confiance si beaucoup d'utilisations
            if regles[regle_id]["utilisations"] >= 5:
                regles[regle_id]["confiance"] = min(
                    regles[regle_id].get("confiance", 90) + 1,
                    98
                )

            Database.update(
                "Comptes_Bancaires",
                self.tenant_id,
                UUID(compte_id),
                {"regles_rapprochement": regles}
            )

            # Invalider cache
            self._regles_cache.pop(compte_id, None)

    async def _update_stats_compte(self, compte_id: UUID):
        """Met à jour les statistiques de rapprochement d'un compte."""
        mouvements = Database.query(
            "Mouvements_Bancaires",
            self.tenant_id,
            filters={"compte_id": str(compte_id)}
        )

        total = len(mouvements)
        rapproches = sum(1 for m in mouvements if m.get("statut") == "RAPPROCHE")
        taux = round((rapproches / total * 100) if total > 0 else 0, 1)

        Database.update(
            "Comptes_Bancaires",
            self.tenant_id,
            compte_id,
            {
                "nb_mouvements_total": total,
                "nb_mouvements_rapproches": rapproches,
                "taux_rapprochement": taux,
                "dernier_rapprochement": datetime.utcnow().isoformat()
            }
        )

    def _normaliser_pour_pattern(self, texte: str) -> str:
        """Normalise un texte pour création/matching de pattern."""
        if not texte:
            return ""
        # Majuscules, sans accents, sans caractères spéciaux
        texte = texte.upper()
        # Remplacer accents
        accents = {
            'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
            'À': 'A', 'Â': 'A', 'Ä': 'A',
            'Ù': 'U', 'Û': 'U', 'Ü': 'U',
            'Î': 'I', 'Ï': 'I',
            'Ô': 'O', 'Ö': 'O',
            'Ç': 'C'
        }
        for acc, rep in accents.items():
            texte = texte.replace(acc, rep)
        # Garder alphanum et espaces
        texte = re.sub(r'[^A-Z0-9\s]', ' ', texte)
        texte = re.sub(r'\s+', ' ', texte).strip()
        return texte

    def _similarite(self, a: str, b: str) -> float:
        """Calcule similarité entre deux chaînes (Jaccard)."""
        if not a or not b:
            return 0.0
        set_a = set(a.split())
        set_b = set(b.split())
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def _calculer_hash_doublon(self, mouvement: Dict) -> str:
        """Calcule hash pour détection de doublons."""
        elements = [
            mouvement.get("compte_id", ""),
            mouvement.get("date_operation", ""),
            str(mouvement.get("montant", "")),
            mouvement.get("sens", ""),
            mouvement.get("libelle", "")[:20],
        ]
        return hashlib.md5("|".join(elements).encode()).hexdigest()


# =============================================================================
# Fonctions utilitaires
# =============================================================================

async def rapprocher_mouvement_swan(
    tenant_id: UUID,
    mouvement_id: UUID
) -> ResultatRapprochement:
    """
    Fonction helper pour appeler depuis swan.py.

    Usage dans swan.py:
        from .rapprochement_service import rapprocher_mouvement_swan
        result = await rapprocher_mouvement_swan(tenant_id, mouvement_id)
    """
    service = RapprochementService(tenant_id)
    return await service.rapprocher_mouvement(mouvement_id)


async def rapprocher_tous_compte(
    tenant_id: UUID,
    compte_id: UUID
) -> List[ResultatRapprochement]:
    """Rapproche tous les mouvements d'un compte."""
    service = RapprochementService(tenant_id)
    return await service.rapprocher_tous(compte_id)
