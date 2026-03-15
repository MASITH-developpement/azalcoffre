# =============================================================================
# Tests - Import Bancaire
# =============================================================================
"""
Tests pour le parser d'import de relevés bancaires.
"""

import pytest
from decimal import Decimal
from uuid import uuid4
from datetime import date

from moteur.import_bancaire import (
    ImportBancaireService,
    FormatImport,
    ParserCSV,
    ParserOFX,
    ParserQIF,
    ParserCAMT053,
    ParserMT940,
    TypeMouvement,
    PROFILS_CSV_BANQUES,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.fixture
def compte_id():
    return uuid4()


@pytest.fixture
def service(tenant_id):
    return ImportBancaireService(tenant_id)


# =============================================================================
# TESTS DETECTION FORMAT
# =============================================================================

class TestDetectionFormat:
    """Tests de détection automatique du format."""

    def test_detecte_csv_par_extension(self, service):
        contenu = b"Date;Libelle;Montant\n01/01/2024;Test;100,00"
        assert service.detecter_format(contenu, "releve.csv") == FormatImport.CSV

    def test_detecte_ofx_par_extension(self, service):
        contenu = b"<OFX></OFX>"
        assert service.detecter_format(contenu, "releve.ofx") == FormatImport.OFX

    def test_detecte_qif_par_extension(self, service):
        contenu = b"!Type:Bank\nD01/01/2024"
        assert service.detecter_format(contenu, "releve.qif") == FormatImport.QIF

    def test_detecte_mt940_par_extension(self, service):
        contenu = b":20:STMT\n:60F:C240101EUR1000,00"
        assert service.detecter_format(contenu, "releve.sta") == FormatImport.MT940

    def test_detecte_ofx_par_contenu(self, service):
        contenu = b"OFXHEADER:100\n<OFX><BANKMSGSRSV1></OFX>"
        assert service.detecter_format(contenu, "fichier.txt") == FormatImport.OFX

    def test_detecte_qif_par_contenu(self, service):
        contenu = b"!Type:Bank\nD01/01/2024\nT-50.00\n^"
        assert service.detecter_format(contenu, "fichier.txt") == FormatImport.QIF

    def test_detecte_mt940_par_contenu(self, service):
        contenu = b":20:STATEMENT\n:60F:C240101EUR1234,56\n:61:2401010101D100,00NTRFTEST"
        assert service.detecter_format(contenu, "fichier.txt") == FormatImport.MT940


class TestDetectionBanqueCSV:
    """Tests de détection de la banque pour les CSV."""

    def test_detecte_credit_agricole(self, service):
        contenu = b"Releve Compte - Credit Agricole\nDate;Libelle;Debit;Credit"
        assert service.detecter_banque_csv(contenu) == "credit_agricole"

    def test_detecte_bnp(self, service):
        contenu = b"BNP Paribas - Releve de compte\nDate;Valeur;Libelle"
        assert service.detecter_banque_csv(contenu) == "bnp"

    def test_detecte_boursorama(self, service):
        contenu = b"dateOp;dateVal;label;amount;category"
        assert service.detecter_banque_csv(contenu) == "boursorama"

    def test_fallback_generique(self, service):
        contenu = b"Date;Description;Montant"
        assert service.detecter_banque_csv(contenu) == "generique"


# =============================================================================
# TESTS PARSER CSV
# =============================================================================

class TestParserCSV:
    """Tests du parser CSV."""

    def test_parse_csv_simple(self, tenant_id, compte_id):
        parser = ParserCSV(tenant_id, compte_id, "generique")
        contenu = b"Date;Libelle;Montant\n01/01/2024;Achat supermarche;-50,00\n02/01/2024;Virement recu;100,00"

        resultat = parser.parse(contenu, "test.csv")

        assert resultat.succes
        assert resultat.nb_mouvements_importes == 2
        assert len(resultat.mouvements) == 2

        # Premier mouvement (débit)
        m1 = resultat.mouvements[0]
        assert m1.date_operation == date(2024, 1, 1)
        assert m1.montant == Decimal("50.00")
        assert m1.type_mouvement == TypeMouvement.DEBIT
        assert "supermarche" in m1.libelle.lower()

        # Deuxième mouvement (crédit)
        m2 = resultat.mouvements[1]
        assert m2.date_operation == date(2024, 1, 2)
        assert m2.montant == Decimal("100.00")
        assert m2.type_mouvement == TypeMouvement.CREDIT

    def test_parse_csv_debit_credit_separes(self, tenant_id, compte_id):
        parser = ParserCSV(tenant_id, compte_id, "generique")
        contenu = b"Date;Libelle;Debit;Credit\n01/01/2024;Retrait DAB;50,00;\n02/01/2024;Salaire;;2000,00"

        resultat = parser.parse(contenu, "test.csv")

        assert resultat.succes
        assert len(resultat.mouvements) == 2

        assert resultat.mouvements[0].type_mouvement == TypeMouvement.DEBIT
        assert resultat.mouvements[0].montant == Decimal("50.00")

        assert resultat.mouvements[1].type_mouvement == TypeMouvement.CREDIT
        assert resultat.mouvements[1].montant == Decimal("2000.00")

    def test_parse_csv_encodage_latin1(self, tenant_id, compte_id):
        parser = ParserCSV(tenant_id, compte_id, "credit_agricole")
        # Contenu en ISO-8859-1 avec caractères accentués
        contenu = "Date;Libellé;Montant\n01/01/2024;Café épicerie;-5,50".encode("iso-8859-1")

        resultat = parser.parse(contenu, "test.csv")

        assert resultat.succes
        assert len(resultat.mouvements) == 1

    def test_parse_csv_periode(self, tenant_id, compte_id):
        parser = ParserCSV(tenant_id, compte_id, "generique")
        contenu = b"Date;Libelle;Montant\n15/01/2024;Op1;-10\n20/01/2024;Op2;-20\n10/01/2024;Op3;-30"

        resultat = parser.parse(contenu, "test.csv")

        assert resultat.date_debut == date(2024, 1, 10)
        assert resultat.date_fin == date(2024, 1, 20)

    def test_parse_csv_reference_auto_generee(self, tenant_id, compte_id):
        parser = ParserCSV(tenant_id, compte_id, "generique")
        contenu = b"Date;Libelle;Montant\n01/01/2024;Test;-10"

        resultat = parser.parse(contenu, "test.csv")

        assert resultat.mouvements[0].reference_banque.startswith("IMP-")


# =============================================================================
# TESTS PARSER OFX
# =============================================================================

class TestParserOFX:
    """Tests du parser OFX."""

    def test_parse_ofx_sgml(self, tenant_id, compte_id):
        parser = ParserOFX(tenant_id, compte_id)
        contenu = b"""OFXHEADER:100
DATA:OFXSGML
<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20240115
<TRNAMT>-50.00
<FITID>20240115001
<NAME>Achat Amazon
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20240120
<TRNAMT>1500.00
<FITID>20240120001
<NAME>Virement salaire
</STMTTRN>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>"""

        resultat = parser.parse(contenu, "test.ofx")

        assert resultat.succes
        assert len(resultat.mouvements) == 2

        m1 = resultat.mouvements[0]
        assert m1.date_operation == date(2024, 1, 15)
        assert m1.montant == Decimal("50.00")
        assert m1.type_mouvement == TypeMouvement.DEBIT
        assert m1.reference_banque == "20240115001"

        m2 = resultat.mouvements[1]
        assert m2.montant == Decimal("1500.00")
        assert m2.type_mouvement == TypeMouvement.CREDIT


# =============================================================================
# TESTS PARSER QIF
# =============================================================================

class TestParserQIF:
    """Tests du parser QIF."""

    def test_parse_qif_simple(self, tenant_id, compte_id):
        parser = ParserQIF(tenant_id, compte_id)
        contenu = b"""!Type:Bank
D01/15/2024
T-75.50
PRestaurant Le Gourmet
LRepas affaires
^
D01/20/2024
T500.00
PClient ABC
LPaiement facture
^"""

        resultat = parser.parse(contenu, "test.qif")

        assert resultat.succes
        assert len(resultat.mouvements) == 2

        m1 = resultat.mouvements[0]
        assert m1.montant == Decimal("75.50")
        assert m1.type_mouvement == TypeMouvement.DEBIT
        assert "Restaurant" in m1.libelle

        m2 = resultat.mouvements[1]
        assert m2.montant == Decimal("500.00")
        assert m2.type_mouvement == TypeMouvement.CREDIT


# =============================================================================
# TESTS PARSER CAMT.053
# =============================================================================

class TestParserCAMT053:
    """Tests du parser CAMT.053."""

    def test_parse_camt053_simple(self, tenant_id, compte_id):
        parser = ParserCAMT053(tenant_id, compte_id)
        contenu = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
<BkToCstmrStmt>
<Stmt>
<Ntry>
<Amt Ccy="EUR">150.00</Amt>
<CdtDbtInd>DBIT</CdtDbtInd>
<BookgDt><Dt>2024-01-15</Dt></BookgDt>
<AcctSvcrRef>REF001</AcctSvcrRef>
<AddtlNtryInf>Paiement fournisseur</AddtlNtryInf>
</Ntry>
<Ntry>
<Amt Ccy="EUR">500.00</Amt>
<CdtDbtInd>CRDT</CdtDbtInd>
<BookgDt><Dt>2024-01-20</Dt></BookgDt>
<AcctSvcrRef>REF002</AcctSvcrRef>
<AddtlNtryInf>Encaissement client</AddtlNtryInf>
</Ntry>
</Stmt>
</BkToCstmrStmt>
</Document>"""

        resultat = parser.parse(contenu, "test.xml")

        assert resultat.succes
        assert len(resultat.mouvements) == 2

        m1 = resultat.mouvements[0]
        assert m1.montant == Decimal("150.00")
        assert m1.type_mouvement == TypeMouvement.DEBIT
        assert m1.devise == "EUR"
        assert m1.reference_banque == "REF001"

        m2 = resultat.mouvements[1]
        assert m2.montant == Decimal("500.00")
        assert m2.type_mouvement == TypeMouvement.CREDIT


# =============================================================================
# TESTS PARSER MT940
# =============================================================================

class TestParserMT940:
    """Tests du parser MT940."""

    def test_parse_mt940_simple(self, tenant_id, compte_id):
        parser = ParserMT940(tenant_id, compte_id)
        contenu = b""":20:STMT240115
:25:FR7612345678901234567890123
:28C:1/1
:60F:C240101EUR5000,00
:61:2401150115D100,00NTRFPMT001//REF001
:86:Paiement facture 2024-001
:61:2401200120C500,00NTRFPMT002//REF002
:86:Encaissement client XYZ
:62F:C240120EUR5400,00
-"""

        resultat = parser.parse(contenu, "test.sta")

        assert resultat.succes
        assert len(resultat.mouvements) == 2

        # Soldes
        assert resultat.solde_initial == Decimal("5000.00")
        assert resultat.solde_final == Decimal("5400.00")

        # Mouvements
        m1 = resultat.mouvements[0]
        assert m1.date_operation == date(2024, 1, 15)
        assert m1.montant == Decimal("100.00")
        assert m1.type_mouvement == TypeMouvement.DEBIT

        m2 = resultat.mouvements[1]
        assert m2.date_operation == date(2024, 1, 20)
        assert m2.montant == Decimal("500.00")
        assert m2.type_mouvement == TypeMouvement.CREDIT


# =============================================================================
# TESTS PROFILS BANQUES
# =============================================================================

class TestProfilsBanques:
    """Tests des profils CSV par banque."""

    def test_profils_existent(self):
        banques_attendues = [
            "credit_agricole",
            "bnp",
            "societe_generale",
            "la_banque_postale",
            "caisse_epargne",
            "boursorama",
            "fortuneo",
            "lcl",
            "credit_mutuel",
            "generique",
        ]

        for banque in banques_attendues:
            assert banque in PROFILS_CSV_BANQUES, f"Profil manquant: {banque}"

    def test_profils_ont_colonnes_requises(self):
        colonnes_min = ["date_operation", "libelle"]

        for code, profil in PROFILS_CSV_BANQUES.items():
            colonnes = profil.get("colonnes", {})
            for col in colonnes_min:
                assert col in colonnes, f"Colonne {col} manquante dans profil {code}"


# =============================================================================
# TESTS SERVICE IMPORT
# =============================================================================

class TestImportBancaireService:
    """Tests du service d'import."""

    def test_import_csv_complet(self, tenant_id, compte_id):
        service = ImportBancaireService(tenant_id)

        contenu = b"Date;Libelle;Montant\n01/01/2024;Test 1;-100\n02/01/2024;Test 2;200"

        resultat = service.importer(
            compte_id=compte_id,
            contenu=contenu,
            nom_fichier="releve.csv",
        )

        assert resultat.succes
        assert resultat.format_detecte == FormatImport.CSV
        assert resultat.nb_mouvements_importes == 2
        assert len(resultat.erreurs) == 0

    def test_import_avec_format_force(self, tenant_id, compte_id):
        service = ImportBancaireService(tenant_id)

        # Contenu CSV mais on force OFX (devrait échouer proprement)
        contenu = b"Date;Libelle;Montant\n01/01/2024;Test;-100"

        resultat = service.importer(
            compte_id=compte_id,
            contenu=contenu,
            nom_fichier="releve.txt",
            format_force=FormatImport.OFX,  # Forcé
        )

        # OFX parser ne trouvera pas de transactions
        assert resultat.nb_mouvements_importes == 0


# =============================================================================
# TESTS EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests des cas limites."""

    def test_fichier_vide(self, tenant_id, compte_id):
        parser = ParserCSV(tenant_id, compte_id)
        resultat = parser.parse(b"", "vide.csv")

        assert not resultat.succes or resultat.nb_mouvements_importes == 0

    def test_montant_zero_ignore(self, tenant_id, compte_id):
        parser = ParserCSV(tenant_id, compte_id)
        contenu = b"Date;Libelle;Montant\n01/01/2024;Test;0"

        resultat = parser.parse(contenu, "test.csv")

        # Les montants à zéro sont ignorés
        assert len(resultat.mouvements) == 0

    def test_date_invalide(self, tenant_id, compte_id):
        parser = ParserCSV(tenant_id, compte_id)
        contenu = b"Date;Libelle;Montant\n99/99/2024;Test;-100"

        resultat = parser.parse(contenu, "test.csv")

        # Ligne ignorée avec avertissement
        assert len(resultat.mouvements) == 0
        assert len(resultat.avertissements) > 0

    def test_montant_format_francais(self, tenant_id, compte_id):
        parser = ParserCSV(tenant_id, compte_id)
        contenu = b"Date;Libelle;Montant\n01/01/2024;Test;-1 234,56"

        resultat = parser.parse(contenu, "test.csv")

        assert len(resultat.mouvements) == 1
        assert resultat.mouvements[0].montant == Decimal("1234.56")

    def test_reference_unique_generee(self, tenant_id, compte_id):
        parser = ParserCSV(tenant_id, compte_id)
        contenu = b"Date;Libelle;Montant\n01/01/2024;Test;-100\n01/01/2024;Test;-100"

        resultat = parser.parse(contenu, "test.csv")

        # Même date/montant/libellé = même hash = même référence
        refs = [m.reference_banque for m in resultat.mouvements]
        assert refs[0] == refs[1]  # Doublons potentiels détectés par référence
