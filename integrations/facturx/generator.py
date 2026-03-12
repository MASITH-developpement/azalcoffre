# =============================================================================
# AZALPLUS - Générateur Factur-X Principal
# =============================================================================
"""
Orchestrateur pour la génération de factures Factur-X complètes.

Combine:
- Génération XML EN16931 (xml_builder.py)
- Conversion PDF/A-3 (pdf_a3.py)
- Validation conformité

Profils Factur-X supportés:
- MINIMUM: Données essentielles uniquement
- BASIC WL: Pas de ligne de détail
- BASIC: Lignes de détail basiques
- EN16931 (COMFORT): Profil complet recommandé
- EXTENDED: Extensions propriétaires
"""

import io
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Union
from uuid import UUID

from .xml_builder import XMLBuilder, InvoiceData, from_facture, Party, Address, InvoiceLine, PaymentTerms
from .pdf_a3 import PDFAConverter, create_facturx_pdf

logger = logging.getLogger(__name__)


class FacturXProfile(str, Enum):
    """Profils de conformité Factur-X."""
    MINIMUM = "MINIMUM"
    BASIC_WL = "BASICWL"
    BASIC = "BASIC"
    EN16931 = "EN16931"  # Recommandé
    EXTENDED = "EXTENDED"


@dataclass
class FacturXResult:
    """Résultat de génération Factur-X."""
    pdf_content: bytes
    xml_content: str
    invoice_number: str
    profile: FacturXProfile
    is_valid: bool
    validation_errors: list[str]
    metadata: dict


class FacturXGenerator:
    """
    Générateur de factures Factur-X conformes.

    Usage:
        generator = FacturXGenerator(profile=FacturXProfile.EN16931)
        result = generator.generate(
            pdf_content=pdf_bytes,
            invoice_data=invoice_dict
        )

        if result.is_valid:
            # Utiliser result.pdf_content (PDF/A-3 avec XML embarqué)
            save_pdf(result.pdf_content)
    """

    # Champs requis par profil (mapped to InvoiceData field names)
    REQUIRED_FIELDS = {
        FacturXProfile.MINIMUM: [
            "invoice_number", "invoice_date", "seller_name", "seller_tva",
            "buyer_name", "total_ttc", "currency_code"
        ],
        FacturXProfile.BASIC_WL: [
            "invoice_number", "invoice_date", "seller_name", "seller_tva",
            "seller_address", "buyer_name", "buyer_address",
            "total_ht", "total_tva", "total_ttc", "currency_code"
        ],
        FacturXProfile.BASIC: [
            "invoice_number", "invoice_date", "seller_name", "seller_tva",
            "seller_address", "buyer_name", "buyer_address",
            "lines", "total_ht", "total_tva", "total_ttc", "currency_code"
        ],
        FacturXProfile.EN16931: [
            "invoice_number", "invoice_date", "due_date",
            "seller_name", "seller_tva", "seller_siret", "seller_address",
            "buyer_name", "buyer_siret", "buyer_address",
            "lines", "total_ht", "total_tva", "total_ttc",
            "currency_code", "payment_terms"
        ],
        FacturXProfile.EXTENDED: [
            # Même que EN16931 + extensions
            "invoice_number", "invoice_date", "due_date",
            "seller_name", "seller_tva", "seller_siret", "seller_address",
            "buyer_name", "buyer_siret", "buyer_address",
            "lines", "total_ht", "total_tva", "total_ttc",
            "currency_code", "payment_terms"
        ]
    }

    def __init__(
        self,
        profile: FacturXProfile = FacturXProfile.EN16931,
        validate_on_generate: bool = True
    ):
        """
        Initialiser le générateur.

        Args:
            profile: Profil Factur-X à utiliser
            validate_on_generate: Valider automatiquement à la génération
        """
        self.profile = profile
        self.validate_on_generate = validate_on_generate
        self.xml_builder = XMLBuilder()
        self.pdf_converter = PDFAConverter()

    def generate(
        self,
        pdf_content: bytes,
        invoice_data: Union[dict, InvoiceData],
        validate: Optional[bool] = None
    ) -> FacturXResult:
        """
        Générer une facture Factur-X complète.

        Args:
            pdf_content: PDF source en bytes
            invoice_data: Données facture (dict ou InvoiceData)
            validate: Forcer validation (override validate_on_generate)

        Returns:
            FacturXResult avec PDF/A-3 et métadonnées
        """
        errors = []

        # Convertir dict en InvoiceData si nécessaire
        if isinstance(invoice_data, dict):
            try:
                # from_facture expects (facture, seller) - extract from dict
                seller_data = invoice_data.get("entreprise", invoice_data.get("seller", {}))
                invoice_data = from_facture(invoice_data, seller_data)
            except Exception as e:
                logger.error(f"Erreur conversion données: {e}")
                errors.append(f"Données facture invalides: {e}")
                return FacturXResult(
                    pdf_content=pdf_content,
                    xml_content="",
                    invoice_number=str(invoice_data.get("numero", "UNKNOWN")) if isinstance(invoice_data, dict) else "UNKNOWN",
                    profile=self.profile,
                    is_valid=False,
                    validation_errors=errors,
                    metadata={}
                )

        # Valider les données si demandé
        should_validate = validate if validate is not None else self.validate_on_generate
        if should_validate:
            validation_errors = self._validate_data(invoice_data)
            errors.extend(validation_errors)

        # Générer le XML
        try:
            xml_content = self.xml_builder.build(invoice_data)
        except Exception as e:
            logger.error(f"Erreur génération XML: {e}")
            errors.append(f"Erreur XML: {e}")
            return FacturXResult(
                pdf_content=pdf_content,
                xml_content="",
                invoice_number=invoice_data.invoice_number,
                profile=self.profile,
                is_valid=False,
                validation_errors=errors,
                metadata={}
            )

        # Convertir en PDF/A-3 avec XML embarqué
        try:
            facturx_pdf = self.pdf_converter.convert(
                pdf_input=pdf_content,
                xml_content=xml_content,
                invoice_number=invoice_data.invoice_number,
                conformance_level=self.profile.value
            )
        except Exception as e:
            logger.error(f"Erreur conversion PDF/A-3: {e}")
            errors.append(f"Erreur PDF/A-3: {e}")
            return FacturXResult(
                pdf_content=pdf_content,
                xml_content=xml_content,
                invoice_number=invoice_data.invoice_number,
                profile=self.profile,
                is_valid=False,
                validation_errors=errors,
                metadata={}
            )

        # Valider le PDF/A généré si demandé
        if should_validate:
            is_valid_pdf, pdf_issues = self.pdf_converter.validate_pdfa(facturx_pdf)
            if not is_valid_pdf:
                errors.extend(pdf_issues)

        # Construire les métadonnées
        metadata = {
            "profile": self.profile.value,
            "invoice_number": invoice_data.invoice_number,
            "invoice_date": invoice_data.invoice_date.isoformat() if invoice_data.invoice_date else None,
            "seller": invoice_data.seller.name if invoice_data.seller else None,
            "buyer": invoice_data.buyer.name if invoice_data.buyer else None,
            "total_ttc": str(invoice_data.total_ttc),
            "currency_code": invoice_data.currency_code,
            "generated_at": datetime.utcnow().isoformat(),
            "xml_size": len(xml_content),
            "pdf_size": len(facturx_pdf)
        }

        return FacturXResult(
            pdf_content=facturx_pdf,
            xml_content=xml_content,
            invoice_number=invoice_data.invoice_number,
            profile=self.profile,
            is_valid=len(errors) == 0,
            validation_errors=errors,
            metadata=metadata
        )

    def generate_from_azalplus(
        self,
        pdf_content: bytes,
        facture: dict,
        client: dict,
        entreprise: dict
    ) -> FacturXResult:
        """
        Générer Factur-X depuis les données AZALPLUS.

        Args:
            pdf_content: PDF de la facture
            facture: Données facture AZALPLUS
            client: Données client
            entreprise: Données entreprise (vendeur)

        Returns:
            FacturXResult
        """
        # Construire le dict complet pour from_facture
        invoice_dict = {
            **facture,
            "client": client,
            "entreprise": entreprise
        }

        return self.generate(pdf_content, invoice_dict)

    def _validate_data(self, data: InvoiceData) -> list[str]:
        """Valider les données selon le profil."""
        errors = []
        required = self.REQUIRED_FIELDS.get(self.profile, [])

        # Vérifier les champs requis (using correct InvoiceData field names)
        # Get due_date from payment_terms if present
        due_date = data.payment_terms.due_date if data.payment_terms else None

        field_mapping = {
            "invoice_number": data.invoice_number,
            "invoice_date": data.invoice_date,
            "due_date": due_date,
            "seller_name": data.seller.name if data.seller else None,
            "seller_tva": data.seller.tva_intra if data.seller else None,
            "seller_siret": data.seller.siret if data.seller else None,
            "seller_address": data.seller.address if data.seller else None,
            "buyer_name": data.buyer.name if data.buyer else None,
            "buyer_siret": data.buyer.siret if data.buyer else None,
            "buyer_address": data.buyer.address if data.buyer else None,
            "lines": data.lines,
            "total_ht": data.total_ht,
            "total_tva": data.total_tva,
            "total_ttc": data.total_ttc,
            "currency_code": data.currency_code,
            "payment_terms": data.payment_terms
        }

        for field in required:
            value = field_mapping.get(field)
            if value is None or (isinstance(value, (list, str)) and len(value) == 0):
                errors.append(f"Champ requis manquant: {field}")

        # Validations spécifiques
        if data.total_ttc is not None and data.total_ht is not None:
            if data.total_tva is not None:
                expected = data.total_ht + data.total_tva
                if abs(float(data.total_ttc) - float(expected)) > 0.01:
                    errors.append(
                        f"Incohérence totaux: {data.total_ht} + {data.total_tva} "
                        f"!= {data.total_ttc}"
                    )

        # Valider les lignes si présentes
        if data.lines:
            for i, line in enumerate(data.lines):
                if not line.description:
                    errors.append(f"Ligne {i+1}: description manquante")
                if line.quantity is None or line.quantity <= 0:
                    errors.append(f"Ligne {i+1}: quantité invalide")
                if line.unit_price is None:
                    errors.append(f"Ligne {i+1}: prix unitaire manquant")

        # Valider le numéro TVA si présent
        if data.seller and data.seller.tva_intra:
            if not self._validate_vat_number(data.seller.tva_intra):
                errors.append(f"Numéro TVA vendeur invalide: {data.seller.tva_intra}")

        if data.buyer and data.buyer.tva_intra:
            if not self._validate_vat_number(data.buyer.tva_intra):
                errors.append(f"Numéro TVA acheteur invalide: {data.buyer.tva_intra}")

        return errors

    def _validate_vat_number(self, vat: str) -> bool:
        """Valider un numéro de TVA (format basique)."""
        if not vat:
            return False

        # Nettoyer
        vat = vat.replace(" ", "").upper()

        # Format français: FR + 2 caractères + 9 chiffres (SIREN)
        if vat.startswith("FR"):
            if len(vat) != 13:
                return False
            # Les 2 caractères après FR peuvent être lettres ou chiffres
            # Les 9 derniers sont le SIREN (chiffres)
            return vat[4:].isdigit()

        # Autres pays EU: 2 lettres + chiffres/lettres
        if len(vat) >= 4 and vat[:2].isalpha():
            return True

        return False

    def extract_xml(self, pdf_content: bytes) -> Optional[str]:
        """
        Extraire le XML Factur-X d'un PDF existant.

        Args:
            pdf_content: PDF Factur-X

        Returns:
            XML string ou None
        """
        return self.pdf_converter.extract_xml(pdf_content)

    def validate_pdf(self, pdf_content: bytes) -> tuple[bool, list[str]]:
        """
        Valider qu'un PDF est conforme Factur-X.

        Returns:
            (is_valid, list of issues)
        """
        issues = []

        # Valider PDF/A
        is_pdfa_valid, pdfa_issues = self.pdf_converter.validate_pdfa(pdf_content)
        issues.extend(pdfa_issues)

        # Extraire et valider XML
        xml_content = self.extract_xml(pdf_content)
        if not xml_content:
            issues.append("Aucun XML Factur-X embarqué trouvé")
        else:
            # Valider structure XML basique
            if "CrossIndustryInvoice" not in xml_content:
                issues.append("XML non conforme CII (CrossIndustryInvoice manquant)")
            if "ExchangedDocument" not in xml_content:
                issues.append("XML non conforme (ExchangedDocument manquant)")

        return len(issues) == 0, issues


# Fonction utilitaire pour génération rapide
def generate_facturx(
    pdf_content: bytes,
    invoice_data: Union[dict, InvoiceData],
    profile: FacturXProfile = FacturXProfile.EN16931
) -> FacturXResult:
    """
    Générer une facture Factur-X en une ligne.

    Args:
        pdf_content: PDF source
        invoice_data: Données facture
        profile: Profil Factur-X

    Returns:
        FacturXResult
    """
    generator = FacturXGenerator(profile=profile)
    return generator.generate(pdf_content, invoice_data)
