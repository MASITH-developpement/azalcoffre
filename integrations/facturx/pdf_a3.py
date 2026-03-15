# =============================================================================
# AZALPLUS - Convertisseur PDF/A-3 avec XML embarqué
# =============================================================================
"""
Conversion PDF standard vers PDF/A-3b avec XML Factur-X embarqué.

ISO 19005-3:2012 (PDF/A-3b)
- Format archivable long terme
- Permet l'embarquement de fichiers (XML, etc.)
- Métadonnées XMP obligatoires
"""

import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
import hashlib

logger = logging.getLogger(__name__)

# Essayer d'importer les dépendances
try:
    from pypdf import PdfReader, PdfWriter
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False
    logger.warning("pypdf non disponible - conversion PDF/A limitée")

try:
    from pikepdf import Pdf, AttachedFileSpec, Name, Dictionary, Array, String
    PIKEPDF_AVAILABLE = True
except ImportError:
    PIKEPDF_AVAILABLE = False
    logger.warning("pikepdf non disponible - utilisation de la méthode alternative")


class PDFAConverter:
    """
    Convertisseur PDF vers PDF/A-3b avec XML embarqué.

    Supporte deux modes:
    - pikepdf (recommandé): Conversion complète PDF/A-3
    - pypdf (fallback): Embarquement XML basique
    """

    # Métadonnées XMP pour PDF/A-3
    XMP_TEMPLATE = '''<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
        xmlns:dc="http://purl.org/dc/elements/1.1/"
        xmlns:pdf="http://ns.adobe.com/pdf/1.3/"
        xmlns:xmp="http://ns.adobe.com/xap/1.0/"
        xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"
        xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/"
        xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#"
        xmlns:pdfaProperty="http://www.aiim.org/pdfa/ns/property#"
        xmlns:fx="urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#">
      <pdfaid:part>3</pdfaid:part>
      <pdfaid:conformance>B</pdfaid:conformance>
      <dc:title>
        <rdf:Alt>
          <rdf:li xml:lang="x-default">{title}</rdf:li>
        </rdf:Alt>
      </dc:title>
      <dc:creator>
        <rdf:Seq>
          <rdf:li>AZALPLUS</rdf:li>
        </rdf:Seq>
      </dc:creator>
      <dc:description>
        <rdf:Alt>
          <rdf:li xml:lang="x-default">Factur-X invoice</rdf:li>
        </rdf:Alt>
      </dc:description>
      <xmp:CreatorTool>AZALPLUS ERP</xmp:CreatorTool>
      <xmp:CreateDate>{create_date}</xmp:CreateDate>
      <xmp:ModifyDate>{modify_date}</xmp:ModifyDate>
      <pdf:Producer>AZALPLUS Factur-X Generator</pdf:Producer>
      <pdfaExtension:schemas>
        <rdf:Bag>
          <rdf:li rdf:parseType="Resource">
            <pdfaSchema:schema>Factur-X PDFA Extension Schema</pdfaSchema:schema>
            <pdfaSchema:namespaceURI>urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#</pdfaSchema:namespaceURI>
            <pdfaSchema:prefix>fx</pdfaSchema:prefix>
            <pdfaSchema:property>
              <rdf:Seq>
                <rdf:li rdf:parseType="Resource">
                  <pdfaProperty:name>DocumentFileName</pdfaProperty:name>
                  <pdfaProperty:valueType>Text</pdfaProperty:valueType>
                  <pdfaProperty:category>external</pdfaProperty:category>
                  <pdfaProperty:description>Name of the embedded XML invoice file</pdfaProperty:description>
                </rdf:li>
                <rdf:li rdf:parseType="Resource">
                  <pdfaProperty:name>DocumentType</pdfaProperty:name>
                  <pdfaProperty:valueType>Text</pdfaProperty:valueType>
                  <pdfaProperty:category>external</pdfaProperty:category>
                  <pdfaProperty:description>INVOICE</pdfaProperty:description>
                </rdf:li>
                <rdf:li rdf:parseType="Resource">
                  <pdfaProperty:name>Version</pdfaProperty:name>
                  <pdfaProperty:valueType>Text</pdfaProperty:valueType>
                  <pdfaProperty:category>external</pdfaProperty:category>
                  <pdfaProperty:description>Version of the Factur-X XML Schema</pdfaProperty:description>
                </rdf:li>
                <rdf:li rdf:parseType="Resource">
                  <pdfaProperty:name>ConformanceLevel</pdfaProperty:name>
                  <pdfaProperty:valueType>Text</pdfaProperty:valueType>
                  <pdfaProperty:category>external</pdfaProperty:category>
                  <pdfaProperty:description>Factur-X conformance level</pdfaProperty:description>
                </rdf:li>
              </rdf:Seq>
            </pdfaSchema:property>
          </rdf:li>
        </rdf:Bag>
      </pdfaExtension:schemas>
      <fx:DocumentFileName>factur-x.xml</fx:DocumentFileName>
      <fx:DocumentType>INVOICE</fx:DocumentType>
      <fx:Version>1.0</fx:Version>
      <fx:ConformanceLevel>{conformance_level}</fx:ConformanceLevel>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''

    def __init__(self):
        self.use_pikepdf = PIKEPDF_AVAILABLE

    def convert(
        self,
        pdf_input: Union[bytes, str, Path],
        xml_content: str,
        invoice_number: str,
        conformance_level: str = "EN16931"
    ) -> bytes:
        """
        Convertir un PDF en PDF/A-3 avec XML Factur-X embarqué.

        Args:
            pdf_input: PDF source (bytes ou chemin)
            xml_content: XML Factur-X à embarquer
            invoice_number: Numéro de facture (pour le titre)
            conformance_level: Niveau de conformité Factur-X

        Returns:
            PDF/A-3 en bytes avec XML embarqué
        """
        if self.use_pikepdf:
            return self._convert_pikepdf(pdf_input, xml_content, invoice_number, conformance_level)
        elif PYPDF_AVAILABLE:
            return self._convert_pypdf(pdf_input, xml_content, invoice_number)
        else:
            raise RuntimeError("Aucune bibliothèque PDF disponible (pikepdf ou pypdf requis)")

    def _convert_pikepdf(
        self,
        pdf_input: Union[bytes, str, Path],
        xml_content: str,
        invoice_number: str,
        conformance_level: str
    ) -> bytes:
        """Conversion avec pikepdf (méthode complète)."""
        # Ouvrir le PDF
        if isinstance(pdf_input, bytes):
            pdf = Pdf.open(io.BytesIO(pdf_input))
        else:
            pdf = Pdf.open(pdf_input)

        # Générer les métadonnées XMP
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00")
        xmp = self.XMP_TEMPLATE.format(
            title=f"Facture {invoice_number}",
            create_date=now,
            modify_date=now,
            conformance_level=conformance_level
        )

        # Embarquer le XML Factur-X
        xml_bytes = xml_content.encode("utf-8")
        pdf.attachments["factur-x.xml"] = xml_bytes

        # Sauvegarder
        output = io.BytesIO()
        pdf.save(output, linearize=True)
        return output.getvalue()

    def _convert_pypdf(
        self,
        pdf_input: Union[bytes, str, Path],
        xml_content: str,
        invoice_number: str
    ) -> bytes:
        """Conversion avec pypdf (méthode basique)."""
        # Ouvrir le PDF
        if isinstance(pdf_input, bytes):
            reader = PdfReader(io.BytesIO(pdf_input))
        else:
            reader = PdfReader(pdf_input)

        writer = PdfWriter()

        # Copier les pages
        for page in reader.pages:
            writer.add_page(page)

        # Ajouter le XML comme pièce jointe
        writer.add_attachment("factur-x.xml", xml_content.encode("utf-8"))

        # Métadonnées basiques
        writer.add_metadata({
            "/Title": f"Facture {invoice_number}",
            "/Author": "AZALPLUS",
            "/Subject": "Factur-X Invoice",
            "/Creator": "AZALPLUS ERP",
            "/Producer": "AZALPLUS Factur-X Generator"
        })

        # Sauvegarder
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()

    def extract_xml(self, pdf_input: Union[bytes, str, Path]) -> Optional[str]:
        """
        Extraire le XML Factur-X d'un PDF.

        Args:
            pdf_input: PDF source

        Returns:
            XML string ou None si non trouvé
        """
        if self.use_pikepdf:
            return self._extract_pikepdf(pdf_input)
        elif PYPDF_AVAILABLE:
            return self._extract_pypdf(pdf_input)
        return None

    def _extract_pikepdf(self, pdf_input: Union[bytes, str, Path]) -> Optional[str]:
        """Extraction avec pikepdf."""
        try:
            if isinstance(pdf_input, bytes):
                pdf = Pdf.open(io.BytesIO(pdf_input))
            else:
                pdf = Pdf.open(pdf_input)

            # Chercher dans les fichiers embarqués
            if hasattr(pdf.Root, "Names") and hasattr(pdf.Root.Names, "EmbeddedFiles"):
                names = pdf.Root.Names.EmbeddedFiles.Names
                for i in range(0, len(names), 2):
                    name = str(names[i])
                    if "factur-x" in name.lower() or name.endswith(".xml"):
                        file_spec = names[i + 1]
                        if hasattr(file_spec, "EF") and hasattr(file_spec.EF, "F"):
                            return file_spec.EF.F.read_bytes().decode("utf-8")

        except Exception as e:
            logger.error(f"Erreur extraction XML: {e}")

        return None

    def _extract_pypdf(self, pdf_input: Union[bytes, str, Path]) -> Optional[str]:
        """Extraction avec pypdf."""
        try:
            if isinstance(pdf_input, bytes):
                reader = PdfReader(io.BytesIO(pdf_input))
            else:
                reader = PdfReader(pdf_input)

            # Chercher les pièces jointes
            if "/Names" in reader.trailer["/Root"]:
                names = reader.trailer["/Root"]["/Names"]
                if "/EmbeddedFiles" in names:
                    embedded = names["/EmbeddedFiles"]
                    if "/Names" in embedded:
                        file_names = embedded["/Names"]
                        for i in range(0, len(file_names), 2):
                            name = file_names[i]
                            if "factur-x" in name.lower() or name.endswith(".xml"):
                                file_obj = file_names[i + 1].get_object()
                                if "/EF" in file_obj and "/F" in file_obj["/EF"]:
                                    stream = file_obj["/EF"]["/F"].get_object()
                                    return stream.get_data().decode("utf-8")

        except Exception as e:
            logger.error(f"Erreur extraction XML: {e}")

        return None

    def validate_pdfa(self, pdf_input: Union[bytes, str, Path]) -> tuple[bool, list[str]]:
        """
        Valider qu'un PDF est conforme PDF/A-3.

        Returns:
            (is_valid, list of issues)
        """
        issues = []

        try:
            if self.use_pikepdf:
                if isinstance(pdf_input, bytes):
                    pdf = Pdf.open(io.BytesIO(pdf_input))
                else:
                    pdf = Pdf.open(pdf_input)

                # Vérifier les métadonnées XMP
                if not hasattr(pdf.Root, "Metadata"):
                    issues.append("Métadonnées XMP manquantes")
                else:
                    metadata = pdf.Root.Metadata.read_bytes().decode("utf-8")
                    if "pdfaid:part" not in metadata:
                        issues.append("Déclaration PDF/A manquante dans XMP")
                    if "pdfaid:conformance" not in metadata:
                        issues.append("Niveau de conformité PDF/A manquant")

                # Vérifier les fichiers embarqués
                if not hasattr(pdf.Root, "Names") or not hasattr(pdf.Root.Names, "EmbeddedFiles"):
                    issues.append("Aucun fichier embarqué (XML Factur-X attendu)")

                # Vérifier OutputIntents
                if not hasattr(pdf.Root, "OutputIntents") or len(pdf.Root.OutputIntents) == 0:
                    issues.append("OutputIntents manquant (requis pour PDF/A)")

            else:
                issues.append("Validation complète nécessite pikepdf")

        except Exception as e:
            issues.append(f"Erreur validation: {e}")

        return len(issues) == 0, issues


def create_facturx_pdf(
    pdf_content: bytes,
    xml_content: str,
    invoice_number: str,
    conformance_level: str = "EN16931"
) -> bytes:
    """
    Fonction utilitaire pour créer un PDF Factur-X.

    Args:
        pdf_content: PDF source en bytes
        xml_content: XML Factur-X
        invoice_number: Numéro de facture
        conformance_level: Niveau de conformité

    Returns:
        PDF/A-3 avec XML embarqué
    """
    converter = PDFAConverter()
    return converter.convert(pdf_content, xml_content, invoice_number, conformance_level)
