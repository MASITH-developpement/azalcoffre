# =============================================================================
# AZALPLUS - Email Templates Engine
# =============================================================================
"""
Moteur de templates d'emails personnalisables.
Gere le rendu des variables et l'integration avec le service d'envoi d'emails.
"""

import re
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
import structlog
import yaml
from pathlib import Path

from .db import Database
from .config import settings

logger = structlog.get_logger()


# =============================================================================
# Variables disponibles
# =============================================================================
AVAILABLE_VARIABLES = {
    "client": {
        "nom": "Nom du client",
        "email": "Email du client",
        "telephone": "Telephone du client",
        "adresse": "Adresse du client",
    },
    "document": {
        "numero": "Numero du document (devis/facture)",
        "total": "Total TTC du document",
        "total_ht": "Total HT du document",
        "date": "Date du document",
        "date_validite": "Date de validite (devis)",
        "date_echeance": "Date d'echeance (facture)",
    },
    "entreprise": {
        "nom": "Nom de l'entreprise",
        "email": "Email de l'entreprise",
        "telephone": "Telephone de l'entreprise",
        "adresse": "Adresse de l'entreprise",
        "siret": "SIRET de l'entreprise",
    },
}


# =============================================================================
# Email Template Service
# =============================================================================
class EmailTemplateService:
    """Service de gestion des templates d'emails."""

    # Types de templates disponibles
    TEMPLATE_TYPES = [
        "devis_envoye",
        "facture_envoyee",
        "rappel_paiement",
        "confirmation_paiement",
        "bienvenue_client",
        "relance_devis",
        "intervention_planifiee",
        "intervention_terminee",
        "autre",
    ]

    @classmethod
    def get_template(
        cls,
        tenant_id: UUID,
        template_type: str,
        template_id: Optional[UUID] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Recupere un template d'email.

        Args:
            tenant_id: ID du tenant
            template_type: Type de template (devis_envoye, facture_envoyee, etc.)
            template_id: ID specifique du template (optionnel)

        Returns:
            Template ou None si non trouve
        """
        if template_id:
            # Recuperer un template specifique
            template = Database.get_by_id("ModeleEmail", tenant_id, template_id)
            return template

        # Recuperer le template par defaut pour ce type
        templates = Database.query(
            "ModeleEmail",
            tenant_id,
            filters={"type": template_type, "actif": True, "par_defaut": True},
            limit=1
        )

        if templates:
            return templates[0]

        # Si pas de template par defaut, prendre le premier actif de ce type
        templates = Database.query(
            "ModeleEmail",
            tenant_id,
            filters={"type": template_type, "actif": True},
            limit=1,
            order_by="ordre ASC"
        )

        return templates[0] if templates else None

    @classmethod
    def get_templates_by_type(
        cls,
        tenant_id: UUID,
        template_type: str
    ) -> List[Dict[str, Any]]:
        """
        Recupere tous les templates d'un type.

        Args:
            tenant_id: ID du tenant
            template_type: Type de template

        Returns:
            Liste des templates
        """
        return Database.query(
            "ModeleEmail",
            tenant_id,
            filters={"type": template_type, "actif": True},
            order_by="ordre ASC"
        )

    @classmethod
    def render_template(
        cls,
        template: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Rend un template avec les variables du contexte.

        Args:
            template: Template a rendre
            context: Contexte avec les variables (client, document, entreprise)

        Returns:
            Dict avec sujet et contenu rendus
        """
        sujet = template.get("sujet", "")
        contenu = template.get("contenu", "")

        # Rendre les variables
        sujet_rendu = cls._render_variables(sujet, context)
        contenu_rendu = cls._render_variables(contenu, context)

        return {
            "sujet": sujet_rendu,
            "contenu": contenu_rendu,
        }

    @classmethod
    def _render_variables(cls, text: str, context: Dict[str, Any]) -> str:
        """
        Remplace les variables {{variable}} par leurs valeurs.

        Supporte:
        - Variables simples: {{client.nom}}
        - Conditions: {{#document.date_validite}}...{{/document.date_validite}}
        """
        if not text:
            return ""

        # Traiter les conditions d'abord
        # Pattern: {{#variable}}contenu{{/variable}}
        condition_pattern = r'\{\{#([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\}\}(.*?)\{\{/\1\}\}'

        def replace_condition(match):
            var_path = match.group(1)
            content = match.group(2)

            # Recuperer la valeur de la variable
            value = cls._get_nested_value(context, var_path)

            # Si la valeur existe et n'est pas vide/None, afficher le contenu
            if value:
                # Rendre aussi les variables dans le contenu conditionnel
                return cls._render_variables(content, context)
            return ""

        text = re.sub(condition_pattern, replace_condition, text, flags=re.DOTALL)

        # Puis traiter les variables simples
        # Pattern: {{variable.path}}
        variable_pattern = r'\{\{([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\}\}'

        def replace_variable(match):
            var_path = match.group(1)
            value = cls._get_nested_value(context, var_path)

            if value is None:
                return ""

            # Formatter les valeurs specifiques
            if isinstance(value, float):
                return f"{value:.2f}"
            if isinstance(value, datetime):
                return value.strftime("%d/%m/%Y")

            return str(value)

        text = re.sub(variable_pattern, replace_variable, text)

        return text

    @classmethod
    def _get_nested_value(cls, data: Dict[str, Any], path: str) -> Any:
        """
        Recupere une valeur imbriquee depuis un dict.
        Ex: "client.nom" depuis {"client": {"nom": "Dupont"}}
        """
        keys = path.split(".")
        value = data

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None

            if value is None:
                return None

        return value

    @classmethod
    def build_context(
        cls,
        tenant_id: UUID,
        client_data: Optional[Dict[str, Any]] = None,
        document_data: Optional[Dict[str, Any]] = None,
        tenant_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Construit le contexte de rendu avec les donnees fournies.

        Args:
            tenant_id: ID du tenant
            client_data: Donnees du client
            document_data: Donnees du document (devis/facture)
            tenant_info: Infos du tenant/entreprise

        Returns:
            Contexte pret pour le rendu
        """
        # Recuperer les infos du tenant si non fournies
        if not tenant_info:
            from .db import Database
            from sqlalchemy import text

            with Database.get_session() as session:
                result = session.execute(
                    text("SELECT * FROM azalplus.tenants WHERE id = :tenant_id"),
                    {"tenant_id": str(tenant_id)}
                )
                row = result.fetchone()
                tenant_info = dict(row._mapping) if row else {}

        context = {
            "client": {
                "nom": "",
                "email": "",
                "telephone": "",
                "adresse": "",
            },
            "document": {
                "numero": "",
                "total": 0,
                "total_ht": 0,
                "date": "",
                "date_validite": "",
                "date_echeance": "",
            },
            "entreprise": {
                "nom": tenant_info.get("nom", ""),
                "email": tenant_info.get("email", ""),
                "telephone": tenant_info.get("telephone", ""),
                "adresse": tenant_info.get("adresse", ""),
                "siret": tenant_info.get("siret", ""),
            },
        }

        # Injecter les donnees client
        if client_data:
            context["client"].update({
                "nom": client_data.get("nom") or client_data.get("raison_sociale", ""),
                "email": client_data.get("email", ""),
                "telephone": client_data.get("telephone", ""),
                "adresse": client_data.get("adresse", ""),
            })

        # Injecter les donnees document
        if document_data:
            context["document"].update({
                "numero": document_data.get("numero") or document_data.get("number", ""),
                "total": document_data.get("montant_ttc") or document_data.get("total", 0),
                "total_ht": document_data.get("montant_ht") or document_data.get("subtotal", 0),
                "date": document_data.get("date", ""),
                "date_validite": document_data.get("date_validite") or document_data.get("validite", ""),
                "date_echeance": document_data.get("date_echeance") or document_data.get("due_date", ""),
            })

        return context

    @classmethod
    def preview_template(
        cls,
        template: Dict[str, Any],
        tenant_id: UUID
    ) -> Dict[str, str]:
        """
        Genere un apercu du template avec des donnees fictives.

        Args:
            template: Template a previsualiser
            tenant_id: ID du tenant

        Returns:
            Template rendu avec donnees de demo
        """
        # Contexte de demo
        demo_context = {
            "client": {
                "nom": "Jean Dupont",
                "email": "jean.dupont@example.com",
                "telephone": "06 12 34 56 78",
                "adresse": "123 Rue de la Demo, 75001 Paris",
            },
            "document": {
                "numero": "DEV-2024-0001",
                "total": 1234.56,
                "total_ht": 1028.80,
                "date": "15/03/2024",
                "date_validite": "15/04/2024",
                "date_echeance": "15/04/2024",
            },
            "entreprise": {
                "nom": "Mon Entreprise",
                "email": "contact@monentreprise.fr",
                "telephone": "01 23 45 67 89",
                "adresse": "456 Avenue du Business, 75002 Paris",
                "siret": "123 456 789 00012",
            },
        }

        # Recuperer les vraies infos du tenant si possible
        try:
            real_context = cls.build_context(tenant_id)
            if real_context["entreprise"]["nom"]:
                demo_context["entreprise"] = real_context["entreprise"]
        except Exception:
            pass

        return cls.render_template(template, demo_context)

    @classmethod
    def get_available_variables(cls) -> Dict[str, Dict[str, str]]:
        """Retourne la liste des variables disponibles."""
        return AVAILABLE_VARIABLES

    @classmethod
    async def init_default_templates(cls, tenant_id: UUID) -> int:
        """
        Initialise les templates par defaut pour un tenant.

        Args:
            tenant_id: ID du tenant

        Returns:
            Nombre de templates crees
        """
        # Charger les templates par defaut depuis le YAML
        yaml_path = Path(__file__).parent.parent / "modules" / "modeles_email.yml"

        if not yaml_path.exists():
            logger.warning("modeles_email.yml not found")
            return 0

        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        default_templates = config.get("templates_defaut", [])
        created_count = 0

        for tpl in default_templates:
            # Verifier si un template de ce type existe deja
            existing = Database.query(
                "ModeleEmail",
                tenant_id,
                filters={"type": tpl["type"]},
                limit=1
            )

            if not existing:
                # Creer le template
                Database.insert(
                    "ModeleEmail",
                    tenant_id,
                    {
                        "nom": tpl["nom"],
                        "type": tpl["type"],
                        "sujet": tpl["sujet"],
                        "contenu": tpl["contenu"],
                        "actif": True,
                        "par_defaut": tpl.get("par_defaut", False),
                        "ordre": 0,
                    }
                )
                created_count += 1
                logger.info("default_template_created", type=tpl["type"], tenant_id=str(tenant_id))

        return created_count


# =============================================================================
# Integration avec EmailService
# =============================================================================
class TemplatedEmailService:
    """Service d'envoi d'emails utilisant les templates."""

    @classmethod
    async def send_with_template(
        cls,
        tenant_id: UUID,
        recipient: str,
        template_type: str,
        client_data: Optional[Dict[str, Any]] = None,
        document_data: Optional[Dict[str, Any]] = None,
        template_id: Optional[UUID] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Envoie un email en utilisant un template.

        Args:
            tenant_id: ID du tenant
            recipient: Email du destinataire
            template_type: Type de template
            client_data: Donnees du client
            document_data: Donnees du document
            template_id: ID du template specifique (optionnel)
            attachments: Pieces jointes
            cc: Copies
            bcc: Copies cachees

        Returns:
            Resultat de l'envoi
        """
        from .notifications import EmailService

        # Recuperer le template
        template = EmailTemplateService.get_template(
            tenant_id,
            template_type,
            template_id
        )

        if not template:
            # Fallback sur l'ancien systeme si pas de template
            logger.warning("no_template_found", type=template_type, tenant_id=str(tenant_id))
            raise ValueError(f"Aucun template trouve pour le type: {template_type}")

        # Construire le contexte
        context = EmailTemplateService.build_context(
            tenant_id,
            client_data,
            document_data
        )

        # Rendre le template
        rendered = EmailTemplateService.render_template(template, context)

        # Envoyer l'email
        await EmailService.send_email(
            to=recipient,
            subject=rendered["sujet"],
            html_body=rendered["contenu"],
            cc=cc,
            bcc=bcc,
            attachments=attachments
        )

        logger.info(
            "templated_email_sent",
            recipient=recipient,
            template_type=template_type,
            tenant_id=str(tenant_id)
        )

        return {
            "success": True,
            "recipient": recipient,
            "template_type": template_type,
            "template_id": str(template.get("id", "")),
            "sent_at": datetime.utcnow().isoformat(),
        }
