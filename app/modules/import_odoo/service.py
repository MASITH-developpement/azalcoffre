# =============================================================================
# AZALPLUS - Service Import/Export Odoo
# =============================================================================
"""
Service complet pour synchronisation Odoo:
- Import CSV/Excel
- Import API XML-RPC
- Export vers format Odoo
- Mapping automatique des champs
"""

import csv
import io
import re
import xmlrpc.client
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
import structlog

logger = structlog.get_logger()


# =============================================================================
# MAPPING ODOO -> AZALPLUS
# =============================================================================

# Mapping des modèles Odoo vers les modules AZALPLUS
ODOO_MODEL_MAPPING = {
    "res.partner": {
        "module": "clients",  # ou fournisseurs selon is_company/supplier_rank
        "fields": {
            "id": "__odoo_id__",
            "name": "nom",
            "display_name": "nom",
            "street": "adresse",
            "street2": "adresse_complement",
            "zip": "code_postal",
            "city": "ville",
            "country_id": "pays",
            "phone": "telephone",
            "mobile": "mobile",
            "email": "email",
            "website": "site_web",
            "vat": "numero_tva",
            "ref": "code",
            "comment": "notes",
            "is_company": "__is_company__",
            "parent_id": "societe_parente_id",
            "function": "fonction",
            "title": "civilite",
            "lang": "langue",
            "customer_rank": "__customer_rank__",
            "supplier_rank": "__supplier_rank__",
            "credit_limit": "plafond_credit",
            "property_payment_term_id": "conditions_paiement",
            "siret": "siret",
            "siren": "siren",
            "ape": "code_ape",
        }
    },
    "product.product": {
        "module": "produits",
        "fields": {
            "id": "__odoo_id__",
            "name": "nom",
            "display_name": "nom",
            "default_code": "reference",
            "barcode": "code_barre",
            "type": "type_produit",
            "categ_id": "categorie",
            "list_price": "prix_vente",
            "standard_price": "prix_achat",
            "qty_available": "quantite_stock",
            "virtual_available": "quantite_virtuelle",
            "uom_id": "unite",
            "description": "description",
            "description_sale": "description_vente",
            "description_purchase": "description_achat",
            "weight": "poids",
            "volume": "volume",
            "active": "actif",
            "sale_ok": "vendable",
            "purchase_ok": "achetable",
        }
    },
    "product.template": {
        "module": "produits",
        "fields": {
            "id": "__odoo_id__",
            "name": "nom",
            "default_code": "reference",
            "barcode": "code_barre",
            "type": "type_produit",
            "categ_id": "categorie",
            "list_price": "prix_vente",
            "standard_price": "prix_achat",
            "uom_id": "unite",
            "description": "description",
            "weight": "poids",
            "volume": "volume",
            "active": "actif",
        }
    },
    "sale.order": {
        "module": "commandes",
        "fields": {
            "id": "__odoo_id__",
            "name": "numero",
            "partner_id": "client_id",
            "partner_invoice_id": "adresse_facturation_id",
            "partner_shipping_id": "adresse_livraison_id",
            "date_order": "date_commande",
            "validity_date": "date_validite",
            "commitment_date": "date_livraison_prevue",
            "amount_untaxed": "montant_ht",
            "amount_tax": "montant_tva",
            "amount_total": "montant_ttc",
            "state": "statut",
            "note": "notes",
            "payment_term_id": "conditions_paiement",
            "user_id": "commercial_id",
            "origin": "origine",
            "client_order_ref": "reference_client",
        }
    },
    "sale.order.line": {
        "module": "lignes_commande",
        "fields": {
            "id": "__odoo_id__",
            "order_id": "commande_id",
            "product_id": "produit_id",
            "name": "description",
            "product_uom_qty": "quantite",
            "price_unit": "prix_unitaire",
            "discount": "remise",
            "price_subtotal": "montant_ht",
            "tax_id": "taxes",
        }
    },
    "purchase.order": {
        "module": "commandes_achat",
        "fields": {
            "id": "__odoo_id__",
            "name": "numero",
            "partner_id": "fournisseur_id",
            "date_order": "date_commande",
            "date_planned": "date_livraison_prevue",
            "amount_untaxed": "montant_ht",
            "amount_tax": "montant_tva",
            "amount_total": "montant_ttc",
            "state": "statut",
            "notes": "notes",
            "payment_term_id": "conditions_paiement",
            "user_id": "acheteur_id",
            "origin": "origine",
            "partner_ref": "reference_fournisseur",
        }
    },
    "account.move": {
        "module": "factures",
        "fields": {
            "id": "__odoo_id__",
            "name": "numero",
            "move_type": "type_document",
            "partner_id": "client_id",
            "invoice_date": "date_facture",
            "invoice_date_due": "date_echeance",
            "amount_untaxed": "montant_ht",
            "amount_tax": "montant_tva",
            "amount_total": "montant_ttc",
            "amount_residual": "reste_a_payer",
            "state": "statut",
            "payment_state": "statut_paiement",
            "narration": "notes",
            "ref": "reference",
            "invoice_origin": "origine",
            "invoice_payment_term_id": "conditions_paiement",
        }
    },
    "stock.picking": {
        "module": "expeditions",
        "fields": {
            "id": "__odoo_id__",
            "name": "numero",
            "partner_id": "partenaire_id",
            "scheduled_date": "date_prevue",
            "date_done": "date_realisee",
            "origin": "origine",
            "state": "statut",
            "picking_type_id": "type_operation",
            "location_id": "emplacement_source",
            "location_dest_id": "emplacement_destination",
        }
    },
    "hr.employee": {
        "module": "employes",
        "fields": {
            "id": "__odoo_id__",
            "name": "nom_complet",
            "work_email": "email",
            "work_phone": "telephone",
            "mobile_phone": "mobile",
            "job_id": "poste",
            "department_id": "departement",
            "parent_id": "responsable_id",
            "coach_id": "coach_id",
            "address_home_id": "adresse_personnelle",
            "identification_id": "numero_identite",
            "passport_id": "numero_passeport",
            "bank_account_id": "compte_bancaire",
            "birthday": "date_naissance",
            "country_id": "nationalite",
            "gender": "genre",
            "marital": "situation_familiale",
        }
    },
    "project.project": {
        "module": "projets",
        "fields": {
            "id": "__odoo_id__",
            "name": "nom",
            "partner_id": "client_id",
            "user_id": "responsable_id",
            "date_start": "date_debut",
            "date": "date_fin",
            "description": "description",
            "active": "actif",
        }
    },
    "project.task": {
        "module": "taches",
        "fields": {
            "id": "__odoo_id__",
            "name": "nom",
            "project_id": "projet_id",
            "user_ids": "assignes",
            "date_deadline": "date_echeance",
            "planned_hours": "heures_prevues",
            "description": "description",
            "priority": "priorite",
            "stage_id": "etape",
        }
    },
    "crm.lead": {
        "module": "leads",
        "fields": {
            "id": "__odoo_id__",
            "name": "nom",
            "partner_id": "client_id",
            "user_id": "commercial_id",
            "email_from": "email",
            "phone": "telephone",
            "mobile": "mobile",
            "expected_revenue": "montant_prevu",
            "probability": "probabilite",
            "date_deadline": "date_cloture_prevue",
            "description": "description",
            "stage_id": "etape",
            "type": "type",
        }
    },
    # =========================================================================
    # INTERVENTIONS / SAV / MAINTENANCE
    # =========================================================================
    "maintenance.request": {
        "module": "interventions",
        "fields": {
            "id": "__odoo_id__",
            "name": "objet",
            "description": "description",
            "request_date": "date_demande",
            "schedule_date": "date_prevue",
            "close_date": "date_fin",
            "duration": "duree_reelle",
            "maintenance_type": "type_intervention",
            "priority": "priorite",
            "stage_id": "statut",
            "equipment_id": "equipement_id",
            "user_id": "technicien_id",
            "owner_user_id": "responsable_id",
            "technician_user_id": "technicien_id",
            "company_id": "client_id",
            "kanban_state": "__kanban_state__",
            "archive": "__archive__",
        }
    },
    "helpdesk.ticket": {
        "module": "interventions",
        "fields": {
            "id": "__odoo_id__",
            "name": "objet",
            "description": "description",
            "ticket_ref": "numero",
            "partner_id": "client_id",
            "partner_name": "contact_nom",
            "partner_email": "contact_email",
            "partner_phone": "contact_telephone",
            "user_id": "technicien_id",
            "team_id": "equipe",
            "stage_id": "statut",
            "priority": "priorite",
            "create_date": "date_demande",
            "assign_date": "date_prevue",
            "close_date": "date_fin",
            "sla_deadline": "sla_delai",
            "sla_reached": "sla_respecte",
            "resolution": "travaux_realises",
            "ticket_type_id": "type_intervention",
        }
    },
    "field.service": {
        "module": "interventions",
        "fields": {
            "id": "__odoo_id__",
            "name": "objet",
            "description": "description",
            "partner_id": "client_id",
            "partner_address_id": "adresse_intervention",
            "partner_phone": "contact_telephone",
            "user_id": "technicien_id",
            "stage_id": "statut",
            "priority": "priorite",
            "planned_date_begin": "date_prevue",
            "planned_date_end": "date_fin",
            "date_start": "date_debut",
            "date_end": "date_fin",
            "duration": "duree_reelle",
            "travel_duration": "temps_trajet",
            "equipment_id": "equipement_id",
            "sale_order_id": "commande_id",
            "invoice_id": "facture_id",
        }
    },
    "repair.order": {
        "module": "interventions",
        "fields": {
            "id": "__odoo_id__",
            "name": "numero",
            "description": "description",
            "partner_id": "client_id",
            "address_id": "adresse_intervention",
            "product_id": "equipement_id",
            "lot_id": "equipement_numero_serie",
            "user_id": "technicien_id",
            "state": "statut",
            "priority": "priorite",
            "schedule_date": "date_prevue",
            "guarantee_limit": "garantie_fin",
            "under_guarantee": "sous_garantie",
            "quotation_notes": "diagnostic",
            "internal_notes": "notes",
            "amount_untaxed": "montant_ht",
            "amount_tax": "tva",
            "amount_total": "montant_ttc",
        }
    },
    # Module personnalisé MASITH
    # NOTE: Ne lister ici QUE les champs qui existent dans Odoo
    # Les champs contact_nom/telephone/ville sont remplis via la résolution client
    "intervention.intervention": {
        "module": "interventions",
        "fields": {
            "id": "__odoo_id__",
            "numero": "numero",
            "numero_donneur_ordre": "numero_os",
            "adresse_intervention": "adresse_intervention",
            # Dates
            "create_date": "date_demande",
            "date_prevue": "date_prevue",
            "date_debut": "date_debut",
            "date_fin": "date_fin",
            "description": "description",
            "statut": "statut",
            "type_intervention": "type_intervention",
            # Relations Odoo -> résolution automatique (+ remplissage contact)
            "technicien_principal_id": "@resolve:technicien_id",
            "donneur_ordre_id": "@resolve:donneur_ordre_id",
            "client_final_id": "@resolve:client_id",
            # Durées et distances
            "duree_prevue": "duree_prevue",
            "duree_reelle": "duree_reelle",
            "observations": "notes",
            "travaux_realises": "travaux_realises",
            "facturer_a": "__facturer_a__",
            "distance_km": "km_parcourus",
            "duree_trajet_min": "temps_trajet",
            "satisfaction_client": "satisfaction_score",
            "rapport_intervention": "rapport_intervention",
        }
    },
}

# Mapping des statuts Odoo -> AZALPLUS
ODOO_STATUS_MAPPING = {
    # sale.order
    "draft": "BROUILLON",
    "sent": "ENVOYE",
    "sale": "CONFIRME",
    "done": "TERMINE",
    "cancel": "ANNULE",
    # purchase.order
    "purchase": "CONFIRME",
    "to approve": "A_APPROUVER",
    # account.move
    "posted": "VALIDE",
    # stock.picking
    "waiting": "EN_ATTENTE",
    "confirmed": "CONFIRME",
    "assigned": "PRET",
    # maintenance.request / interventions
    "new": "DEMANDE",
    "in_progress": "EN_COURS",
    "repaired": "TERMINEE",
    "scrap": "ANNULEE",
    # helpdesk.ticket
    "open": "EN_COURS",
    "pending": "EN_ATTENTE",
    "solved": "TERMINEE",
    "closed": "TERMINEE",
    # repair.order
    "quotation": "BROUILLON",
    "confirmed": "PLANIFIEE",
    "under_repair": "EN_COURS",
    "ready": "TERMINEE",
    "2binvoiced": "A_FACTURER",
    "invoice_except": "ERREUR",
}


# =============================================================================
# CLIENT API ODOO (XML-RPC)
# =============================================================================

class OdooAPIClient:
    """Client API XML-RPC pour Odoo."""

    def __init__(
        self,
        url: str,
        db: str,
        username: str,
        password: str
    ):
        # Auto-ajouter https:// si manquant
        if url and not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        self.url = url.rstrip('/')
        self.db = db
        self.username = username
        self.password = password
        self.uid = None
        self.common = None
        self.models = None

    def connect(self) -> bool:
        """Établit la connexion à Odoo."""
        try:
            # Point d'entrée commun pour l'authentification
            self.common = xmlrpc.client.ServerProxy(
                f'{self.url}/xmlrpc/2/common',
                allow_none=True
            )

            # Authentification
            self.uid = self.common.authenticate(
                self.db,
                self.username,
                self.password,
                {}
            )

            if not self.uid:
                logger.error("odoo_auth_failed", url=self.url, db=self.db)
                return False

            # Point d'entrée pour les modèles
            self.models = xmlrpc.client.ServerProxy(
                f'{self.url}/xmlrpc/2/object',
                allow_none=True
            )

            logger.info("odoo_connected", url=self.url, db=self.db, uid=self.uid)
            return True

        except Exception as e:
            logger.error("odoo_connection_error", url=self.url, error=str(e))
            return False

    def get_version(self) -> Optional[Dict]:
        """Récupère la version d'Odoo."""
        try:
            return self.common.version()
        except Exception as e:
            logger.error("odoo_version_error", error=str(e))
            return None

    def search(
        self,
        model: str,
        domain: List = None,
        offset: int = 0,
        limit: int = None,
        order: str = None
    ) -> List[int]:
        """Recherche des enregistrements."""
        domain = domain or []
        kwargs = {"offset": offset}
        if limit:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order

        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, 'search',
            [domain],
            kwargs
        )

    def search_count(self, model: str, domain: List = None) -> int:
        """Compte les enregistrements."""
        domain = domain or []
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, 'search_count',
            [domain]
        )

    def read(
        self,
        model: str,
        ids: List[int],
        fields: List[str] = None
    ) -> List[Dict]:
        """Lit les enregistrements."""
        kwargs = {}
        if fields:
            kwargs["fields"] = fields

        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, 'read',
            [ids],
            kwargs
        )

    def search_read(
        self,
        model: str,
        domain: List = None,
        fields: List[str] = None,
        offset: int = 0,
        limit: int = None,
        order: str = None
    ) -> List[Dict]:
        """Recherche et lit les enregistrements."""
        domain = domain or []
        kwargs = {"offset": offset}
        if fields:
            kwargs["fields"] = fields
        if limit:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order

        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, 'search_read',
            [domain],
            kwargs
        )

    def create(self, model: str, values: Dict) -> int:
        """Crée un enregistrement."""
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, 'create',
            [values]
        )

    def write(self, model: str, ids: List[int], values: Dict) -> bool:
        """Met à jour des enregistrements."""
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, 'write',
            [ids, values]
        )

    def unlink(self, model: str, ids: List[int]) -> bool:
        """Supprime des enregistrements."""
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, 'unlink',
            [ids]
        )

    def get_fields(self, model: str) -> Dict:
        """Récupère la définition des champs d'un modèle."""
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, 'fields_get',
            [],
            {'attributes': ['string', 'type', 'relation', 'required', 'selection']}
        )


# =============================================================================
# SERVICE IMPORT ODOO
# =============================================================================

class OdooImportService:
    """Service d'import depuis Odoo."""

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id
        self.errors: List[Dict] = []
        self.imported_ids: List[str] = []
        self.stats = {
            "total": 0,
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0
        }
        # Cache des entités créées/trouvées (nom -> UUID)
        self._client_cache: Dict[str, str] = {}
        self._donneur_ordre_cache: Dict[str, str] = {}
        self._technicien_cache: Dict[str, str] = {}
        # Client Odoo pour résolution des relations
        self._odoo_client: Optional['OdooAPIClient'] = None

    def _get_or_create_client(
        self,
        nom: str,
        extra_data: Dict = None
    ) -> Optional[str]:
        """
        Cherche un client par nom, le crée ou le met à jour s'il existe.
        Retourne l'UUID du client.
        Utilise la table clients (clients.yml).

        Args:
            nom: Nom du client
            extra_data: Données supplémentaires (email, tel, adresse, etc.)
        """
        if not nom or nom.strip() == '':
            return None

        nom = nom.strip()

        # Vérifier le cache
        if nom in self._client_cache:
            return self._client_cache[nom]

        from moteur.db import Database
        extra_data = extra_data or {}

        # Chercher dans la base de données par name (champ correct du schema clients.yml)
        try:
            existing = Database.query(
                "clients",
                self.tenant_id,
                filters={"name": nom},
                limit=1
            )

            if existing and len(existing) > 0:
                client_id = str(existing[0].get('id'))
                self._client_cache[nom] = client_id

                # Mettre à jour avec les nouvelles données si fournies
                if extra_data:
                    update_data = {k: v for k, v in extra_data.items() if v}
                    if update_data:
                        Database.update("clients", self.tenant_id, client_id, update_data)
                        logger.debug("client_updated", name=nom, client_id=client_id)

                return client_id

            # Créer le client avec toutes les données (champs selon clients.yml)
            new_client = {
                "name": nom,
                "type": "ENTREPRISE",  # Type selon clients.yml: ENTREPRISE ou PARTICULIER
                "is_active": True,
            }
            # Ajouter les données supplémentaires
            if extra_data:
                for key, value in extra_data.items():
                    if value:
                        new_client[key] = value

            result = Database.insert("clients", self.tenant_id, new_client)
            if result:
                client_id = str(result.get('id'))
                self._client_cache[nom] = client_id
                logger.info("client_created", name=nom, client_id=client_id)
                return client_id

        except Exception as e:
            logger.warning("client_lookup_error", name=nom, error=str(e))

        return None

    def _get_or_create_donneur_ordre(
        self,
        nom: str,
        extra_data: Dict = None
    ) -> Optional[str]:
        """
        Cherche un donneur d'ordre par nom, le crée ou le met à jour s'il existe.
        Retourne l'UUID du donneur d'ordre.
        Utilise la table donneur_ordre (donneur_ordre.yml).
        """
        if not nom or nom.strip() == '':
            return None

        nom = nom.strip()

        # Vérifier le cache
        if nom in self._donneur_ordre_cache:
            return self._donneur_ordre_cache[nom]

        from moteur.db import Database
        extra_data = extra_data or {}

        # Chercher dans la base de données par nom (champ correct du schema donneur_ordre.yml)
        try:
            existing = Database.query(
                "donneur_ordre",
                self.tenant_id,
                filters={"nom": nom},
                limit=1
            )

            if existing and len(existing) > 0:
                do_id = str(existing[0].get('id'))
                self._donneur_ordre_cache[nom] = do_id

                # Mettre à jour avec les nouvelles données si fournies
                if extra_data:
                    update_data = {k: v for k, v in extra_data.items() if v}
                    if update_data:
                        Database.update("donneur_ordre", self.tenant_id, do_id, update_data)
                        logger.debug("donneur_ordre_updated", nom=nom, do_id=do_id)

                return do_id

            # Créer le donneur d'ordre avec toutes les données (champs selon donneur_ordre.yml)
            new_do = {
                "nom": nom,
                "type": "CLIENT",  # Type selon donneur_ordre.yml
                "statut": "ACTIF",
            }
            # Ajouter les données supplémentaires
            if extra_data:
                for key, value in extra_data.items():
                    if value:
                        new_do[key] = value

            result = Database.insert("donneur_ordre", self.tenant_id, new_do)
            if result:
                do_id = str(result.get('id'))
                self._donneur_ordre_cache[nom] = do_id
                logger.info("donneur_ordre_created", nom=nom, do_id=do_id)
                return do_id

        except Exception as e:
            logger.warning("donneur_ordre_lookup_error", nom=nom, error=str(e))

        return None

    def _fetch_partner_from_odoo(self, client: 'OdooAPIClient', partner_id: int) -> Optional[Dict]:
        """
        Récupère les informations complètes d'un partenaire depuis Odoo.
        """
        if not partner_id:
            return None

        try:
            partners = client.search_read(
                'res.partner',
                domain=[('id', '=', partner_id)],
                fields=['name', 'email', 'phone', 'mobile', 'street', 'street2',
                        'city', 'zip', 'country_id', 'vat', 'ref', 'website',
                        'is_company', 'function', 'comment'],
                limit=1
            )
            if partners:
                return partners[0]
        except Exception as e:
            logger.debug("fetch_partner_error", partner_id=partner_id, error=str(e))

        return None

    def _create_client_from_odoo_partner(
        self,
        odoo_client: 'OdooAPIClient',
        partner_ref: Any,
        is_donneur_ordre: bool = False
    ) -> Optional[str]:
        """
        Crée ou met à jour un client ou donneur d'ordre depuis un partenaire Odoo.
        partner_ref peut être: [id, "nom"], id, ou "nom"
        """
        if not partner_ref or partner_ref is False:
            return None

        partner_id = None
        partner_name = None

        # Extraire ID et nom selon le format
        if isinstance(partner_ref, (list, tuple)) and len(partner_ref) >= 2:
            partner_id = partner_ref[0]
            partner_name = partner_ref[1]
        elif isinstance(partner_ref, int):
            partner_id = partner_ref
        elif isinstance(partner_ref, str):
            partner_name = partner_ref

        # Si on a l'ID, récupérer les données complètes depuis Odoo
        partner_data = None
        if partner_id and odoo_client:
            partner_data = self._fetch_partner_from_odoo(odoo_client, partner_id)
            if partner_data:
                partner_name = partner_data.get('name') or partner_name

        if not partner_name:
            return None

        # Créer les données extra selon le type de destination
        if is_donneur_ordre:
            # Mapping pour donneur_ordre.yml
            extra_data = {}
            if partner_data:
                extra_data = {
                    'email': partner_data.get('email'),
                    'telephone': partner_data.get('phone'),  # donneur_ordre.yml: telephone
                    'portable': partner_data.get('mobile'),  # donneur_ordre.yml: portable
                    'adresse_ligne1': partner_data.get('street'),  # donneur_ordre.yml
                    'adresse_ligne2': partner_data.get('street2'),
                    'ville': partner_data.get('city'),
                    'code_postal': partner_data.get('zip'),
                    'siret': partner_data.get('vat'),  # donneur_ordre.yml: siret
                    'code': partner_data.get('ref'),
                    'notes': partner_data.get('comment'),
                }
                # Pays
                country = partner_data.get('country_id')
                if country and isinstance(country, (list, tuple)):
                    extra_data['pays'] = country[1] if len(country) > 1 else None
            return self._get_or_create_donneur_ordre(partner_name, extra_data)
        else:
            # Mapping pour clients.yml
            extra_data = {}
            if partner_data:
                extra_data = {
                    'email': partner_data.get('email'),
                    'phone': partner_data.get('phone'),  # clients.yml: phone
                    'mobile': partner_data.get('mobile'),
                    'address_line1': partner_data.get('street'),  # clients.yml
                    'address_line2': partner_data.get('street2'),
                    'city': partner_data.get('city'),
                    'postal_code': partner_data.get('zip'),
                    'tax_id': partner_data.get('vat'),  # clients.yml: tax_id
                    'code': partner_data.get('ref'),
                    'website': partner_data.get('website'),
                    'notes': partner_data.get('comment'),
                }
                # Pays
                country = partner_data.get('country_id')
                if country and isinstance(country, (list, tuple)):
                    extra_data['country_code'] = country[1] if len(country) > 1 else None
            return self._get_or_create_client(partner_name, extra_data=extra_data)

    def _create_client_from_odoo_partner_with_data(
        self,
        odoo_client: 'OdooAPIClient',
        partner_ref: Any,
        is_donneur_ordre: bool = False
    ) -> Tuple[Optional[str], Optional[Dict]]:
        """
        Comme _create_client_from_odoo_partner mais retourne aussi les données du partenaire.
        Utile pour remplir contact_nom, contact_telephone dans les interventions.
        """
        if not partner_ref or partner_ref is False:
            return None, None

        partner_id = None
        partner_name = None

        # Extraire ID et nom selon le format
        if isinstance(partner_ref, (list, tuple)) and len(partner_ref) >= 2:
            partner_id = partner_ref[0]
            partner_name = partner_ref[1]
        elif isinstance(partner_ref, int):
            partner_id = partner_ref
        elif isinstance(partner_ref, str):
            partner_name = partner_ref

        # Si on a l'ID, récupérer les données complètes depuis Odoo
        partner_data = None
        if partner_id and odoo_client:
            partner_data = self._fetch_partner_from_odoo(odoo_client, partner_id)
            if partner_data:
                partner_name = partner_data.get('name') or partner_name

        if not partner_name:
            return None, None

        # Créer les données extra pour clients.yml
        extra_data = {}
        if partner_data:
            extra_data = {
                'email': partner_data.get('email'),
                'phone': partner_data.get('phone'),
                'mobile': partner_data.get('mobile'),
                'address_line1': partner_data.get('street'),
                'address_line2': partner_data.get('street2'),
                'city': partner_data.get('city'),
                'postal_code': partner_data.get('zip'),
                'tax_id': partner_data.get('vat'),
                'code': partner_data.get('ref'),
                'website': partner_data.get('website'),
                'notes': partner_data.get('comment'),
            }
            country = partner_data.get('country_id')
            if country and isinstance(country, (list, tuple)):
                extra_data['country_code'] = country[1] if len(country) > 1 else None

        client_id = self._get_or_create_client(partner_name, extra_data=extra_data)
        return client_id, partner_data

    def _get_or_create_technicien(self, nom: str) -> Optional[str]:
        """
        Cherche un employé/technicien par nom, retourne son UUID.
        Ne crée pas automatiquement les employés (sécurité).
        Utilise la table employes (employes.yml).
        """
        if not nom or nom.strip() == '':
            return None

        nom = nom.strip()

        # Vérifier le cache
        if nom in self._technicien_cache:
            return self._technicien_cache[nom]

        from moteur.db import Database

        try:
            # Chercher dans la table employes (selon employes.yml)
            existing = Database.query(
                "employes",
                self.tenant_id,
                filters={},
                limit=100
            )

            for emp in existing:
                # employes.yml: champs nom et prenom
                emp_nom = emp.get('nom', '') or ''
                emp_prenom = emp.get('prenom', '') or ''

                # Correspondance par combinaison prénom nom ou nom seul
                if nom.lower() == f"{emp_prenom} {emp_nom}".lower():
                    tech_id = str(emp.get('id'))
                    self._technicien_cache[nom] = tech_id
                    return tech_id
                if nom.lower() == f"{emp_nom} {emp_prenom}".lower():
                    tech_id = str(emp.get('id'))
                    self._technicien_cache[nom] = tech_id
                    return tech_id
                if nom.lower() == emp_nom.lower():
                    tech_id = str(emp.get('id'))
                    self._technicien_cache[nom] = tech_id
                    return tech_id
                # Correspondance partielle (prénom seul si unique)
                if nom.lower() == emp_prenom.lower():
                    tech_id = str(emp.get('id'))
                    self._technicien_cache[nom] = tech_id
                    return tech_id

            logger.debug("technicien_not_found", nom=nom)

        except Exception as e:
            logger.warning("technicien_lookup_error", nom=nom, error=str(e))

        return None

    # -------------------------------------------------------------------------
    # Import CSV
    # -------------------------------------------------------------------------

    def import_from_csv(
        self,
        csv_content: str,
        odoo_model: str,
        module_cible: str,
        options: Dict = None
    ) -> Dict:
        """
        Importe des données depuis un CSV exporté d'Odoo.

        Args:
            csv_content: Contenu du fichier CSV
            odoo_model: Modèle Odoo source (res.partner, product.product, etc.)
            module_cible: Module AZALPLUS cible
            options: Options d'import (update_existing, ignore_errors, etc.)
        """
        options = options or {}
        self.errors = []
        self.imported_ids = []

        # Récupérer le mapping
        mapping = ODOO_MODEL_MAPPING.get(odoo_model, {}).get("fields", {})
        if not mapping:
            return {"success": False, "error": f"Modèle Odoo non supporté: {odoo_model}"}

        # Nettoyer BOM
        if csv_content.startswith('\ufeff'):
            csv_content = csv_content[1:]

        # Détecter le délimiteur
        first_line = csv_content.split('\n')[0]
        delimiter = ';' if ';' in first_line else ','

        # Lire le CSV
        reader = csv.DictReader(io.StringIO(csv_content), delimiter=delimiter)

        records = []
        for row_num, row in enumerate(reader, start=2):
            try:
                record = self._transform_odoo_row(row, mapping, odoo_model)
                if record:
                    records.append(record)
                    self.stats["total"] += 1
            except Exception as e:
                self.errors.append({
                    "ligne": row_num,
                    "erreur": str(e),
                    "data": dict(row)
                })
                self.stats["errors"] += 1

        # Insérer les enregistrements
        from moteur.db import Database

        for record in records:
            try:
                result = Database.insert(module_cible, self.tenant_id, record)
                if result:
                    self.imported_ids.append(str(result.get("id", "")))
                    self.stats["imported"] += 1
            except Exception as e:
                self.errors.append({
                    "erreur": str(e),
                    "data": record
                })
                self.stats["errors"] += 1

        return {
            "success": True,
            "stats": self.stats,
            "errors": self.errors[:100],  # Limiter à 100 erreurs
            "imported_ids": self.imported_ids
        }

    # -------------------------------------------------------------------------
    # Import API
    # -------------------------------------------------------------------------

    def import_from_api(
        self,
        client: OdooAPIClient,
        odoo_model: str,
        module_cible: str,
        domain: List = None,
        fields: List[str] = None,
        limit: int = None,
        options: Dict = None
    ) -> Dict:
        """
        Importe des données via l'API XML-RPC Odoo.

        Args:
            client: Client API Odoo connecté
            odoo_model: Modèle Odoo à importer
            module_cible: Module AZALPLUS cible
            domain: Filtre domaine Odoo
            fields: Champs à récupérer (None = tous)
            limit: Limite d'enregistrements
            options: Options d'import
        """
        options = options or {}
        self.errors = []
        self.imported_ids = []
        self._odoo_client = client  # Stocker pour résolution des relations

        # Récupérer le mapping
        mapping_config = ODOO_MODEL_MAPPING.get(odoo_model, {})
        mapping = mapping_config.get("fields", {})

        if not mapping:
            return {
                "success": False,
                "error": f"Modèle Odoo non supporté: {odoo_model}",
                "stats": {"total": 0, "imported": 0, "updated": 0, "skipped": 0, "errors": 0}
            }

        # Récupérer les champs si non spécifiés
        if not fields:
            fields = list(mapping.keys())

        # Compter le total - avec gestion des erreurs XML-RPC
        try:
            total = client.search_count(odoo_model, domain)
        except xmlrpc.client.Fault as e:
            error_msg = str(e.faultString) if hasattr(e, 'faultString') else str(e)
            if "doesn't exist" in error_msg or "does not exist" in error_msg:
                return {
                    "success": False,
                    "error": f"Le modèle '{odoo_model}' n'existe pas dans votre Odoo. Vérifiez que le module correspondant est installé.",
                    "stats": {"total": 0, "imported": 0, "updated": 0, "skipped": 0, "errors": 1},
                    "errors": [{"row": 0, "error": f"Modèle Odoo introuvable: {odoo_model}"}]
                }
            return {
                "success": False,
                "error": f"Erreur Odoo: {error_msg}",
                "stats": {"total": 0, "imported": 0, "updated": 0, "skipped": 0, "errors": 1},
                "errors": [{"row": 0, "error": error_msg}]
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Erreur de connexion Odoo: {str(e)}",
                "stats": {"total": 0, "imported": 0, "updated": 0, "skipped": 0, "errors": 1},
                "errors": [{"row": 0, "error": str(e)}]
            }
        self.stats["total"] = min(total, limit) if limit else total

        logger.info(
            "odoo_import_start",
            model=odoo_model,
            total=self.stats["total"],
            domain=domain
        )

        # Récupérer les données par lots
        batch_size = 100
        offset = 0

        from moteur.db import Database

        while True:
            current_limit = batch_size
            if limit:
                remaining = limit - offset
                if remaining <= 0:
                    break
                current_limit = min(batch_size, remaining)

            records = client.search_read(
                odoo_model,
                domain=domain,
                fields=fields,
                offset=offset,
                limit=current_limit,
                order="id"
            )

            if not records:
                break

            for record in records:
                try:
                    transformed = self._transform_odoo_record(record, mapping, odoo_model)
                    if transformed:
                        result = Database.insert(module_cible, self.tenant_id, transformed)
                        if result:
                            self.imported_ids.append(str(result.get("id", "")))
                            self.stats["imported"] += 1
                except Exception as e:
                    self.errors.append({
                        "odoo_id": record.get("id"),
                        "erreur": str(e)
                    })
                    self.stats["errors"] += 1

            offset += len(records)

            logger.info(
                "odoo_import_progress",
                imported=self.stats["imported"],
                total=self.stats["total"]
            )

        return {
            "success": True,
            "stats": self.stats,
            "errors": self.errors[:100],
            "imported_ids": self.imported_ids
        }

    # -------------------------------------------------------------------------
    # Transformation des données
    # -------------------------------------------------------------------------

    def _transform_odoo_row(
        self,
        row: Dict[str, str],
        mapping: Dict[str, str],
        odoo_model: str
    ) -> Optional[Dict]:
        """Transforme une ligne CSV Odoo vers format AZALPLUS."""
        result = {}

        # Normaliser les clés (Odoo exporte parfois avec des espaces)
        normalized_row = {}
        for key, value in row.items():
            clean_key = key.strip().lower().replace(' ', '_').replace('/', '_')
            normalized_row[clean_key] = value

        # Mapper les champs
        for odoo_field, azal_field in mapping.items():
            if azal_field.startswith("__"):
                continue  # Champ de contrôle interne

            # Chercher la valeur (essayer plusieurs variantes)
            value = None
            for variant in [odoo_field, odoo_field.lower(), odoo_field.replace('.', '_')]:
                if variant in normalized_row:
                    value = normalized_row[variant]
                    break

            if value is not None and value != '':
                result[azal_field] = self._convert_value(value, odoo_field, odoo_model)

        return result if result else None

    def _transform_odoo_record(
        self,
        record: Dict,
        mapping: Dict[str, str],
        odoo_model: str
    ) -> Optional[Dict]:
        """Transforme un enregistrement API Odoo vers format AZALPLUS."""
        result = {}
        client_data_for_contact = None  # Pour stocker les données client

        for odoo_field, azal_field in mapping.items():
            # Ignorer les champs internes
            if azal_field.startswith("__"):
                continue

            value = record.get(odoo_field)

            # Gérer les résolutions de relations (@resolve:field_name)
            if azal_field.startswith("@resolve:"):
                target_field = azal_field[9:]  # Enlever "@resolve:"
                if value is not None and value is not False:
                    resolved_id, partner_data = self._resolve_relation_with_data(odoo_field, value, target_field)
                    if resolved_id:
                        result[target_field] = resolved_id
                    # Stocker les données client pour remplir contact_nom/telephone
                    if target_field == 'client_id' and partner_data:
                        client_data_for_contact = partner_data
                continue

            if value is not None and value is not False:
                result[azal_field] = self._convert_api_value(value, odoo_field, odoo_model)

        # Post-traitement: extraire ville/code_postal de l'adresse si manquants
        if 'adresse_intervention' in result and (not result.get('ville') or not result.get('code_postal')):
            parsed = self._parse_address(result['adresse_intervention'])
            if parsed.get('ville') and not result.get('ville'):
                result['ville'] = parsed['ville']
            if parsed.get('code_postal') and not result.get('code_postal'):
                result['code_postal'] = parsed['code_postal']

        # Post-traitement: remplir contact depuis les données client
        if client_data_for_contact:
            if not result.get('contact_nom'):
                result['contact_nom'] = client_data_for_contact.get('name') or client_data_for_contact.get('display_name')
            if not result.get('contact_telephone'):
                result['contact_telephone'] = client_data_for_contact.get('phone') or client_data_for_contact.get('mobile')
            if not result.get('contact_email'):
                result['contact_email'] = client_data_for_contact.get('email')

        return result if result else None

    def _parse_address(self, address: str) -> Dict[str, str]:
        """
        Parse une adresse pour extraire ville et code postal.
        Formats supportés:
        - "rue, 13000, Marseille, France"
        - "rue\\n13000 Marseille"
        - "rue, Marseille 13000"
        """
        result = {}
        if not address:
            return result

        # Nettoyer et normaliser
        address = address.replace('\\n', ', ').replace('\n', ', ')
        parts = [p.strip() for p in address.split(',')]

        # Chercher un code postal français (5 chiffres)
        import re
        for part in parts:
            # Code postal seul
            cp_match = re.search(r'\b(\d{5})\b', part)
            if cp_match:
                result['code_postal'] = cp_match.group(1)
                # La ville peut être dans la même partie ou la suivante
                remaining = part.replace(cp_match.group(0), '').strip()
                if remaining and remaining.lower() not in ['france', 'fr']:
                    result['ville'] = remaining
                continue

            # Si pas de code postal dans cette partie, c'est peut-être la ville
            if part and part.lower() not in ['france', 'fr'] and not re.match(r'^\d+', part):
                # Si on a déjà un code postal et pas encore de ville
                if 'code_postal' in result and 'ville' not in result:
                    result['ville'] = part

        return result

    def _resolve_relation(self, odoo_field: str, value: Any, target_field: str) -> Optional[str]:
        """
        Résout une relation Odoo vers un UUID AZALPLUS.
        Crée l'entité si elle n'existe pas.
        """
        resolved_id, _ = self._resolve_relation_with_data(odoo_field, value, target_field)
        return resolved_id

    def _resolve_relation_with_data(self, odoo_field: str, value: Any, target_field: str) -> Tuple[Optional[str], Optional[Dict]]:
        """
        Résout une relation Odoo vers un UUID AZALPLUS.
        Retourne (uuid, partner_data) pour permettre de récupérer les données contact.
        """
        partner_data = None

        # Déterminer le type de relation
        if target_field == 'technicien_id':
            # Pour les techniciens, on cherche sans créer
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                return self._get_or_create_technicien(value[1]), None
            elif isinstance(value, str):
                return self._get_or_create_technicien(value), None

        elif target_field == 'donneur_ordre_id':
            # Donneur d'ordre = créer comme client type DONNEUR_ORDRE
            resolved_id = self._create_client_from_odoo_partner(
                self._odoo_client, value, is_donneur_ordre=True
            )
            return resolved_id, None

        elif target_field == 'client_id':
            # Client final = créer comme client normal + récupérer les données
            resolved_id, partner_data = self._create_client_from_odoo_partner_with_data(
                self._odoo_client, value, is_donneur_ordre=False
            )
            return resolved_id, partner_data

        return None, None

    def _convert_value(self, value: str, field_name: str, model: str) -> Any:
        """Convertit une valeur CSV vers le type approprié."""
        if not value or value.strip() == '':
            return None

        value = value.strip()

        # Détection du type par le nom du champ
        if field_name.endswith('_id'):
            # Relation many2one: "Nom (id)" -> id ou nom
            match = re.match(r'^(.+?)\s*\((\d+)\)$', value)
            if match:
                return match.group(1)  # Retourner le nom
            return value

        if field_name.endswith('_ids'):
            # Relation many2many
            return [v.strip() for v in value.split(',')]

        if field_name in ['date', 'date_order', 'invoice_date', 'date_start', 'birthday']:
            # Date
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                try:
                    return datetime.strptime(value, fmt).date().isoformat()
                except ValueError:
                    continue
            return value

        if field_name in ['create_date', 'write_date', 'date_done', 'scheduled_date']:
            # Datetime
            for fmt in ['%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
                try:
                    return datetime.strptime(value, fmt).isoformat()
                except ValueError:
                    continue
            return value

        if field_name in ['amount_total', 'amount_untaxed', 'amount_tax', 'price_unit',
                          'list_price', 'standard_price', 'credit_limit', 'expected_revenue']:
            # Montant
            try:
                return float(value.replace(',', '.').replace(' ', ''))
            except ValueError:
                return None

        if field_name in ['qty_available', 'virtual_available', 'product_uom_qty',
                          'planned_hours', 'probability']:
            # Nombre
            try:
                return float(value.replace(',', '.').replace(' ', ''))
            except ValueError:
                return None

        if field_name in ['active', 'sale_ok', 'purchase_ok', 'is_company']:
            # Booléen
            return value.lower() in ['true', '1', 'yes', 'oui', 'vrai']

        if field_name == 'state':
            # Statut
            return ODOO_STATUS_MAPPING.get(value.lower(), value.upper())

        return value

    def _convert_api_value(self, value: Any, field_name: str, model: str) -> Any:
        """Convertit une valeur API vers le format AZALPLUS."""
        if value is None or value is False:
            return None

        # Many2one: retourne tuple (id, name)
        if isinstance(value, (list, tuple)) and len(value) == 2:
            if isinstance(value[0], int):
                return value[1]  # Retourner le nom

        # Many2many/One2many: liste d'IDs
        if isinstance(value, list) and all(isinstance(v, int) for v in value):
            return value

        # Statut
        if field_name == 'state' and isinstance(value, str):
            return ODOO_STATUS_MAPPING.get(value, value.upper())

        # Booléen
        if isinstance(value, bool):
            return value

        # Date/Datetime (API retourne des strings ISO)
        if isinstance(value, str) and field_name in ['date', 'date_order', 'invoice_date',
                                                       'create_date', 'write_date']:
            return value

        return value


# =============================================================================
# SERVICE EXPORT ODOO
# =============================================================================

class OdooExportService:
    """Service d'export vers format Odoo."""

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id

    def export_to_csv(
        self,
        module_source: str,
        odoo_model: str,
        records: List[Dict],
        options: Dict = None
    ) -> str:
        """
        Exporte des données AZALPLUS vers CSV format Odoo.

        Args:
            module_source: Module AZALPLUS source
            odoo_model: Modèle Odoo cible
            records: Enregistrements à exporter
            options: Options d'export
        """
        options = options or {}

        # Récupérer le mapping inversé
        mapping_config = ODOO_MODEL_MAPPING.get(odoo_model, {})
        mapping = mapping_config.get("fields", {})

        if not mapping:
            raise ValueError(f"Modèle Odoo non supporté: {odoo_model}")

        # Inverser le mapping (azal -> odoo)
        reverse_mapping = {v: k for k, v in mapping.items() if not v.startswith("__")}

        # Déterminer les colonnes Odoo à exporter
        odoo_fields = [k for k, v in mapping.items() if not v.startswith("__")]

        # Créer le CSV
        output = io.StringIO()
        output.write('\ufeff')  # BOM UTF-8

        writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)

        # En-têtes
        writer.writerow(odoo_fields)

        # Données
        for record in records:
            row = []
            for odoo_field in odoo_fields:
                azal_field = mapping.get(odoo_field)
                if azal_field and azal_field in record:
                    value = self._format_for_odoo(record[azal_field], odoo_field)
                    row.append(value)
                else:
                    row.append('')
            writer.writerow(row)

        logger.info(
            "odoo_export_csv",
            module=module_source,
            odoo_model=odoo_model,
            records=len(records)
        )

        return output.getvalue()

    def export_to_api(
        self,
        client: OdooAPIClient,
        module_source: str,
        odoo_model: str,
        records: List[Dict],
        options: Dict = None
    ) -> Dict:
        """
        Exporte des données vers Odoo via API XML-RPC.

        Args:
            client: Client API Odoo connecté
            module_source: Module AZALPLUS source
            odoo_model: Modèle Odoo cible
            records: Enregistrements à exporter
            options: Options d'export (update_existing, etc.)
        """
        options = options or {}
        errors = []
        created_ids = []
        updated_ids = []

        # Récupérer le mapping inversé
        mapping_config = ODOO_MODEL_MAPPING.get(odoo_model, {})
        mapping = mapping_config.get("fields", {})

        if not mapping:
            return {"success": False, "error": f"Modèle Odoo non supporté: {odoo_model}"}

        # Inverser le mapping
        reverse_mapping = {v: k for k, v in mapping.items() if not v.startswith("__")}

        for record in records:
            try:
                odoo_values = {}
                for azal_field, value in record.items():
                    odoo_field = reverse_mapping.get(azal_field)
                    if odoo_field and value is not None:
                        odoo_values[odoo_field] = self._convert_for_api(value, odoo_field)

                if not odoo_values:
                    continue

                # Créer dans Odoo
                odoo_id = client.create(odoo_model, odoo_values)
                created_ids.append(odoo_id)

            except Exception as e:
                errors.append({
                    "azal_id": record.get("id"),
                    "erreur": str(e)
                })

        return {
            "success": True,
            "created": len(created_ids),
            "updated": len(updated_ids),
            "errors": len(errors),
            "created_ids": created_ids,
            "error_details": errors[:50]
        }

    def _format_for_odoo(self, value: Any, field_name: str) -> str:
        """Formate une valeur pour export CSV Odoo."""
        if value is None:
            return ''

        if isinstance(value, bool):
            return 'True' if value else 'False'

        if isinstance(value, (datetime, date)):
            return value.strftime('%Y-%m-%d')

        if isinstance(value, float):
            return str(value)

        if isinstance(value, list):
            return ','.join(str(v) for v in value)

        return str(value)

    def _convert_for_api(self, value: Any, field_name: str) -> Any:
        """Convertit une valeur pour l'API Odoo."""
        if value is None:
            return False  # Odoo utilise False pour les valeurs nulles

        # Les relations many2one doivent être des IDs
        if field_name.endswith('_id') and isinstance(value, str):
            # Si c'est un nom, on ne peut pas le résoudre automatiquement
            return value

        return value


# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================

def get_supported_odoo_models() -> List[Dict]:
    """Retourne la liste des modèles Odoo supportés."""
    return [
        {"model": model, "module": config["module"]}
        for model, config in ODOO_MODEL_MAPPING.items()
    ]


def get_field_mapping(odoo_model: str) -> Dict[str, str]:
    """Retourne le mapping des champs pour un modèle Odoo."""
    config = ODOO_MODEL_MAPPING.get(odoo_model, {})
    return config.get("fields", {})


def test_odoo_connection(url: str, db: str, username: str, password: str) -> Dict:
    """Teste la connexion à une instance Odoo."""

    # Auto-ajouter https:// si manquant
    if url and not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Validation des paramètres
    if not url:
        return {"success": False, "error": "URL Odoo manquante"}
    if not db:
        return {"success": False, "error": "Nom de base de données manquant"}
    if not username:
        return {"success": False, "error": "Identifiant manquant"}
    if not password:
        return {"success": False, "error": "Clé API / mot de passe manquant"}

    try:
        client = OdooAPIClient(url, db, username, password)

        if client.connect():
            version = client.get_version()
            return {
                "success": True,
                "version": version,
                "uid": client.uid
            }
        else:
            return {
                "success": False,
                "error": f"Échec de l'authentification. Vérifiez: base='{db}', login='{username}'"
            }
    except Exception as e:
        error_msg = str(e)
        if "Connection refused" in error_msg:
            return {"success": False, "error": f"Connexion refusée à {url}. Vérifiez l'URL."}
        elif "Name or service not known" in error_msg or "getaddrinfo failed" in error_msg:
            return {"success": False, "error": f"URL invalide ou inaccessible: {url}"}
        elif "SSL" in error_msg or "certificate" in error_msg.lower():
            return {"success": False, "error": f"Erreur SSL/certificat. Essayez http:// au lieu de https://"}
        else:
            return {"success": False, "error": f"Erreur: {error_msg}"}
