# =============================================================================
# AZALPLUS - Smart Suggestions / Autocomplete Engine
# =============================================================================
"""
Service de suggestions intelligentes pour l'autocompletion.
Utilise dans les formulaires Devis/Facture pour:
- Recherche de clients (nom, email, telephone)
- Recherche de produits (nom, code, SKU)
- Suggestions recentes par module/utilisateur

IMPORTANT: tenant_id obligatoire sur toutes les operations (AZA-TENANT)
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
import structlog

from .db import Database
from .tenant import get_current_tenant

logger = structlog.get_logger()


# =============================================================================
# Suggestion Service
# =============================================================================
class SuggestionService:
    """
    Service de suggestions intelligentes.
    IMPORTANT: Toutes les methodes requierent tenant_id (multi-tenant).
    """

    # Champs de recherche par entite
    CLIENT_SEARCH_FIELDS = ["name", "legal_name", "email", "phone", "mobile", "code"]
    PRODUCT_SEARCH_FIELDS = ["name", "code", "sku", "barcode", "ean13", "trade_name", "description"]

    def __init__(self, tenant_id: UUID, user_id: Optional[UUID] = None):
        """
        Initialise le service de suggestions.

        Args:
            tenant_id: ID du tenant (OBLIGATOIRE)
            user_id: ID de l'utilisateur pour les suggestions personnalisees
        """
        if not tenant_id:
            raise ValueError("tenant_id est obligatoire (AZA-TENANT)")

        self.tenant_id = tenant_id
        self.user_id = user_id

    # =========================================================================
    # Suggestions Clients
    # =========================================================================
    def suggest_clients(
        self,
        query: str,
        limit: int = 10,
        include_recent: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Recherche des clients pour autocompletion.

        Args:
            query: Terme de recherche (nom, email, telephone)
            limit: Nombre max de resultats
            include_recent: Inclure les clients recents en priorite

        Returns:
            Liste de clients correspondants avec infos essentielles
        """
        logger.debug(
            "suggest_clients",
            tenant_id=str(self.tenant_id),
            query=query,
            limit=limit
        )

        results = []

        # Si query vide ou trop court, retourner les clients recents
        if not query or len(query) < 2:
            if include_recent:
                return self._get_recent_clients(limit)
            return []

        # Recherche multi-champs avec ILIKE
        search_term = f"%{query.lower()}%"

        with Database.get_session() as session:
            try:
                # Construire la clause WHERE avec OR pour chaque champ
                where_clauses = []
                for field in self.CLIENT_SEARCH_FIELDS:
                    where_clauses.append(
                        f"COALESCE(LOWER(CAST({field} AS TEXT)), '') LIKE :search_term"
                    )

                search_condition = " OR ".join(where_clauses)

                sql = f'''
                    SELECT
                        id, code, name, legal_name, email, phone, mobile,
                        type, city, credit_limit, solde_credit,
                        is_active, created_at
                    FROM azalplus.clients
                    WHERE tenant_id = :tenant_id
                    AND deleted_at IS NULL
                    AND is_active = true
                    AND ({search_condition})
                    ORDER BY
                        CASE
                            WHEN LOWER(name) LIKE :exact_term THEN 0
                            WHEN LOWER(name) LIKE :start_term THEN 1
                            ELSE 2
                        END,
                        name ASC
                    LIMIT :limit
                '''

                from sqlalchemy import text
                result = session.execute(
                    text(sql),
                    {
                        "tenant_id": str(self.tenant_id),
                        "search_term": search_term,
                        "exact_term": query.lower(),
                        "start_term": f"{query.lower()}%",
                        "limit": limit
                    }
                )

                for row in result:
                    results.append(self._format_client_suggestion(dict(row._mapping)))

            except Exception as e:
                logger.error("suggest_clients_error", error=str(e))

        return results

    def _get_recent_clients(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retourne les clients les plus recemment utilises."""
        results = []

        # D'abord les clients utilises recemment (par factures/devis)
        recent_used = self._get_recently_used_clients(limit // 2)
        results.extend(recent_used)

        # Completer avec les clients crees recemment
        remaining = limit - len(results)
        if remaining > 0:
            recent_created = Database.query(
                "clients",
                self.tenant_id,
                filters={"is_active": True},
                order_by="created_at DESC",
                limit=remaining
            )

            # Eviter les doublons
            existing_ids = {r["id"] for r in results}
            for client in recent_created:
                if client["id"] not in existing_ids:
                    results.append(self._format_client_suggestion(client))

        return results[:limit]

    def _get_recently_used_clients(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Retourne les clients utilises dans les derniers documents."""
        results = []

        with Database.get_session() as session:
            try:
                # Rechercher dans les devis et factures recents
                sql = '''
                    WITH recent_customers AS (
                        SELECT DISTINCT customer_id, MAX(created_at) as last_used
                        FROM azalplus.factures
                        WHERE tenant_id = :tenant_id
                        AND deleted_at IS NULL
                        AND customer_id IS NOT NULL
                        GROUP BY customer_id

                        UNION

                        SELECT DISTINCT client as customer_id, MAX(created_at) as last_used
                        FROM azalplus.devis
                        WHERE tenant_id = :tenant_id
                        AND deleted_at IS NULL
                        AND client IS NOT NULL
                        GROUP BY client
                    )
                    SELECT c.id, c.code, c.name, c.legal_name, c.email, c.phone, c.mobile,
                           c.type, c.city, c.credit_limit, c.solde_credit, c.is_active
                    FROM azalplus.clients c
                    INNER JOIN recent_customers rc ON c.id::text = rc.customer_id::text
                    WHERE c.tenant_id = :tenant_id
                    AND c.deleted_at IS NULL
                    AND c.is_active = true
                    ORDER BY rc.last_used DESC
                    LIMIT :limit
                '''

                from sqlalchemy import text
                result = session.execute(
                    text(sql),
                    {
                        "tenant_id": str(self.tenant_id),
                        "limit": limit
                    }
                )

                for row in result:
                    results.append(self._format_client_suggestion(dict(row._mapping)))

            except Exception as e:
                logger.debug("recently_used_clients_error", error=str(e))

        return results

    def _format_client_suggestion(self, client: Dict) -> Dict[str, Any]:
        """Formate un client pour l'autocompletion."""
        return {
            "id": str(client.get("id")),
            "code": client.get("code"),
            "name": client.get("name") or client.get("legal_name", ""),
            "legal_name": client.get("legal_name"),
            "email": client.get("email"),
            "phone": client.get("phone") or client.get("mobile"),
            "type": client.get("type"),
            "city": client.get("city"),
            "credit_limit": client.get("credit_limit"),
            "solde_credit": client.get("solde_credit"),
            # Label combine pour affichage
            "label": self._build_client_label(client),
            "sublabel": self._build_client_sublabel(client)
        }

    def _build_client_label(self, client: Dict) -> str:
        """Construit le label principal du client."""
        name = client.get("name") or client.get("legal_name", "Client")
        code = client.get("code")
        if code:
            return f"{name} ({code})"
        return name

    def _build_client_sublabel(self, client: Dict) -> str:
        """Construit le sous-label du client (info secondaire)."""
        parts = []
        if client.get("email"):
            parts.append(client["email"])
        if client.get("phone"):
            parts.append(client["phone"])
        elif client.get("mobile"):
            parts.append(client["mobile"])
        if client.get("city"):
            parts.append(client["city"])
        return " - ".join(parts) if parts else ""

    # =========================================================================
    # Suggestions Produits
    # =========================================================================
    def suggest_products(
        self,
        query: str,
        limit: int = 10,
        include_stock: bool = True,
        only_sellable: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Recherche des produits pour autocompletion.

        Args:
            query: Terme de recherche (nom, code, SKU)
            limit: Nombre max de resultats
            include_stock: Inclure les infos de stock
            only_sellable: Filtrer sur is_sellable=true

        Returns:
            Liste de produits correspondants avec infos essentielles
        """
        logger.debug(
            "suggest_products",
            tenant_id=str(self.tenant_id),
            query=query,
            limit=limit
        )

        results = []

        # Si query vide ou trop court, retourner les produits populaires
        if not query or len(query) < 2:
            return self._get_popular_products(limit)

        # Recherche multi-champs avec ILIKE
        search_term = f"%{query.lower()}%"

        with Database.get_session() as session:
            try:
                # Construire la clause WHERE
                where_clauses = []
                for field in self.PRODUCT_SEARCH_FIELDS:
                    where_clauses.append(
                        f"COALESCE(LOWER(CAST({field} AS TEXT)), '') LIKE :search_term"
                    )

                search_condition = " OR ".join(where_clauses)

                # Filtre vendable
                sellable_filter = "AND is_sellable = true" if only_sellable else ""

                sql = f'''
                    SELECT
                        id, code, name, trade_name, sku, barcode,
                        sale_price, standard_cost, tax_rate,
                        stock_actuel, stock_disponible, stock_minimum,
                        statut_stock, gestion_stock, unit,
                        type, status, has_variants, image_url
                    FROM azalplus.produits
                    WHERE tenant_id = :tenant_id
                    AND deleted_at IS NULL
                    AND status = 'ACTIVE'
                    {sellable_filter}
                    AND ({search_condition})
                    ORDER BY
                        CASE
                            WHEN LOWER(code) = :exact_term THEN 0
                            WHEN LOWER(sku) = :exact_term THEN 0
                            WHEN LOWER(name) LIKE :start_term THEN 1
                            WHEN LOWER(code) LIKE :start_term THEN 1
                            ELSE 2
                        END,
                        name ASC
                    LIMIT :limit
                '''

                from sqlalchemy import text
                result = session.execute(
                    text(sql),
                    {
                        "tenant_id": str(self.tenant_id),
                        "search_term": search_term,
                        "exact_term": query.lower(),
                        "start_term": f"{query.lower()}%",
                        "limit": limit
                    }
                )

                for row in result:
                    results.append(self._format_product_suggestion(dict(row._mapping), include_stock))

            except Exception as e:
                logger.error("suggest_products_error", error=str(e))

        return results

    def _get_popular_products(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retourne les produits les plus vendus ou utilises."""
        results = []

        # Produits les plus utilises dans les documents recents
        with Database.get_session() as session:
            try:
                sql = '''
                    SELECT
                        p.id, p.code, p.name, p.trade_name, p.sku, p.barcode,
                        p.sale_price, p.standard_cost, p.tax_rate,
                        p.stock_actuel, p.stock_disponible, p.stock_minimum,
                        p.statut_stock, p.gestion_stock, p.unit,
                        p.type, p.status, p.has_variants, p.image_url
                    FROM azalplus.produits p
                    WHERE p.tenant_id = :tenant_id
                    AND p.deleted_at IS NULL
                    AND p.status = 'ACTIVE'
                    AND p.is_sellable = true
                    ORDER BY p.created_at DESC
                    LIMIT :limit
                '''

                from sqlalchemy import text
                result = session.execute(
                    text(sql),
                    {
                        "tenant_id": str(self.tenant_id),
                        "limit": limit
                    }
                )

                for row in result:
                    results.append(self._format_product_suggestion(dict(row._mapping), True))

            except Exception as e:
                logger.debug("popular_products_error", error=str(e))

        return results

    def _format_product_suggestion(self, product: Dict, include_stock: bool = True) -> Dict[str, Any]:
        """Formate un produit pour l'autocompletion."""
        result = {
            "id": str(product.get("id")),
            "code": product.get("code"),
            "name": product.get("name") or product.get("trade_name", ""),
            "trade_name": product.get("trade_name"),
            "sku": product.get("sku"),
            "barcode": product.get("barcode"),
            "sale_price": float(product.get("sale_price") or 0),
            "tax_rate": float(product.get("tax_rate") or 20),
            "unit": product.get("unit", "pce"),
            "type": product.get("type"),
            "has_variants": product.get("has_variants", False),
            "image_url": product.get("image_url"),
            # Label combine pour affichage
            "label": self._build_product_label(product),
            "sublabel": self._build_product_sublabel(product, include_stock)
        }

        # Infos stock si demande
        if include_stock:
            result.update({
                "stock_actuel": product.get("stock_actuel", 0),
                "stock_disponible": product.get("stock_disponible", 0),
                "stock_minimum": product.get("stock_minimum", 0),
                "statut_stock": product.get("statut_stock"),
                "gestion_stock": product.get("gestion_stock", True),
                "stock_badge": self._get_stock_badge(product)
            })

        return result

    def _build_product_label(self, product: Dict) -> str:
        """Construit le label principal du produit."""
        name = product.get("name") or product.get("trade_name", "Produit")
        code = product.get("code") or product.get("sku")
        if code:
            return f"{name} ({code})"
        return name

    def _build_product_sublabel(self, product: Dict, include_stock: bool) -> str:
        """Construit le sous-label du produit (prix, stock)."""
        parts = []

        # Prix
        price = product.get("sale_price")
        if price:
            parts.append(f"{float(price):.2f} EUR")

        # Stock
        if include_stock and product.get("gestion_stock", True):
            stock = product.get("stock_disponible", 0)
            parts.append(f"Stock: {stock}")

        return " - ".join(parts) if parts else ""

    def _get_stock_badge(self, product: Dict) -> Dict[str, str]:
        """Retourne le badge de stock avec couleur."""
        if not product.get("gestion_stock", True):
            return {"text": "Non gere", "color": "gray"}

        statut = product.get("statut_stock", "EN_STOCK")
        stock = product.get("stock_disponible", 0)

        if statut == "RUPTURE" or stock <= 0:
            return {"text": "Rupture", "color": "red"}
        elif statut == "STOCK_BAS":
            return {"text": f"Stock bas ({stock})", "color": "orange"}
        else:
            return {"text": f"En stock ({stock})", "color": "green"}

    # =========================================================================
    # Suggestions Recentes (generique par module)
    # =========================================================================
    def suggest_recent(
        self,
        module: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retourne les elements recents d'un module.

        Args:
            module: Nom du module (clients, produits, etc.)
            limit: Nombre max de resultats

        Returns:
            Liste d'elements recents
        """
        logger.debug(
            "suggest_recent",
            tenant_id=str(self.tenant_id),
            module=module,
            limit=limit
        )

        if module.lower() in ["clients", "client"]:
            return self._get_recent_clients(limit)
        elif module.lower() in ["produits", "produit", "products", "product"]:
            return self._get_popular_products(limit)
        else:
            # Generique: retourner les derniers crees
            items = Database.query(
                module,
                self.tenant_id,
                order_by="created_at DESC",
                limit=limit
            )
            return [{"id": str(item.get("id")), **item} for item in items]

    # =========================================================================
    # Creation rapide (inline)
    # =========================================================================
    def create_client_quick(
        self,
        name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cree un client rapidement (creation inline).

        Args:
            name: Nom du client (obligatoire)
            email: Email (optionnel)
            phone: Telephone (optionnel)

        Returns:
            Client cree
        """
        logger.info(
            "create_client_quick",
            tenant_id=str(self.tenant_id),
            name=name
        )

        # Generer un code client
        code = self._generate_client_code(name)

        client_data = {
            "name": name,
            "code": code,
            "type": "PROSPECT",
            "is_active": True
        }

        if email:
            client_data["email"] = email
        if phone:
            client_data["phone"] = phone

        client = Database.insert(
            "clients",
            self.tenant_id,
            client_data,
            self.user_id
        )

        return self._format_client_suggestion(client)

    def _generate_client_code(self, name: str) -> str:
        """Genere un code client unique."""
        # Prendre les 3 premieres lettres du nom
        prefix = "".join(c for c in name.upper() if c.isalpha())[:3]
        if len(prefix) < 3:
            prefix = prefix.ljust(3, "X")

        # Compter les clients avec ce prefix
        count = len(Database.query(
            "clients",
            self.tenant_id,
            limit=1000
        ))

        return f"{prefix}{(count + 1):05d}"


# =============================================================================
# Fonctions utilitaires pour l'API
# =============================================================================
def suggest_clients(
    tenant_id: UUID,
    query: str,
    limit: int = 10,
    user_id: Optional[UUID] = None
) -> List[Dict[str, Any]]:
    """Fonction raccourci pour suggestions clients."""
    service = SuggestionService(tenant_id, user_id)
    return service.suggest_clients(query, limit)


def suggest_products(
    tenant_id: UUID,
    query: str,
    limit: int = 10,
    user_id: Optional[UUID] = None,
    include_stock: bool = True
) -> List[Dict[str, Any]]:
    """Fonction raccourci pour suggestions produits."""
    service = SuggestionService(tenant_id, user_id)
    return service.suggest_products(query, limit, include_stock)


def suggest_recent(
    tenant_id: UUID,
    module: str,
    limit: int = 10,
    user_id: Optional[UUID] = None
) -> List[Dict[str, Any]]:
    """Fonction raccourci pour suggestions recentes."""
    service = SuggestionService(tenant_id, user_id)
    return service.suggest_recent(module, limit)


def create_client_quick(
    tenant_id: UUID,
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    user_id: Optional[UUID] = None
) -> Dict[str, Any]:
    """Fonction raccourci pour creation rapide client."""
    service = SuggestionService(tenant_id, user_id)
    return service.create_client_quick(name, email, phone)
