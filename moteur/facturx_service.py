# =============================================================================
# AZALPLUS - Service Factur-X Unifie
# =============================================================================
"""
Service unifie pour la facturation electronique Factur-X.

Connecte tous les modules existants:
- xml_builder.py - Generation XML EN16931
- pdf_a3.py - Conversion PDF/A-3
- generator.py - Orchestration
- pdp_client.py - Client PDP
- chorus_pro.py - Integration B2G
- reception.py - Reception factures entrantes
- annuaire.py - Annuaire PPF

Ce service respecte:
- Isolation multi-tenant obligatoire (AZA-TENANT)
- Logging structure avec structlog
- Stockage des URLs/IDs dans la facture

Usage:
    service = FacturXService(tenant_id)
    pdf, xml = await service.generate_facturx(invoice_data)
    result = await service.submit_to_ppf(invoice_id, pdf, xml)
"""

import structlog
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Union
from uuid import UUID

# Import des modules Factur-X existants
from integrations.facturx import (
    # Generateur
    FacturXGenerator,
    FacturXProfile,
    FacturXResult,
    # XML Builder
    XMLBuilder,
    InvoiceData,
    from_facture,
    # PDF
    PDFAConverter,
    # PDP
    PDPClient,
    PDPConfig,
    PDPProvider,
    PDPInvoice,
    PDPResponse,
    PDPStatusResponse,
    InvoiceStatus as PDPInvoiceStatus,
    InvoiceDirection,
    # Chorus
    ChorusProClient,
    ChorusConfig,
    ChorusEnvironment,
    ChorusInvoice,
    ChorusInvoiceStatus,
    ChorusResponse,
    ChorusStatusResponse,
    # Reception
    InvoiceReceptionService,
    InvoiceParser,
    ReceivedInvoice,
    InvoiceFormat,
    ReceptionStatus,
    # Annuaire
    AnnuairePPF,
    PPFConfig,
    PPFEnvironment,
    RoutingInfo,
    RoutingType,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================

class SubmissionProvider(str, Enum):
    """Providers de soumission supportes."""
    PPF = "ppf"
    CHORUS = "chorus"
    PDP = "pdp"


class SubmissionStatus(str, Enum):
    """Statuts de soumission."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    DELIVERED = "delivered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PAID = "paid"
    ERROR = "error"


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class GenerationResult:
    """Resultat de generation Factur-X."""
    success: bool
    pdf_bytes: Optional[bytes] = None
    xml_bytes: Optional[bytes] = None
    invoice_number: Optional[str] = None
    profile: FacturXProfile = FacturXProfile.EN16931
    validation_errors: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class SubmissionResult:
    """Resultat de soumission."""
    success: bool
    provider: SubmissionProvider
    provider_id: Optional[str] = None  # ID chez le provider (PPF, Chorus, PDP)
    status: SubmissionStatus = SubmissionStatus.PENDING
    message: Optional[str] = None
    errors: list[str] = field(default_factory=list)
    submitted_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)


@dataclass
class StatusResult:
    """Resultat de verification de statut."""
    success: bool
    provider: SubmissionProvider
    provider_id: str
    status: SubmissionStatus
    status_date: Optional[datetime] = None
    message: Optional[str] = None
    lifecycle_events: list[dict] = field(default_factory=list)


@dataclass
class ReceptionResult:
    """Resultat de reception de facture entrante."""
    success: bool
    invoice: Optional[ReceivedInvoice] = None
    format: InvoiceFormat = InvoiceFormat.UNKNOWN
    validation_errors: list[dict] = field(default_factory=list)
    confidence_score: float = 0.0


# =============================================================================
# Service Factur-X Unifie
# =============================================================================

class FacturXService:
    """
    Service unifie pour la facturation electronique Factur-X.

    Gere tout le pipeline:
    - Generation PDF/A-3 avec XML embarque
    - Soumission PPF / Chorus Pro / PDP
    - Reception factures entrantes
    - Verification statuts

    Respecte l'isolation multi-tenant obligatoire.

    Usage:
        service = FacturXService(tenant_id)

        # Generer Factur-X
        pdf, xml = await service.generate_facturx(invoice_data)

        # Soumettre au PPF
        result = await service.submit_to_ppf(invoice_id, pdf, xml)

        # Verifier statut
        status = await service.check_status(invoice_id, "ppf")
    """

    def __init__(
        self,
        tenant_id: UUID,
        pdp_config: Optional[PDPConfig] = None,
        chorus_config: Optional[ChorusConfig] = None,
        ppf_config: Optional[PPFConfig] = None,
        profile: FacturXProfile = FacturXProfile.EN16931
    ):
        """
        Initialiser le service.

        Args:
            tenant_id: ID du tenant (obligatoire - AZA-TENANT)
            pdp_config: Configuration PDP (optionnel)
            chorus_config: Configuration Chorus Pro (optionnel)
            ppf_config: Configuration PPF/Annuaire (optionnel)
            profile: Profil Factur-X par defaut
        """
        # Isolation multi-tenant obligatoire
        self.tenant_id = tenant_id
        self.profile = profile

        # Composants
        self.generator = FacturXGenerator(profile=profile, validate_on_generate=True)
        self.pdf_converter = PDFAConverter()
        self.xml_builder = XMLBuilder()
        self.reception_service = InvoiceReceptionService(tenant_id=tenant_id)

        # Configuration providers
        self._pdp_config = pdp_config
        self._chorus_config = chorus_config
        self._ppf_config = ppf_config

        # Clients (initialises a la demande)
        self._pdp_client: Optional[PDPClient] = None
        self._chorus_client: Optional[ChorusProClient] = None
        self._ppf_client: Optional[AnnuairePPF] = None

        logger.info(
            "facturx_service_initialized",
            tenant_id=str(tenant_id),
            profile=profile.value
        )

    # =========================================================================
    # Methode 1: generate_facturx
    # =========================================================================

    async def generate_facturx(
        self,
        invoice_data: dict,
        pdf_source: Optional[bytes] = None,
        seller_data: Optional[dict] = None,
        validate: bool = True
    ) -> tuple[bytes, bytes]:
        """
        Generer une facture Factur-X (PDF/A-3 avec XML embarque).

        Args:
            invoice_data: Donnees de la facture (dict ou InvoiceData)
            pdf_source: PDF source (optionnel, genere si absent)
            seller_data: Donnees vendeur/entreprise
            validate: Valider la facture avant generation

        Returns:
            Tuple (pdf_bytes, xml_bytes)

        Raises:
            ValueError: Si les donnees sont invalides
        """
        log = logger.bind(
            tenant_id=str(self.tenant_id),
            invoice_number=invoice_data.get("numero", "unknown")
        )

        log.info("facturx_generation_started")

        try:
            # Preparer les donnees vendeur
            if seller_data is None:
                seller_data = invoice_data.get("entreprise", invoice_data.get("seller", {}))

            # Convertir en InvoiceData si necessaire
            if isinstance(invoice_data, dict):
                invoice_obj = from_facture(invoice_data, seller_data)
            else:
                invoice_obj = invoice_data

            # Generer le XML
            xml_content = self.xml_builder.build(invoice_obj)
            xml_bytes = xml_content.encode("utf-8")

            log.debug("xml_generated", xml_size=len(xml_bytes))

            # Valider le XML si demande
            if validate:
                is_valid, errors = self.xml_builder.validate(xml_content)
                if not is_valid:
                    log.warning("xml_validation_errors", errors=errors)
                    raise ValueError(f"XML invalide: {errors}")

            # Generer ou utiliser le PDF source
            if pdf_source is None:
                # TODO: Generer le PDF depuis les donnees
                # Pour l'instant, necessaire de fournir le PDF
                raise ValueError("pdf_source est requis pour la generation")

            # Convertir en PDF/A-3 avec XML embarque
            pdf_bytes = self.pdf_converter.convert(
                pdf_input=pdf_source,
                xml_content=xml_content,
                invoice_number=invoice_obj.invoice_number,
                conformance_level=self.profile.value
            )

            log.info(
                "facturx_generation_completed",
                pdf_size=len(pdf_bytes),
                xml_size=len(xml_bytes),
                profile=self.profile.value
            )

            return pdf_bytes, xml_bytes

        except Exception as e:
            log.error("facturx_generation_failed", error=str(e))
            raise

    # =========================================================================
    # Methode 2: submit_to_ppf
    # =========================================================================

    async def submit_to_ppf(
        self,
        invoice_id: UUID,
        pdf_bytes: bytes,
        xml_bytes: bytes,
        invoice_data: Optional[dict] = None
    ) -> dict:
        """
        Soumettre une facture au PPF (via PDP configuree).

        Args:
            invoice_id: ID interne de la facture
            pdf_bytes: PDF Factur-X
            xml_bytes: XML Factur-X
            invoice_data: Donnees additionnelles de la facture

        Returns:
            Dict avec resultat de soumission:
            {
                "success": bool,
                "provider_id": str,
                "status": str,
                "message": str,
                "submitted_at": datetime,
                "urls": { ... }
            }
        """
        log = logger.bind(
            tenant_id=str(self.tenant_id),
            invoice_id=str(invoice_id)
        )

        log.info("ppf_submission_started")

        # Verifier configuration PDP
        if self._pdp_config is None:
            log.error("pdp_config_missing")
            return {
                "success": False,
                "provider": SubmissionProvider.PPF.value,
                "status": SubmissionStatus.ERROR.value,
                "message": "Configuration PDP non fournie",
                "errors": ["pdp_config_required"]
            }

        try:
            # Initialiser le client PDP si necessaire
            if self._pdp_client is None:
                self._pdp_client = PDPClient(self._pdp_config)

            # Preparer la facture PDP
            pdp_invoice = PDPInvoice(
                id=invoice_id,
                invoice_number=invoice_data.get("numero", "") if invoice_data else str(invoice_id),
                issue_date=datetime.utcnow(),
                seller_siret=invoice_data.get("seller_siret", "") if invoice_data else "",
                buyer_siret=invoice_data.get("buyer_siret", "") if invoice_data else "",
                total_without_tax=float(invoice_data.get("total_ht", 0)) if invoice_data else 0,
                total_tax=float(invoice_data.get("total_tva", 0)) if invoice_data else 0,
                total_with_tax=float(invoice_data.get("total_ttc", 0)) if invoice_data else 0,
                pdf_content=pdf_bytes,
                xml_content=xml_bytes.decode("utf-8"),
                direction=InvoiceDirection.OUTGOING,
                metadata={"tenant_id": str(self.tenant_id)}
            )

            # Soumettre
            response = await self._pdp_client.submit_invoice(pdp_invoice)

            result = {
                "success": response.success,
                "provider": SubmissionProvider.PPF.value,
                "provider_id": response.pdp_id,
                "status": self._map_pdp_status(response.status),
                "message": response.message,
                "errors": response.errors,
                "submitted_at": datetime.utcnow().isoformat(),
                "urls": {
                    "tracking": f"/api/v1/factures/{invoice_id}/status",
                    "pdf": f"/api/v1/factures/{invoice_id}/pdf",
                    "xml": f"/api/v1/factures/{invoice_id}/xml"
                }
            }

            if response.success:
                log.info(
                    "ppf_submission_completed",
                    provider_id=response.pdp_id,
                    status=response.status.value
                )
            else:
                log.warning(
                    "ppf_submission_failed",
                    errors=response.errors,
                    message=response.message
                )

            return result

        except Exception as e:
            log.error("ppf_submission_error", error=str(e))
            return {
                "success": False,
                "provider": SubmissionProvider.PPF.value,
                "status": SubmissionStatus.ERROR.value,
                "message": str(e),
                "errors": [str(e)]
            }

    # =========================================================================
    # Methode 3: submit_to_chorus
    # =========================================================================

    async def submit_to_chorus(
        self,
        invoice_id: UUID,
        pdf_bytes: bytes,
        xml_bytes: bytes,
        invoice_data: Optional[dict] = None
    ) -> dict:
        """
        Soumettre une facture a Chorus Pro (B2G - secteur public).

        Args:
            invoice_id: ID interne de la facture
            pdf_bytes: PDF Factur-X
            xml_bytes: XML Factur-X
            invoice_data: Donnees additionnelles (service_code, engagement, etc.)

        Returns:
            Dict avec resultat de soumission
        """
        log = logger.bind(
            tenant_id=str(self.tenant_id),
            invoice_id=str(invoice_id)
        )

        log.info("chorus_submission_started")

        # Verifier configuration Chorus
        if self._chorus_config is None:
            log.error("chorus_config_missing")
            return {
                "success": False,
                "provider": SubmissionProvider.CHORUS.value,
                "status": SubmissionStatus.ERROR.value,
                "message": "Configuration Chorus Pro non fournie",
                "errors": ["chorus_config_required"]
            }

        try:
            # Initialiser le client Chorus si necessaire
            if self._chorus_client is None:
                self._chorus_client = ChorusProClient(self._chorus_config)

            # Preparer la facture Chorus
            chorus_invoice = ChorusInvoice(
                invoice_number=invoice_data.get("numero", str(invoice_id)) if invoice_data else str(invoice_id),
                issue_date=datetime.utcnow(),
                supplier_siret=invoice_data.get("seller_siret", "") if invoice_data else "",
                supplier_name=invoice_data.get("seller_name", "") if invoice_data else "",
                buyer_siret=invoice_data.get("buyer_siret", "") if invoice_data else "",
                buyer_name=invoice_data.get("buyer_name", "") if invoice_data else "",
                service_code=invoice_data.get("service_code") if invoice_data else None,
                engagement_number=invoice_data.get("engagement_number") if invoice_data else None,
                total_without_tax=float(invoice_data.get("total_ht", 0)) if invoice_data else 0,
                total_tax=float(invoice_data.get("total_tva", 0)) if invoice_data else 0,
                total_with_tax=float(invoice_data.get("total_ttc", 0)) if invoice_data else 0,
                pdf_content=pdf_bytes,
                xml_content=xml_bytes.decode("utf-8")
            )

            # Soumettre avec pieces jointes
            response = await self._chorus_client.submit_with_attachment(chorus_invoice)

            result = {
                "success": response.success,
                "provider": SubmissionProvider.CHORUS.value,
                "provider_id": response.chorus_id,
                "flux_number": response.numero_flux,
                "status": self._map_chorus_status(response.status) if response.status else SubmissionStatus.PENDING.value,
                "message": response.message,
                "errors": [e.get("message", str(e)) for e in response.errors] if response.errors else [],
                "submitted_at": datetime.utcnow().isoformat(),
                "urls": {
                    "tracking": f"/api/v1/factures/{invoice_id}/status",
                    "chorus": f"https://chorus-pro.gouv.fr/facture/{response.chorus_id}" if response.chorus_id else None
                }
            }

            if response.success:
                log.info(
                    "chorus_submission_completed",
                    chorus_id=response.chorus_id,
                    flux_number=response.numero_flux
                )
            else:
                log.warning(
                    "chorus_submission_failed",
                    errors=response.errors,
                    message=response.message
                )

            return result

        except Exception as e:
            log.error("chorus_submission_error", error=str(e))
            return {
                "success": False,
                "provider": SubmissionProvider.CHORUS.value,
                "status": SubmissionStatus.ERROR.value,
                "message": str(e),
                "errors": [str(e)]
            }

    # =========================================================================
    # Methode 4: receive_invoice
    # =========================================================================

    async def receive_invoice(
        self,
        content: bytes,
        content_type: str,
        filename: Optional[str] = None,
        source: str = "upload",
        source_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Recevoir et parser une facture entrante.

        Supporte:
        - Factur-X (PDF/A-3 avec XML embarque)
        - UBL
        - CII
        - PDF simple (OCR fallback)

        Args:
            content: Contenu du fichier
            content_type: Type MIME (application/pdf, text/xml, etc.)
            filename: Nom du fichier (aide a la detection du format)
            source: Source de la facture (upload, pdp, chorus, email)
            source_id: ID chez la source
            metadata: Metadonnees additionnelles

        Returns:
            Dict avec facture parsee et validee
        """
        log = logger.bind(
            tenant_id=str(self.tenant_id),
            content_type=content_type,
            source=source
        )

        log.info("invoice_reception_started", filename=filename)

        try:
            # Recevoir et parser
            invoice = await self.reception_service.receive(
                content=content,
                filename=filename,
                source=source,
                source_id=source_id,
                metadata=metadata
            )

            result = {
                "success": invoice.status not in [ReceptionStatus.ERROR],
                "invoice_id": str(invoice.id),
                "format": invoice.format.value,
                "status": invoice.status.value,
                "confidence_score": invoice.confidence_score,
                "data": {
                    "invoice_number": invoice.invoice_number,
                    "issue_date": invoice.issue_date.isoformat() if invoice.issue_date else None,
                    "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                    "supplier_name": invoice.supplier_name,
                    "supplier_siret": invoice.supplier_siret,
                    "supplier_vat": invoice.supplier_vat,
                    "buyer_siret": invoice.buyer_siret,
                    "buyer_name": invoice.buyer_name,
                    "total_ht": str(invoice.total_without_tax) if invoice.total_without_tax else None,
                    "total_tva": str(invoice.total_tax) if invoice.total_tax else None,
                    "total_ttc": str(invoice.total_with_tax) if invoice.total_with_tax else None,
                    "currency": invoice.currency,
                    "lines_count": len(invoice.lines)
                },
                "validation_errors": invoice.validation_errors,
                "received_at": invoice.received_at.isoformat(),
                "parsed_at": invoice.parsed_at.isoformat() if invoice.parsed_at else None
            }

            log.info(
                "invoice_reception_completed",
                format=invoice.format.value,
                status=invoice.status.value,
                confidence=invoice.confidence_score
            )

            return result

        except Exception as e:
            log.error("invoice_reception_error", error=str(e))
            return {
                "success": False,
                "format": InvoiceFormat.UNKNOWN.value,
                "status": ReceptionStatus.ERROR.value,
                "message": str(e),
                "validation_errors": [{"type": "reception", "message": str(e)}]
            }

    # =========================================================================
    # Methode 5: check_status
    # =========================================================================

    async def check_status(
        self,
        invoice_id: UUID,
        provider: str,
        provider_id: Optional[str] = None
    ) -> dict:
        """
        Verifier le statut d'une facture soumise.

        Args:
            invoice_id: ID interne de la facture
            provider: Provider de soumission (ppf, chorus, pdp)
            provider_id: ID chez le provider (optionnel si connu)

        Returns:
            Dict avec statut actuel et historique
        """
        log = logger.bind(
            tenant_id=str(self.tenant_id),
            invoice_id=str(invoice_id),
            provider=provider
        )

        log.info("status_check_started")

        try:
            provider_enum = SubmissionProvider(provider.lower())

            if provider_enum == SubmissionProvider.PPF or provider_enum == SubmissionProvider.PDP:
                return await self._check_pdp_status(provider_id, log)
            elif provider_enum == SubmissionProvider.CHORUS:
                return await self._check_chorus_status(provider_id, log)
            else:
                return {
                    "success": False,
                    "provider": provider,
                    "status": SubmissionStatus.ERROR.value,
                    "message": f"Provider non supporte: {provider}"
                }

        except ValueError:
            log.error("invalid_provider", provider=provider)
            return {
                "success": False,
                "provider": provider,
                "status": SubmissionStatus.ERROR.value,
                "message": f"Provider invalide: {provider}"
            }
        except Exception as e:
            log.error("status_check_error", error=str(e))
            return {
                "success": False,
                "provider": provider,
                "status": SubmissionStatus.ERROR.value,
                "message": str(e)
            }

    async def _check_pdp_status(self, provider_id: str, log) -> dict:
        """Verifier statut PDP."""
        if self._pdp_config is None or self._pdp_client is None:
            return {
                "success": False,
                "provider": SubmissionProvider.PDP.value,
                "status": SubmissionStatus.ERROR.value,
                "message": "Configuration PDP non disponible"
            }

        if not provider_id:
            return {
                "success": False,
                "provider": SubmissionProvider.PDP.value,
                "status": SubmissionStatus.ERROR.value,
                "message": "provider_id requis pour verification statut"
            }

        response = await self._pdp_client.get_status(provider_id)

        result = {
            "success": True,
            "provider": SubmissionProvider.PDP.value,
            "provider_id": response.pdp_id,
            "status": self._map_pdp_status(response.status),
            "status_date": response.status_date.isoformat() if response.status_date else None,
            "rejection_reason": response.rejection_reason,
            "lifecycle_events": response.lifecycle_events
        }

        log.info("pdp_status_checked", status=response.status.value)
        return result

    async def _check_chorus_status(self, provider_id: str, log) -> dict:
        """Verifier statut Chorus."""
        if self._chorus_config is None or self._chorus_client is None:
            return {
                "success": False,
                "provider": SubmissionProvider.CHORUS.value,
                "status": SubmissionStatus.ERROR.value,
                "message": "Configuration Chorus Pro non disponible"
            }

        if not provider_id:
            return {
                "success": False,
                "provider": SubmissionProvider.CHORUS.value,
                "status": SubmissionStatus.ERROR.value,
                "message": "provider_id requis pour verification statut"
            }

        response = await self._chorus_client.get_status(provider_id)

        result = {
            "success": True,
            "provider": SubmissionProvider.CHORUS.value,
            "provider_id": response.chorus_id,
            "status": self._map_chorus_status(response.status),
            "status_date": response.status_date.isoformat() if response.status_date else None,
            "rejection_reason": response.rejection_reason,
            "payment_date": response.payment_date.isoformat() if response.payment_date else None,
            "payment_reference": response.payment_reference,
            "lifecycle_events": response.lifecycle
        }

        log.info("chorus_status_checked", status=response.status.value)
        return result

    # =========================================================================
    # Methodes Utilitaires
    # =========================================================================

    async def get_routing_info(self, siret: str) -> dict:
        """
        Obtenir les informations de routage pour un destinataire.

        Interroge l'annuaire PPF pour savoir comment envoyer une facture.

        Args:
            siret: SIRET du destinataire

        Returns:
            Dict avec infos de routage
        """
        log = logger.bind(tenant_id=str(self.tenant_id), siret=siret)

        if self._ppf_config is None:
            return {
                "success": False,
                "message": "Configuration PPF non disponible"
            }

        try:
            if self._ppf_client is None:
                self._ppf_client = AnnuairePPF(self._ppf_config)

            routing = await self._ppf_client.get_routing(siret)

            return {
                "success": True,
                "siret": routing.siret,
                "can_receive": routing.can_receive,
                "routing_type": routing.routing_type.value,
                "pdp_id": routing.pdp_id,
                "pdp_endpoint": routing.pdp_endpoint,
                "preferred_format": routing.preferred_format.value,
                "supported_formats": [f.value for f in routing.supported_formats]
            }

        except Exception as e:
            log.error("routing_lookup_error", error=str(e))
            return {
                "success": False,
                "siret": siret,
                "message": str(e)
            }

    async def validate_invoice(self, invoice_data: dict) -> dict:
        """
        Valider une facture avant generation.

        Args:
            invoice_data: Donnees de la facture

        Returns:
            Dict avec resultat de validation
        """
        log = logger.bind(
            tenant_id=str(self.tenant_id),
            invoice_number=invoice_data.get("numero", "unknown")
        )

        try:
            seller_data = invoice_data.get("entreprise", invoice_data.get("seller", {}))
            invoice_obj = from_facture(invoice_data, seller_data)

            # Generer XML temporaire pour validation
            xml_content = self.xml_builder.build(invoice_obj)
            is_valid, errors = self.xml_builder.validate(xml_content)

            result = {
                "valid": is_valid,
                "errors": errors,
                "profile": self.profile.value,
                "invoice_number": invoice_obj.invoice_number,
                "total_ttc": str(invoice_obj.total_ttc)
            }

            log.info("invoice_validated", valid=is_valid, errors_count=len(errors))
            return result

        except Exception as e:
            log.error("invoice_validation_error", error=str(e))
            return {
                "valid": False,
                "errors": [str(e)]
            }

    # =========================================================================
    # Mappings de Statuts
    # =========================================================================

    def _map_pdp_status(self, status: PDPInvoiceStatus) -> str:
        """Convertir statut PDP vers statut unifie."""
        mapping = {
            PDPInvoiceStatus.DRAFT: SubmissionStatus.PENDING.value,
            PDPInvoiceStatus.SUBMITTED: SubmissionStatus.SUBMITTED.value,
            PDPInvoiceStatus.PENDING: SubmissionStatus.SUBMITTED.value,
            PDPInvoiceStatus.DELIVERED: SubmissionStatus.DELIVERED.value,
            PDPInvoiceStatus.RECEIVED: SubmissionStatus.DELIVERED.value,
            PDPInvoiceStatus.ACCEPTED: SubmissionStatus.ACCEPTED.value,
            PDPInvoiceStatus.REJECTED: SubmissionStatus.REJECTED.value,
            PDPInvoiceStatus.PAID: SubmissionStatus.PAID.value,
            PDPInvoiceStatus.ERROR: SubmissionStatus.ERROR.value,
        }
        return mapping.get(status, SubmissionStatus.PENDING.value)

    def _map_chorus_status(self, status: Optional[ChorusInvoiceStatus]) -> str:
        """Convertir statut Chorus vers statut unifie."""
        if status is None:
            return SubmissionStatus.PENDING.value

        mapping = {
            ChorusInvoiceStatus.DEPOSEE: SubmissionStatus.SUBMITTED.value,
            ChorusInvoiceStatus.EN_COURS_ACHEMINEMENT: SubmissionStatus.SUBMITTED.value,
            ChorusInvoiceStatus.MISE_A_DISPOSITION: SubmissionStatus.DELIVERED.value,
            ChorusInvoiceStatus.RECUE_PAR_DESTINATAIRE: SubmissionStatus.DELIVERED.value,
            ChorusInvoiceStatus.REJETEE: SubmissionStatus.REJECTED.value,
            ChorusInvoiceStatus.MANDATEE: SubmissionStatus.ACCEPTED.value,
            ChorusInvoiceStatus.MISE_EN_PAIEMENT: SubmissionStatus.PAID.value,
            ChorusInvoiceStatus.SUSPENDUE: SubmissionStatus.PENDING.value,
            ChorusInvoiceStatus.A_RECYCLER: SubmissionStatus.ERROR.value,
        }
        return mapping.get(status, SubmissionStatus.PENDING.value)

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def close(self):
        """Fermer les clients."""
        if self._pdp_client:
            await self._pdp_client.close()
        if self._chorus_client:
            await self._chorus_client.close()
        if self._ppf_client:
            await self._ppf_client.close()

        logger.info("facturx_service_closed", tenant_id=str(self.tenant_id))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# =============================================================================
# Fonction Utilitaire de Haut Niveau
# =============================================================================

async def create_and_submit_facturx(
    tenant_id: UUID,
    invoice_data: dict,
    pdf_source: bytes,
    submit_to: str = "ppf",
    pdp_config: Optional[PDPConfig] = None,
    chorus_config: Optional[ChorusConfig] = None
) -> dict:
    """
    Creer et soumettre une facture Factur-X en une seule operation.

    Args:
        tenant_id: ID du tenant
        invoice_data: Donnees de la facture
        pdf_source: PDF source
        submit_to: Provider de soumission (ppf, chorus)
        pdp_config: Configuration PDP
        chorus_config: Configuration Chorus

    Returns:
        Dict avec resultat complet (generation + soumission)
    """
    async with FacturXService(
        tenant_id=tenant_id,
        pdp_config=pdp_config,
        chorus_config=chorus_config
    ) as service:
        # Generer
        pdf_bytes, xml_bytes = await service.generate_facturx(
            invoice_data=invoice_data,
            pdf_source=pdf_source
        )

        # Soumettre
        invoice_id = UUID(invoice_data.get("id", str(UUID(int=0))))

        if submit_to.lower() == "chorus":
            result = await service.submit_to_chorus(
                invoice_id=invoice_id,
                pdf_bytes=pdf_bytes,
                xml_bytes=xml_bytes,
                invoice_data=invoice_data
            )
        else:
            result = await service.submit_to_ppf(
                invoice_id=invoice_id,
                pdf_bytes=pdf_bytes,
                xml_bytes=xml_bytes,
                invoice_data=invoice_data
            )

        result["pdf_size"] = len(pdf_bytes)
        result["xml_size"] = len(xml_bytes)

        return result
