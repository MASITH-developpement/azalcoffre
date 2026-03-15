# =============================================================================
# AZALPLUS - Parser Import Bancaire
# =============================================================================
"""
Import de relevés bancaires multi-format.

Formats supportés:
- CSV : Format générique (configurable par banque)
- OFX : Open Financial Exchange (standard USA/international)
- QIF : Quicken Interchange Format (legacy)
- CAMT.053 : ISO 20022 Bank-to-Customer Statement (SEPA)
- MT940 : SWIFT format (legacy bancaire)

Chaque format est normalisé vers MouvementBancaireImport pour création
dans mouvements_bancaires avec rapprochement automatique.
"""

import csv
import io
import logging
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# TYPES ET CONSTANTES
# =============================================================================

class FormatImport(str, Enum):
    """Formats d'import supportés."""
    CSV = "CSV"
    OFX = "OFX"
    QIF = "QIF"
    CAMT053 = "CAMT053"
    MT940 = "MT940"


class TypeMouvement(str, Enum):
    """Type de mouvement bancaire."""
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


@dataclass
class MouvementBancaireImport:
    """Structure normalisée d'un mouvement bancaire importé."""
    # Identification
    reference_banque: str
    date_operation: date
    date_valeur: Optional[date] = None

    # Montant
    montant: Decimal = Decimal("0")
    type_mouvement: TypeMouvement = TypeMouvement.DEBIT
    devise: str = "EUR"

    # Libellé et détails
    libelle: str = ""
    libelle_complement: Optional[str] = None

    # Contrepartie (si disponible)
    nom_contrepartie: Optional[str] = None
    iban_contrepartie: Optional[str] = None
    bic_contrepartie: Optional[str] = None

    # Références
    reference_client: Optional[str] = None
    reference_bout_en_bout: Optional[str] = None  # End-to-end ID SEPA
    reference_mandat: Optional[str] = None  # Mandat SEPA DD

    # Catégorisation banque
    code_operation: Optional[str] = None
    categorie_banque: Optional[str] = None

    # Métadonnées
    ligne_source: int = 0
    donnees_brutes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResultatImport:
    """Résultat d'un import de relevé bancaire."""
    succes: bool
    format_detecte: FormatImport
    compte_id: UUID
    fichier_nom: str

    # Statistiques
    nb_mouvements_importes: int = 0
    nb_mouvements_ignores: int = 0  # Doublons
    nb_erreurs: int = 0

    # Période
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None

    # Soldes (si disponibles dans le fichier)
    solde_initial: Optional[Decimal] = None
    solde_final: Optional[Decimal] = None

    # Détails
    mouvements: List[MouvementBancaireImport] = field(default_factory=list)
    erreurs: List[str] = field(default_factory=list)
    avertissements: List[str] = field(default_factory=list)


# =============================================================================
# PROFILS CSV PAR BANQUE
# =============================================================================

# Mapping colonnes CSV par banque française
PROFILS_CSV_BANQUES: Dict[str, Dict[str, Any]] = {
    "credit_agricole": {
        "nom": "Crédit Agricole",
        "encodage": "iso-8859-1",
        "separateur": ";",
        "decimal": ",",
        "date_format": "%d/%m/%Y",
        "colonnes": {
            "date_operation": ["Date", "Date opération", "Date d'opération"],
            "date_valeur": ["Date valeur", "Date de valeur"],
            "libelle": ["Libellé", "Libelle", "Description"],
            "debit": ["Débit", "Debit", "Montant débit"],
            "credit": ["Crédit", "Credit", "Montant crédit"],
            "montant": ["Montant"],  # Si colonne unique signée
            "reference": ["Référence", "Reference", "N° opération"],
        },
        "lignes_entete": 1,
    },
    "bnp": {
        "nom": "BNP Paribas",
        "encodage": "utf-8",
        "separateur": ";",
        "decimal": ",",
        "date_format": "%d/%m/%Y",
        "colonnes": {
            "date_operation": ["Date"],
            "date_valeur": ["Valeur"],
            "libelle": ["Libellé"],
            "debit": ["Débit euros"],
            "credit": ["Crédit euros"],
            "reference": ["Référence"],
            "categorie": ["Catégorie"],
        },
        "lignes_entete": 1,
    },
    "societe_generale": {
        "nom": "Société Générale",
        "encodage": "iso-8859-1",
        "separateur": ";",
        "decimal": ",",
        "date_format": "%d/%m/%Y",
        "colonnes": {
            "date_operation": ["Date de l'opération", "Date"],
            "date_valeur": ["Date de valeur"],
            "libelle": ["Libellé de l'opération", "Libellé"],
            "montant": ["Montant de l'opération", "Montant"],
            "reference": ["Référence de l'opération"],
        },
        "lignes_entete": 1,
    },
    "la_banque_postale": {
        "nom": "La Banque Postale",
        "encodage": "iso-8859-1",
        "separateur": ";",
        "decimal": ",",
        "date_format": "%d/%m/%Y",
        "colonnes": {
            "date_operation": ["Date comptable"],
            "date_valeur": ["Date de valeur"],
            "libelle": ["Libellé"],
            "debit": ["Débit"],
            "credit": ["Crédit"],
        },
        "lignes_entete": 1,
    },
    "caisse_epargne": {
        "nom": "Caisse d'Épargne",
        "encodage": "iso-8859-1",
        "separateur": ";",
        "decimal": ",",
        "date_format": "%d/%m/%Y",
        "colonnes": {
            "date_operation": ["Date"],
            "date_valeur": ["Date valeur"],
            "libelle": ["Libellé"],
            "debit": ["Débit"],
            "credit": ["Crédit"],
            "reference": ["Numéro d'opération"],
        },
        "lignes_entete": 1,
    },
    "boursorama": {
        "nom": "Boursorama",
        "encodage": "utf-8",
        "separateur": ";",
        "decimal": ",",
        "date_format": "%Y-%m-%d",
        "colonnes": {
            "date_operation": ["dateOp", "Date opération"],
            "date_valeur": ["dateVal", "Date valeur"],
            "libelle": ["label", "Libellé"],
            "montant": ["amount", "Montant"],
            "categorie": ["category", "Catégorie"],
        },
        "lignes_entete": 1,
    },
    "fortuneo": {
        "nom": "Fortuneo",
        "encodage": "utf-8",
        "separateur": ";",
        "decimal": ",",
        "date_format": "%d/%m/%Y",
        "colonnes": {
            "date_operation": ["Date opération"],
            "date_valeur": ["Date valeur"],
            "libelle": ["Libellé"],
            "debit": ["Débit"],
            "credit": ["Crédit"],
        },
        "lignes_entete": 1,
    },
    "lcl": {
        "nom": "LCL",
        "encodage": "iso-8859-1",
        "separateur": ";",
        "decimal": ",",
        "date_format": "%d/%m/%Y",
        "colonnes": {
            "date_operation": ["Date"],
            "date_valeur": ["Date valeur"],
            "libelle": ["Libellé"],
            "debit": ["Débit"],
            "credit": ["Crédit"],
        },
        "lignes_entete": 1,
    },
    "credit_mutuel": {
        "nom": "Crédit Mutuel / CIC",
        "encodage": "iso-8859-1",
        "separateur": ";",
        "decimal": ",",
        "date_format": "%d/%m/%Y",
        "colonnes": {
            "date_operation": ["Date"],
            "date_valeur": ["Date de valeur"],
            "libelle": ["Libellé"],
            "debit": ["Débit"],
            "credit": ["Crédit"],
        },
        "lignes_entete": 1,
    },
    "generique": {
        "nom": "Format générique",
        "encodage": "utf-8",
        "separateur": ";",
        "decimal": ",",
        "date_format": "%d/%m/%Y",
        "colonnes": {
            "date_operation": ["date", "Date", "DATE", "date_operation"],
            "date_valeur": ["date_valeur", "Date valeur", "valeur"],
            "libelle": ["libelle", "Libellé", "LIBELLE", "description", "Description"],
            "montant": ["montant", "Montant", "MONTANT", "amount"],
            "debit": ["debit", "Débit", "DEBIT"],
            "credit": ["credit", "Crédit", "CREDIT"],
            "reference": ["reference", "Référence", "REFERENCE", "ref"],
        },
        "lignes_entete": 1,
    },
}


# =============================================================================
# PARSERS ABSTRAITS
# =============================================================================

class ParserBancaire(ABC):
    """Classe abstraite pour les parsers de relevés bancaires."""

    format: FormatImport

    def __init__(self, tenant_id: UUID, compte_id: UUID):
        self.tenant_id = tenant_id
        self.compte_id = compte_id
        self.erreurs: List[str] = []
        self.avertissements: List[str] = []

    @abstractmethod
    def parse(self, contenu: bytes, nom_fichier: str) -> ResultatImport:
        """Parse le contenu du fichier et retourne les mouvements."""
        pass

    def _nettoyer_montant(self, valeur: str, decimal_sep: str = ",") -> Optional[Decimal]:
        """Nettoie et convertit une chaîne en Decimal."""
        if not valeur or valeur.strip() in ("", "-", "N/A"):
            return None

        # Nettoyer
        valeur = valeur.strip()
        valeur = valeur.replace(" ", "").replace("\u00a0", "")  # Espaces insécables
        valeur = valeur.replace("€", "").replace("EUR", "")

        # Gérer séparateur décimal
        if decimal_sep == ",":
            valeur = valeur.replace(".", "").replace(",", ".")

        # Gérer signe négatif entre parenthèses
        if valeur.startswith("(") and valeur.endswith(")"):
            valeur = "-" + valeur[1:-1]

        try:
            return Decimal(valeur)
        except InvalidOperation:
            return None

    def _parser_date(self, valeur: str, formats: List[str]) -> Optional[date]:
        """Parse une date selon plusieurs formats possibles."""
        if not valeur or valeur.strip() == "":
            return None

        valeur = valeur.strip()

        for fmt in formats:
            try:
                return datetime.strptime(valeur, fmt).date()
            except ValueError:
                continue

        return None

    def _generer_reference(self, mouvement: MouvementBancaireImport) -> str:
        """Génère une référence unique si absente."""
        if mouvement.reference_banque:
            return mouvement.reference_banque

        # Générer depuis date + montant + hash libellé
        import hashlib
        data = f"{mouvement.date_operation}|{mouvement.montant}|{mouvement.libelle}"
        hash_court = hashlib.sha256(data.encode()).hexdigest()[:12]
        return f"IMP-{mouvement.date_operation.strftime('%Y%m%d')}-{hash_court}"


# =============================================================================
# PARSER CSV
# =============================================================================

class ParserCSV(ParserBancaire):
    """Parser pour fichiers CSV bancaires."""

    format = FormatImport.CSV

    def __init__(self, tenant_id: UUID, compte_id: UUID, profil: str = "generique"):
        super().__init__(tenant_id, compte_id)
        self.profil_nom = profil
        self.profil = PROFILS_CSV_BANQUES.get(profil, PROFILS_CSV_BANQUES["generique"])

    def parse(self, contenu: bytes, nom_fichier: str) -> ResultatImport:
        """Parse un fichier CSV bancaire."""
        mouvements: List[MouvementBancaireImport] = []

        # Détecter encodage
        encodage = self.profil.get("encodage", "utf-8")
        try:
            texte = contenu.decode(encodage)
        except UnicodeDecodeError:
            # Fallback
            for enc in ["utf-8", "iso-8859-1", "cp1252"]:
                try:
                    texte = contenu.decode(enc)
                    encodage = enc
                    break
                except UnicodeDecodeError:
                    continue
            else:
                self.erreurs.append("Impossible de décoder le fichier")
                return ResultatImport(
                    succes=False,
                    format_detecte=self.format,
                    compte_id=self.compte_id,
                    fichier_nom=nom_fichier,
                    erreurs=self.erreurs,
                )

        # Détecter séparateur si non spécifié
        separateur = self.profil.get("separateur", ";")
        premiere_ligne = texte.split("\n")[0] if texte else ""
        if ";" in premiere_ligne and "," not in premiere_ligne:
            separateur = ";"
        elif "," in premiere_ligne and ";" not in premiere_ligne:
            separateur = ","
        elif "\t" in premiere_ligne:
            separateur = "\t"

        # Parser CSV
        reader = csv.DictReader(
            io.StringIO(texte),
            delimiter=separateur,
        )

        # Mapper colonnes
        colonnes_config = self.profil.get("colonnes", {})
        mapping = self._detecter_mapping_colonnes(reader.fieldnames or [], colonnes_config)

        if not mapping.get("date_operation"):
            self.erreurs.append("Colonne date non trouvée")
            return ResultatImport(
                succes=False,
                format_detecte=self.format,
                compte_id=self.compte_id,
                fichier_nom=nom_fichier,
                erreurs=self.erreurs,
            )

        # Parser lignes
        date_format = self.profil.get("date_format", "%d/%m/%Y")
        decimal_sep = self.profil.get("decimal", ",")

        for i, row in enumerate(reader, start=2):  # Ligne 2 car entête = 1
            try:
                mouvement = self._parser_ligne_csv(row, mapping, date_format, decimal_sep, i)
                if mouvement:
                    mouvements.append(mouvement)
            except Exception as e:
                self.erreurs.append(f"Ligne {i}: {str(e)}")

        # Calculer période
        dates = [m.date_operation for m in mouvements if m.date_operation]
        date_debut = min(dates) if dates else None
        date_fin = max(dates) if dates else None

        return ResultatImport(
            succes=len(mouvements) > 0,
            format_detecte=self.format,
            compte_id=self.compte_id,
            fichier_nom=nom_fichier,
            nb_mouvements_importes=len(mouvements),
            nb_erreurs=len(self.erreurs),
            date_debut=date_debut,
            date_fin=date_fin,
            mouvements=mouvements,
            erreurs=self.erreurs,
            avertissements=self.avertissements,
        )

    def _detecter_mapping_colonnes(
        self,
        colonnes_fichier: List[str],
        colonnes_config: Dict[str, List[str]]
    ) -> Dict[str, Optional[str]]:
        """Détecte le mapping entre colonnes fichier et colonnes attendues."""
        mapping: Dict[str, Optional[str]] = {}

        colonnes_normalisees = {c.lower().strip(): c for c in colonnes_fichier}

        for champ, noms_possibles in colonnes_config.items():
            mapping[champ] = None
            for nom in noms_possibles:
                nom_lower = nom.lower().strip()
                if nom_lower in colonnes_normalisees:
                    mapping[champ] = colonnes_normalisees[nom_lower]
                    break
                # Match partiel
                for col_norm, col_orig in colonnes_normalisees.items():
                    if nom_lower in col_norm or col_norm in nom_lower:
                        mapping[champ] = col_orig
                        break
                if mapping[champ]:
                    break

        return mapping

    def _parser_ligne_csv(
        self,
        row: Dict[str, str],
        mapping: Dict[str, Optional[str]],
        date_format: str,
        decimal_sep: str,
        ligne: int,
    ) -> Optional[MouvementBancaireImport]:
        """Parse une ligne CSV en MouvementBancaireImport."""

        # Date opération (obligatoire)
        col_date = mapping.get("date_operation")
        if not col_date or col_date not in row:
            return None

        date_op = self._parser_date(row[col_date], [date_format, "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"])
        if not date_op:
            self.avertissements.append(f"Ligne {ligne}: date invalide '{row.get(col_date, '')}'")
            return None

        # Date valeur
        date_val = None
        col_date_val = mapping.get("date_valeur")
        if col_date_val and col_date_val in row:
            date_val = self._parser_date(row[col_date_val], [date_format, "%Y-%m-%d", "%d/%m/%Y"])

        # Montant
        montant = Decimal("0")
        type_mouvement = TypeMouvement.DEBIT

        # Cas 1: Colonnes séparées débit/crédit
        col_debit = mapping.get("debit")
        col_credit = mapping.get("credit")

        if col_debit and col_credit:
            debit = self._nettoyer_montant(row.get(col_debit, ""), decimal_sep)
            credit = self._nettoyer_montant(row.get(col_credit, ""), decimal_sep)

            if debit and debit != Decimal("0"):
                montant = abs(debit)
                type_mouvement = TypeMouvement.DEBIT
            elif credit and credit != Decimal("0"):
                montant = abs(credit)
                type_mouvement = TypeMouvement.CREDIT

        # Cas 2: Colonne unique signée
        else:
            col_montant = mapping.get("montant")
            if col_montant and col_montant in row:
                montant_raw = self._nettoyer_montant(row[col_montant], decimal_sep)
                if montant_raw:
                    if montant_raw < 0:
                        montant = abs(montant_raw)
                        type_mouvement = TypeMouvement.DEBIT
                    else:
                        montant = montant_raw
                        type_mouvement = TypeMouvement.CREDIT

        if montant == Decimal("0"):
            # Ignorer les lignes sans montant
            return None

        # Libellé
        libelle = ""
        col_libelle = mapping.get("libelle")
        if col_libelle and col_libelle in row:
            libelle = row[col_libelle].strip()

        if not libelle:
            libelle = "Opération sans libellé"

        # Référence
        reference = ""
        col_ref = mapping.get("reference")
        if col_ref and col_ref in row:
            reference = row[col_ref].strip()

        # Catégorie banque
        categorie = None
        col_cat = mapping.get("categorie")
        if col_cat and col_cat in row:
            categorie = row[col_cat].strip() or None

        mouvement = MouvementBancaireImport(
            reference_banque=reference,
            date_operation=date_op,
            date_valeur=date_val,
            montant=montant,
            type_mouvement=type_mouvement,
            libelle=libelle,
            categorie_banque=categorie,
            ligne_source=ligne,
            donnees_brutes=dict(row),
        )

        # Générer référence si absente
        if not mouvement.reference_banque:
            mouvement.reference_banque = self._generer_reference(mouvement)

        return mouvement


# =============================================================================
# PARSER OFX
# =============================================================================

class ParserOFX(ParserBancaire):
    """Parser pour fichiers OFX (Open Financial Exchange)."""

    format = FormatImport.OFX

    def parse(self, contenu: bytes, nom_fichier: str) -> ResultatImport:
        """Parse un fichier OFX."""
        mouvements: List[MouvementBancaireImport] = []
        solde_initial: Optional[Decimal] = None
        solde_final: Optional[Decimal] = None

        # Décoder
        try:
            texte = contenu.decode("utf-8")
        except UnicodeDecodeError:
            try:
                texte = contenu.decode("iso-8859-1")
            except UnicodeDecodeError:
                texte = contenu.decode("cp1252", errors="ignore")

        # OFX peut être SGML ou XML
        if texte.strip().startswith("<?xml") or texte.strip().startswith("<OFX"):
            mouvements, solde_initial, solde_final = self._parse_ofx_xml(texte)
        else:
            mouvements, solde_initial, solde_final = self._parse_ofx_sgml(texte)

        # Calculer période
        dates = [m.date_operation for m in mouvements if m.date_operation]

        return ResultatImport(
            succes=len(mouvements) > 0,
            format_detecte=self.format,
            compte_id=self.compte_id,
            fichier_nom=nom_fichier,
            nb_mouvements_importes=len(mouvements),
            nb_erreurs=len(self.erreurs),
            date_debut=min(dates) if dates else None,
            date_fin=max(dates) if dates else None,
            solde_initial=solde_initial,
            solde_final=solde_final,
            mouvements=mouvements,
            erreurs=self.erreurs,
            avertissements=self.avertissements,
        )

    def _parse_ofx_sgml(self, texte: str) -> Tuple[List[MouvementBancaireImport], Optional[Decimal], Optional[Decimal]]:
        """Parse OFX format SGML (tags non fermés)."""
        mouvements: List[MouvementBancaireImport] = []
        solde_initial: Optional[Decimal] = None
        solde_final: Optional[Decimal] = None

        # Extraire transactions
        stmttrn_pattern = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.DOTALL | re.IGNORECASE)

        for i, match in enumerate(stmttrn_pattern.finditer(texte), start=1):
            bloc = match.group(1)
            mouvement = self._parse_stmttrn_sgml(bloc, i)
            if mouvement:
                mouvements.append(mouvement)

        # Soldes
        ledger_match = re.search(r"<LEDGERBAL>.*?<BALAMT>([^<\n]+)", texte, re.DOTALL | re.IGNORECASE)
        if ledger_match:
            solde_final = self._nettoyer_montant(ledger_match.group(1).strip(), ".")

        avail_match = re.search(r"<AVAILBAL>.*?<BALAMT>([^<\n]+)", texte, re.DOTALL | re.IGNORECASE)
        if avail_match and not solde_final:
            solde_final = self._nettoyer_montant(avail_match.group(1).strip(), ".")

        return mouvements, solde_initial, solde_final

    def _parse_stmttrn_sgml(self, bloc: str, ligne: int) -> Optional[MouvementBancaireImport]:
        """Parse un bloc STMTTRN SGML."""

        def extraire(tag: str) -> Optional[str]:
            pattern = re.compile(rf"<{tag}>([^<\n]+)", re.IGNORECASE)
            match = pattern.search(bloc)
            return match.group(1).strip() if match else None

        # Type transaction
        trntype = extraire("TRNTYPE") or "OTHER"

        # Date
        dtposted = extraire("DTPOSTED")
        if not dtposted:
            return None

        date_op = self._parse_date_ofx(dtposted)
        if not date_op:
            return None

        # Montant
        trnamt = extraire("TRNAMT")
        if not trnamt:
            return None

        montant_raw = self._nettoyer_montant(trnamt, ".")
        if not montant_raw:
            return None

        if montant_raw < 0:
            montant = abs(montant_raw)
            type_mouvement = TypeMouvement.DEBIT
        else:
            montant = montant_raw
            type_mouvement = TypeMouvement.CREDIT

        # Référence
        fitid = extraire("FITID") or ""

        # Libellé
        name = extraire("NAME") or ""
        memo = extraire("MEMO") or ""
        libelle = name if name else memo
        libelle_complement = memo if name and memo else None

        # Contrepartie
        payee = extraire("PAYEE")

        mouvement = MouvementBancaireImport(
            reference_banque=fitid,
            date_operation=date_op,
            montant=montant,
            type_mouvement=type_mouvement,
            libelle=libelle or "Opération",
            libelle_complement=libelle_complement,
            nom_contrepartie=payee,
            code_operation=trntype,
            ligne_source=ligne,
        )

        if not mouvement.reference_banque:
            mouvement.reference_banque = self._generer_reference(mouvement)

        return mouvement

    def _parse_ofx_xml(self, texte: str) -> Tuple[List[MouvementBancaireImport], Optional[Decimal], Optional[Decimal]]:
        """Parse OFX format XML."""
        mouvements: List[MouvementBancaireImport] = []
        solde_initial: Optional[Decimal] = None
        solde_final: Optional[Decimal] = None

        try:
            # Nettoyer pour XML valide
            texte = re.sub(r"<\?OFX[^>]*\?>", "", texte)
            root = ET.fromstring(texte)
        except ET.ParseError:
            # Fallback SGML
            return self._parse_ofx_sgml(texte)

        # Namespace OFX
        ns = {"ofx": "http://ofx.net/types/2003/04"}

        # Chercher transactions
        for i, stmttrn in enumerate(root.iter(), start=1):
            if stmttrn.tag.upper().endswith("STMTTRN"):
                mouvement = self._parse_stmttrn_xml(stmttrn, i)
                if mouvement:
                    mouvements.append(mouvement)

        return mouvements, solde_initial, solde_final

    def _parse_stmttrn_xml(self, elem: ET.Element, ligne: int) -> Optional[MouvementBancaireImport]:
        """Parse un élément STMTTRN XML."""

        def get_text(tag: str) -> Optional[str]:
            for child in elem.iter():
                if child.tag.upper().endswith(tag.upper()):
                    return child.text.strip() if child.text else None
            return None

        dtposted = get_text("DTPOSTED")
        if not dtposted:
            return None

        date_op = self._parse_date_ofx(dtposted)
        if not date_op:
            return None

        trnamt = get_text("TRNAMT")
        if not trnamt:
            return None

        montant_raw = self._nettoyer_montant(trnamt, ".")
        if not montant_raw:
            return None

        if montant_raw < 0:
            montant = abs(montant_raw)
            type_mouvement = TypeMouvement.DEBIT
        else:
            montant = montant_raw
            type_mouvement = TypeMouvement.CREDIT

        return MouvementBancaireImport(
            reference_banque=get_text("FITID") or "",
            date_operation=date_op,
            montant=montant,
            type_mouvement=type_mouvement,
            libelle=get_text("NAME") or get_text("MEMO") or "Opération",
            libelle_complement=get_text("MEMO") if get_text("NAME") else None,
            code_operation=get_text("TRNTYPE"),
            ligne_source=ligne,
        )

    def _parse_date_ofx(self, valeur: str) -> Optional[date]:
        """Parse une date OFX (YYYYMMDD ou YYYYMMDDHHMMSS)."""
        if not valeur:
            return None

        valeur = valeur.strip()[:8]  # Prendre juste la date

        try:
            return datetime.strptime(valeur, "%Y%m%d").date()
        except ValueError:
            return None


# =============================================================================
# PARSER QIF
# =============================================================================

class ParserQIF(ParserBancaire):
    """Parser pour fichiers QIF (Quicken Interchange Format)."""

    format = FormatImport.QIF

    def parse(self, contenu: bytes, nom_fichier: str) -> ResultatImport:
        """Parse un fichier QIF."""
        mouvements: List[MouvementBancaireImport] = []

        # Décoder
        try:
            texte = contenu.decode("utf-8")
        except UnicodeDecodeError:
            texte = contenu.decode("iso-8859-1", errors="ignore")

        # QIF utilise des blocs séparés par ^
        lignes = texte.split("\n")
        bloc_courant: Dict[str, str] = {}
        num_ligne = 0

        for ligne in lignes:
            num_ligne += 1
            ligne = ligne.strip()

            if not ligne:
                continue

            if ligne == "^":
                # Fin de transaction
                if bloc_courant:
                    mouvement = self._parse_bloc_qif(bloc_courant, num_ligne)
                    if mouvement:
                        mouvements.append(mouvement)
                bloc_courant = {}
                continue

            if ligne.startswith("!"):
                # Type de compte, ignorer
                continue

            # Parser champ
            code = ligne[0]
            valeur = ligne[1:].strip()
            bloc_courant[code] = valeur

        # Dernier bloc
        if bloc_courant:
            mouvement = self._parse_bloc_qif(bloc_courant, num_ligne)
            if mouvement:
                mouvements.append(mouvement)

        dates = [m.date_operation for m in mouvements if m.date_operation]

        return ResultatImport(
            succes=len(mouvements) > 0,
            format_detecte=self.format,
            compte_id=self.compte_id,
            fichier_nom=nom_fichier,
            nb_mouvements_importes=len(mouvements),
            nb_erreurs=len(self.erreurs),
            date_debut=min(dates) if dates else None,
            date_fin=max(dates) if dates else None,
            mouvements=mouvements,
            erreurs=self.erreurs,
            avertissements=self.avertissements,
        )

    def _parse_bloc_qif(self, bloc: Dict[str, str], ligne: int) -> Optional[MouvementBancaireImport]:
        """Parse un bloc QIF."""
        # D = Date
        date_str = bloc.get("D")
        if not date_str:
            return None

        date_op = self._parse_date_qif(date_str)
        if not date_op:
            return None

        # T = Montant
        montant_str = bloc.get("T")
        if not montant_str:
            return None

        montant_raw = self._nettoyer_montant(montant_str, ".")
        if not montant_raw:
            return None

        if montant_raw < 0:
            montant = abs(montant_raw)
            type_mouvement = TypeMouvement.DEBIT
        else:
            montant = montant_raw
            type_mouvement = TypeMouvement.CREDIT

        # P = Bénéficiaire / Libellé
        libelle = bloc.get("P") or bloc.get("M") or "Opération"

        # M = Mémo
        memo = bloc.get("M") if bloc.get("P") else None

        # N = Numéro chèque / référence
        reference = bloc.get("N") or ""

        # L = Catégorie
        categorie = bloc.get("L")

        mouvement = MouvementBancaireImport(
            reference_banque=reference,
            date_operation=date_op,
            montant=montant,
            type_mouvement=type_mouvement,
            libelle=libelle,
            libelle_complement=memo,
            categorie_banque=categorie,
            ligne_source=ligne,
        )

        if not mouvement.reference_banque:
            mouvement.reference_banque = self._generer_reference(mouvement)

        return mouvement

    def _parse_date_qif(self, valeur: str) -> Optional[date]:
        """Parse une date QIF (formats multiples)."""
        formats = [
            "%m/%d/%Y",      # US
            "%d/%m/%Y",      # EU
            "%m/%d'%Y",      # Quicken
            "%m-%d-%Y",
            "%d-%m-%Y",
            "%Y-%m-%d",
        ]

        valeur = valeur.strip().replace("'", "/")

        for fmt in formats:
            try:
                return datetime.strptime(valeur, fmt).date()
            except ValueError:
                continue

        return None


# =============================================================================
# PARSER CAMT.053 (ISO 20022)
# =============================================================================

class ParserCAMT053(ParserBancaire):
    """Parser pour fichiers CAMT.053 (ISO 20022 Bank Statement)."""

    format = FormatImport.CAMT053

    # Namespaces ISO 20022
    NS = {
        "camt": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02",
        "camt04": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.04",
        "camt08": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08",
    }

    def parse(self, contenu: bytes, nom_fichier: str) -> ResultatImport:
        """Parse un fichier CAMT.053."""
        mouvements: List[MouvementBancaireImport] = []
        solde_initial: Optional[Decimal] = None
        solde_final: Optional[Decimal] = None

        try:
            root = ET.fromstring(contenu)
        except ET.ParseError as e:
            self.erreurs.append(f"XML invalide: {str(e)}")
            return ResultatImport(
                succes=False,
                format_detecte=self.format,
                compte_id=self.compte_id,
                fichier_nom=nom_fichier,
                erreurs=self.erreurs,
            )

        # Détecter namespace
        ns = self._detecter_namespace(root)

        # Parcourir les statements
        for stmt in root.iter():
            if stmt.tag.endswith("}Stmt") or stmt.tag == "Stmt":
                mouvements_stmt, solde_i, solde_f = self._parse_statement(stmt, ns)
                mouvements.extend(mouvements_stmt)
                if solde_i is not None:
                    solde_initial = solde_i
                if solde_f is not None:
                    solde_final = solde_f

        dates = [m.date_operation for m in mouvements if m.date_operation]

        return ResultatImport(
            succes=len(mouvements) > 0,
            format_detecte=self.format,
            compte_id=self.compte_id,
            fichier_nom=nom_fichier,
            nb_mouvements_importes=len(mouvements),
            nb_erreurs=len(self.erreurs),
            date_debut=min(dates) if dates else None,
            date_fin=max(dates) if dates else None,
            solde_initial=solde_initial,
            solde_final=solde_final,
            mouvements=mouvements,
            erreurs=self.erreurs,
            avertissements=self.avertissements,
        )

    def _detecter_namespace(self, root: ET.Element) -> str:
        """Détecte le namespace utilisé."""
        tag = root.tag
        if "{" in tag:
            return tag[tag.index("{") + 1:tag.index("}")]
        return ""

    def _parse_statement(self, stmt: ET.Element, ns: str) -> Tuple[List[MouvementBancaireImport], Optional[Decimal], Optional[Decimal]]:
        """Parse un Statement CAMT.053."""
        mouvements: List[MouvementBancaireImport] = []
        solde_initial: Optional[Decimal] = None
        solde_final: Optional[Decimal] = None

        ns_prefix = f"{{{ns}}}" if ns else ""

        # Soldes
        for bal in stmt.iter():
            if bal.tag.endswith("}Bal") or bal.tag == "Bal":
                tp = self._get_text(bal, "Tp/CdOrPrtry/Cd", ns)
                amt = self._get_text(bal, "Amt", ns)

                if amt:
                    montant = self._nettoyer_montant(amt, ".")
                    if tp == "OPBD":  # Opening Booked
                        solde_initial = montant
                    elif tp == "CLBD":  # Closing Booked
                        solde_final = montant

        # Entrées
        ligne = 0
        for ntry in stmt.iter():
            if ntry.tag.endswith("}Ntry") or ntry.tag == "Ntry":
                ligne += 1
                mouvement = self._parse_entry(ntry, ns, ligne)
                if mouvement:
                    mouvements.append(mouvement)

        return mouvements, solde_initial, solde_final

    def _parse_entry(self, ntry: ET.Element, ns: str, ligne: int) -> Optional[MouvementBancaireImport]:
        """Parse une Entry CAMT.053."""

        # Montant
        amt = self._get_text(ntry, "Amt", ns)
        if not amt:
            return None

        montant = self._nettoyer_montant(amt, ".")
        if not montant:
            return None

        # Crédit/Débit
        cdt_dbt = self._get_text(ntry, "CdtDbtInd", ns)
        if cdt_dbt == "DBIT":
            type_mouvement = TypeMouvement.DEBIT
        else:
            type_mouvement = TypeMouvement.CREDIT

        # Devise
        devise = "EUR"
        amt_elem = self._find_element(ntry, "Amt", ns)
        if amt_elem is not None:
            devise = amt_elem.get("Ccy", "EUR")

        # Date
        date_str = self._get_text(ntry, "BookgDt/Dt", ns) or self._get_text(ntry, "ValDt/Dt", ns)
        if not date_str:
            return None

        date_op = self._parser_date(date_str, ["%Y-%m-%d"])
        if not date_op:
            return None

        date_val_str = self._get_text(ntry, "ValDt/Dt", ns)
        date_val = self._parser_date(date_val_str, ["%Y-%m-%d"]) if date_val_str else None

        # Références
        acct_svcr_ref = self._get_text(ntry, "AcctSvcrRef", ns) or ""
        end_to_end_id = self._get_text(ntry, "NtryDtls/TxDtls/Refs/EndToEndId", ns)

        # Libellé
        libelle_parts = []

        # RmtInf (informations de remise)
        rmt_inf = self._get_text(ntry, "NtryDtls/TxDtls/RmtInf/Ustrd", ns)
        if rmt_inf:
            libelle_parts.append(rmt_inf)

        # AddtlNtryInf
        addtl = self._get_text(ntry, "AddtlNtryInf", ns)
        if addtl and addtl not in libelle_parts:
            libelle_parts.append(addtl)

        libelle = " | ".join(libelle_parts) if libelle_parts else "Opération SEPA"

        # Contrepartie
        nom_contrepartie = None
        iban_contrepartie = None

        # Chercher dans RltdPties
        dbtr_nm = self._get_text(ntry, "NtryDtls/TxDtls/RltdPties/Dbtr/Nm", ns)
        cdtr_nm = self._get_text(ntry, "NtryDtls/TxDtls/RltdPties/Cdtr/Nm", ns)

        if type_mouvement == TypeMouvement.CREDIT and dbtr_nm:
            nom_contrepartie = dbtr_nm
            iban_contrepartie = self._get_text(ntry, "NtryDtls/TxDtls/RltdPties/DbtrAcct/Id/IBAN", ns)
        elif type_mouvement == TypeMouvement.DEBIT and cdtr_nm:
            nom_contrepartie = cdtr_nm
            iban_contrepartie = self._get_text(ntry, "NtryDtls/TxDtls/RltdPties/CdtrAcct/Id/IBAN", ns)

        # BIC
        bic_contrepartie = self._get_text(ntry, "NtryDtls/TxDtls/RltdAgts/DbtrAgt/FinInstnId/BIC", ns)
        if not bic_contrepartie:
            bic_contrepartie = self._get_text(ntry, "NtryDtls/TxDtls/RltdAgts/CdtrAgt/FinInstnId/BIC", ns)

        # Code opération
        code_op = self._get_text(ntry, "BkTxCd/Domn/Cd", ns)

        mouvement = MouvementBancaireImport(
            reference_banque=acct_svcr_ref,
            date_operation=date_op,
            date_valeur=date_val,
            montant=montant,
            type_mouvement=type_mouvement,
            devise=devise,
            libelle=libelle,
            nom_contrepartie=nom_contrepartie,
            iban_contrepartie=iban_contrepartie,
            bic_contrepartie=bic_contrepartie,
            reference_bout_en_bout=end_to_end_id,
            code_operation=code_op,
            ligne_source=ligne,
        )

        if not mouvement.reference_banque:
            mouvement.reference_banque = self._generer_reference(mouvement)

        return mouvement

    def _find_element(self, parent: ET.Element, path: str, ns: str) -> Optional[ET.Element]:
        """Trouve un élément par chemin."""
        parts = path.split("/")
        current = parent

        for part in parts:
            found = None
            ns_prefix = f"{{{ns}}}" if ns else ""

            for child in current:
                tag_name = child.tag.replace(ns_prefix, "")
                if tag_name == part:
                    found = child
                    break

            if found is None:
                return None
            current = found

        return current

    def _get_text(self, parent: ET.Element, path: str, ns: str) -> Optional[str]:
        """Récupère le texte d'un élément par chemin."""
        elem = self._find_element(parent, path, ns)
        if elem is not None and elem.text:
            return elem.text.strip()
        return None


# =============================================================================
# PARSER MT940 (SWIFT)
# =============================================================================

class ParserMT940(ParserBancaire):
    """Parser pour fichiers MT940 (SWIFT Bank Statement)."""

    format = FormatImport.MT940

    def parse(self, contenu: bytes, nom_fichier: str) -> ResultatImport:
        """Parse un fichier MT940."""
        mouvements: List[MouvementBancaireImport] = []
        solde_initial: Optional[Decimal] = None
        solde_final: Optional[Decimal] = None

        # Décoder
        try:
            texte = contenu.decode("utf-8")
        except UnicodeDecodeError:
            texte = contenu.decode("iso-8859-1", errors="ignore")

        # MT940 utilise des tags :XX:
        lignes = texte.split("\n")

        tag_courant = ""
        valeur_courante = ""
        tags: Dict[str, List[str]] = {}

        for ligne in lignes:
            ligne = ligne.rstrip("\r")

            # Nouveau tag
            match = re.match(r":(\d{2}[A-Z]?):(.*)$", ligne)
            if match:
                # Sauvegarder tag précédent
                if tag_courant:
                    if tag_courant not in tags:
                        tags[tag_courant] = []
                    tags[tag_courant].append(valeur_courante)

                tag_courant = match.group(1)
                valeur_courante = match.group(2)
            elif ligne.startswith("-") and tag_courant:
                # Fin de message
                if tag_courant:
                    if tag_courant not in tags:
                        tags[tag_courant] = []
                    tags[tag_courant].append(valeur_courante)
                tag_courant = ""
                valeur_courante = ""
            elif tag_courant:
                # Continuation
                valeur_courante += ligne

        # Dernier tag
        if tag_courant:
            if tag_courant not in tags:
                tags[tag_courant] = []
            tags[tag_courant].append(valeur_courante)

        # :60F: ou :60M: = Solde initial
        for tag in ["60F", "60M"]:
            if tag in tags and tags[tag]:
                solde_initial = self._parse_solde_mt940(tags[tag][0])
                break

        # :62F: ou :62M: = Solde final
        for tag in ["62F", "62M"]:
            if tag in tags and tags[tag]:
                solde_final = self._parse_solde_mt940(tags[tag][0])
                break

        # :61: = Transactions
        if "61" in tags:
            for i, trans_line in enumerate(tags["61"], start=1):
                # :86: info complémentaire
                info_ligne = tags.get("86", [None] * len(tags["61"]))
                info = info_ligne[i - 1] if i - 1 < len(info_ligne) else None

                mouvement = self._parse_transaction_mt940(trans_line, info, i)
                if mouvement:
                    mouvements.append(mouvement)

        dates = [m.date_operation for m in mouvements if m.date_operation]

        return ResultatImport(
            succes=len(mouvements) > 0,
            format_detecte=self.format,
            compte_id=self.compte_id,
            fichier_nom=nom_fichier,
            nb_mouvements_importes=len(mouvements),
            nb_erreurs=len(self.erreurs),
            date_debut=min(dates) if dates else None,
            date_fin=max(dates) if dates else None,
            solde_initial=solde_initial,
            solde_final=solde_final,
            mouvements=mouvements,
            erreurs=self.erreurs,
            avertissements=self.avertissements,
        )

    def _parse_solde_mt940(self, valeur: str) -> Optional[Decimal]:
        """Parse un solde MT940 (ex: C210915EUR1234,56)."""
        # Format: [C/D]YYMMDDCCY[montant]
        match = re.match(r"([CD])(\d{6})([A-Z]{3})([\d,\.]+)", valeur)
        if not match:
            return None

        signe = match.group(1)
        montant_str = match.group(4).replace(",", ".")

        try:
            montant = Decimal(montant_str)
            if signe == "D":
                montant = -montant
            return montant
        except InvalidOperation:
            return None

    def _parse_transaction_mt940(self, ligne_61: str, ligne_86: Optional[str], num: int) -> Optional[MouvementBancaireImport]:
        """Parse une transaction MT940."""
        # Format :61: YYMMDD[YYMMDD][C/D/RC/RD][montant]NXXX[//ref][BR ref]

        # Date (YYMMDD)
        date_str = ligne_61[:6]
        try:
            annee = int(date_str[:2])
            annee = 2000 + annee if annee < 70 else 1900 + annee
            mois = int(date_str[2:4])
            jour = int(date_str[4:6])
            date_op = date(annee, mois, jour)
        except (ValueError, IndexError):
            return None

        # Date valeur optionnelle
        reste = ligne_61[6:]
        date_val = None
        if reste[:4].isdigit():
            try:
                mois_v = int(reste[:2])
                jour_v = int(reste[2:4])
                date_val = date(date_op.year, mois_v, jour_v)
                reste = reste[4:]
            except ValueError:
                pass

        # Crédit/Débit
        if reste.startswith("RC") or reste.startswith("C"):
            type_mouvement = TypeMouvement.CREDIT
            reste = reste[2:] if reste.startswith("RC") else reste[1:]
        elif reste.startswith("RD") or reste.startswith("D"):
            type_mouvement = TypeMouvement.DEBIT
            reste = reste[2:] if reste.startswith("RD") else reste[1:]
        else:
            type_mouvement = TypeMouvement.DEBIT

        # Montant (avant N ou F)
        match_montant = re.match(r"([\d,\.]+)([NF])", reste)
        if not match_montant:
            return None

        montant_str = match_montant.group(1).replace(",", ".")
        try:
            montant = Decimal(montant_str)
        except InvalidOperation:
            return None

        reste = reste[len(match_montant.group(0)):]

        # Type opération (3 caractères après N/F)
        code_op = reste[:3] if len(reste) >= 3 else ""
        reste = reste[3:]

        # Référence (après //)
        reference = ""
        if "//" in reste:
            reference = reste.split("//")[1].split()[0] if "//" in reste else ""

        # Libellé depuis :86:
        libelle = ligne_86 if ligne_86 else f"Opération {code_op}"

        # Parser :86: pour extraire des infos
        nom_contrepartie = None
        iban_contrepartie = None

        if ligne_86:
            # Format structuré ?XXX (codes SWIFT)
            if ligne_86.startswith("?"):
                # Parser champs structurés
                champs_86 = self._parse_86_structure(ligne_86)
                libelle = champs_86.get("20", "") + " " + champs_86.get("21", "")
                libelle = libelle.strip() or ligne_86
                nom_contrepartie = champs_86.get("32") or champs_86.get("33")
            else:
                # Non structuré
                libelle = ligne_86

        mouvement = MouvementBancaireImport(
            reference_banque=reference,
            date_operation=date_op,
            date_valeur=date_val,
            montant=montant,
            type_mouvement=type_mouvement,
            libelle=libelle.strip(),
            nom_contrepartie=nom_contrepartie,
            iban_contrepartie=iban_contrepartie,
            code_operation=code_op,
            ligne_source=num,
        )

        if not mouvement.reference_banque:
            mouvement.reference_banque = self._generer_reference(mouvement)

        return mouvement

    def _parse_86_structure(self, ligne: str) -> Dict[str, str]:
        """Parse une ligne :86: structurée."""
        champs: Dict[str, str] = {}

        # Format: ?20texte?21texte?32texte...
        pattern = re.compile(r"\?(\d{2})([^?]*)")

        for match in pattern.finditer(ligne):
            code = match.group(1)
            valeur = match.group(2).strip()
            champs[code] = valeur

        return champs


# =============================================================================
# SERVICE D'IMPORT
# =============================================================================

class ImportBancaireService:
    """Service d'import de relevés bancaires."""

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id

    def detecter_format(self, contenu: bytes, nom_fichier: str) -> FormatImport:
        """Détecte automatiquement le format du fichier."""
        nom_lower = nom_fichier.lower()

        # Par extension
        if nom_lower.endswith(".ofx"):
            return FormatImport.OFX
        elif nom_lower.endswith(".qif"):
            return FormatImport.QIF
        elif nom_lower.endswith(".xml"):
            # Vérifier si CAMT.053
            try:
                texte = contenu.decode("utf-8", errors="ignore")
                if "camt.053" in texte.lower() or "BkToCstmrStmt" in texte:
                    return FormatImport.CAMT053
            except:
                pass
        elif nom_lower.endswith(".sta") or nom_lower.endswith(".mt940"):
            return FormatImport.MT940

        # Par contenu
        try:
            texte = contenu.decode("utf-8", errors="ignore")
        except:
            texte = contenu.decode("iso-8859-1", errors="ignore")

        # OFX
        if "<OFX>" in texte.upper() or "OFXHEADER" in texte.upper():
            return FormatImport.OFX

        # QIF
        if texte.strip().startswith("!Type:"):
            return FormatImport.QIF

        # MT940
        if ":20:" in texte and ":60F:" in texte:
            return FormatImport.MT940

        # CAMT.053
        if "camt.053" in texte.lower() or "<BkToCstmrStmt>" in texte:
            return FormatImport.CAMT053

        # Par défaut CSV
        return FormatImport.CSV

    def detecter_banque_csv(self, contenu: bytes) -> str:
        """Détecte la banque d'origine d'un fichier CSV."""
        try:
            texte = contenu.decode("utf-8")
        except UnicodeDecodeError:
            try:
                texte = contenu.decode("iso-8859-1")
            except:
                return "generique"

        premiere_ligne = texte.split("\n")[0].lower() if texte else ""

        # Détection par colonnes caractéristiques
        texte_lower = texte.lower()[:500]
        if "crédit agricole" in texte_lower or "credit agricole" in texte_lower:
            return "credit_agricole"
        elif "bnp" in texte.lower()[:500]:
            return "bnp"
        elif "société générale" in texte.lower()[:500]:
            return "societe_generale"
        elif "la banque postale" in texte.lower()[:500]:
            return "la_banque_postale"
        elif "caisse d'épargne" in texte.lower()[:500]:
            return "caisse_epargne"
        elif "boursorama" in texte.lower()[:500] or "dateop" in premiere_ligne:
            return "boursorama"
        elif "fortuneo" in texte.lower()[:500]:
            return "fortuneo"
        elif "lcl" in texte.lower()[:500]:
            return "lcl"
        elif "crédit mutuel" in texte.lower()[:500] or "cic" in texte.lower()[:500]:
            return "credit_mutuel"

        return "generique"

    def importer(
        self,
        compte_id: UUID,
        contenu: bytes,
        nom_fichier: str,
        format_force: Optional[FormatImport] = None,
        profil_csv: Optional[str] = None,
    ) -> ResultatImport:
        """
        Importe un relevé bancaire.

        Args:
            compte_id: ID du compte bancaire
            contenu: Contenu binaire du fichier
            nom_fichier: Nom du fichier
            format_force: Forcer un format (auto-détection sinon)
            profil_csv: Profil CSV à utiliser (auto-détection sinon)

        Returns:
            ResultatImport avec les mouvements parsés
        """
        # Détection format
        format_import = format_force or self.detecter_format(contenu, nom_fichier)

        logger.info(
            "import_bancaire_debut",
            tenant_id=str(self.tenant_id),
            compte_id=str(compte_id),
            fichier=nom_fichier,
            format=format_import.value,
        )

        # Créer le parser approprié
        parser: ParserBancaire

        if format_import == FormatImport.CSV:
            profil = profil_csv or self.detecter_banque_csv(contenu)
            parser = ParserCSV(self.tenant_id, compte_id, profil)
            logger.info("csv_profil_detecte", profil=profil)
        elif format_import == FormatImport.OFX:
            parser = ParserOFX(self.tenant_id, compte_id)
        elif format_import == FormatImport.QIF:
            parser = ParserQIF(self.tenant_id, compte_id)
        elif format_import == FormatImport.CAMT053:
            parser = ParserCAMT053(self.tenant_id, compte_id)
        elif format_import == FormatImport.MT940:
            parser = ParserMT940(self.tenant_id, compte_id)
        else:
            return ResultatImport(
                succes=False,
                format_detecte=format_import,
                compte_id=compte_id,
                fichier_nom=nom_fichier,
                erreurs=[f"Format non supporté: {format_import}"],
            )

        # Parser
        resultat = parser.parse(contenu, nom_fichier)

        logger.info(
            "import_bancaire_fin",
            succes=resultat.succes,
            nb_mouvements=resultat.nb_mouvements_importes,
            nb_erreurs=resultat.nb_erreurs,
            date_debut=str(resultat.date_debut) if resultat.date_debut else None,
            date_fin=str(resultat.date_fin) if resultat.date_fin else None,
        )

        return resultat

    async def importer_et_creer(
        self,
        compte_id: UUID,
        contenu: bytes,
        nom_fichier: str,
        format_force: Optional[FormatImport] = None,
        profil_csv: Optional[str] = None,
        rapprocher_auto: bool = True,
    ) -> ResultatImport:
        """
        Importe un relevé et crée les mouvements en base.

        Args:
            compte_id: ID du compte bancaire
            contenu: Contenu binaire du fichier
            nom_fichier: Nom du fichier
            format_force: Forcer un format
            profil_csv: Profil CSV
            rapprocher_auto: Lancer le rapprochement automatique après import

        Returns:
            ResultatImport avec statistiques de création
        """
        from moteur.db import Database
        from moteur.rapprochement_service import RapprochementService

        # Parser le fichier
        resultat = self.importer(compte_id, contenu, nom_fichier, format_force, profil_csv)

        if not resultat.succes or not resultat.mouvements:
            return resultat

        # Vérifier doublons et créer mouvements
        nb_crees = 0
        nb_doublons = 0

        for mouvement in resultat.mouvements:
            # Vérifier doublon par référence banque
            existant = Database.query(
                "mouvements_bancaires",
                self.tenant_id,
                filters={
                    "compte_bancaire_id": str(compte_id),
                    "reference_banque": mouvement.reference_banque,
                },
                limit=1,
            )

            if existant:
                nb_doublons += 1
                continue

            # Créer le mouvement
            data = {
                "compte_bancaire_id": str(compte_id),
                "reference_banque": mouvement.reference_banque,
                "date_operation": mouvement.date_operation.isoformat(),
                "date_valeur": mouvement.date_valeur.isoformat() if mouvement.date_valeur else None,
                "montant": float(mouvement.montant),
                "sens": mouvement.type_mouvement.value,
                "devise": mouvement.devise,
                "libelle_banque": mouvement.libelle[:500] if mouvement.libelle else "",
                "libelle_complement": mouvement.libelle_complement[:500] if mouvement.libelle_complement else None,
                "nom_contrepartie": mouvement.nom_contrepartie,
                "iban_contrepartie": mouvement.iban_contrepartie,
                "bic_contrepartie": mouvement.bic_contrepartie,
                "reference_client": mouvement.reference_client,
                "reference_bout_en_bout": mouvement.reference_bout_en_bout,
                "code_operation_banque": mouvement.code_operation,
                "categorie_banque": mouvement.categorie_banque,
                "statut": "A_TRAITER",
                "source": "IMPORT",
                "donnees_import": mouvement.donnees_brutes,
            }

            Database.insert("mouvements_bancaires", self.tenant_id, data)
            nb_crees += 1

        resultat.nb_mouvements_importes = nb_crees
        resultat.nb_mouvements_ignores = nb_doublons

        logger.info(
            "mouvements_crees",
            nb_crees=nb_crees,
            nb_doublons=nb_doublons,
        )

        # Lancer rapprochement automatique si demandé
        if rapprocher_auto and nb_crees > 0:
            service_rapprochement = RapprochementService(self.tenant_id)
            await service_rapprochement.rapprocher_tous(compte_id)

        return resultat


# =============================================================================
# FACTORY
# =============================================================================

def get_parser(
    format_import: FormatImport,
    tenant_id: UUID,
    compte_id: UUID,
    profil_csv: str = "generique",
) -> ParserBancaire:
    """Factory pour obtenir le bon parser."""
    if format_import == FormatImport.CSV:
        return ParserCSV(tenant_id, compte_id, profil_csv)
    elif format_import == FormatImport.OFX:
        return ParserOFX(tenant_id, compte_id)
    elif format_import == FormatImport.QIF:
        return ParserQIF(tenant_id, compte_id)
    elif format_import == FormatImport.CAMT053:
        return ParserCAMT053(tenant_id, compte_id)
    elif format_import == FormatImport.MT940:
        return ParserMT940(tenant_id, compte_id)
    else:
        raise ValueError(f"Format non supporté: {format_import}")
