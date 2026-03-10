# =============================================================================
# AZALPLUS - Database Engine
# =============================================================================
"""
Gestion de la base de données PostgreSQL.
- Connexion pool
- Génération de tables depuis YAML
- Requêtes avec isolation tenant automatique
"""

from sqlalchemy import create_engine, text, MetaData, Table, Column, inspect
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP, INET
from sqlalchemy import String, Integer, Boolean, Numeric, Date, DateTime, Text, ForeignKey
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Generator
import redis.asyncio as redis
import structlog
import json
from uuid import UUID as PyUUID, uuid4

from .config import settings

logger = structlog.get_logger()

# =============================================================================
# Type Mapping YAML → SQLAlchemy
# =============================================================================
TYPE_MAPPING = {
    # Texte
    "texte": String(255),
    "texte court": String(100),
    "texte long": Text,
    "email": String(255),
    "telephone": String(20),
    "url": String(500),

    # Nombres
    "nombre": Numeric(15, 2),
    "entier": Integer,
    "monnaie": Numeric(15, 2),
    "pourcentage": Numeric(5, 2),

    # Dates
    "date": Date,
    "datetime": DateTime,
    "heure": String(8),

    # Booléen
    "oui/non": Boolean,
    "booleen": Boolean,

    # Spéciaux
    "uuid": UUID(as_uuid=True),
    "json": JSONB,
    "fichier": String(500),
    "image": String(500),
}

# =============================================================================
# Database Class
# =============================================================================
class Database:
    """Gestionnaire de base de données."""

    _engine = None
    _session_factory = None
    _redis = None
    _metadata = MetaData(schema="azalplus")

    @classmethod
    async def connect(cls):
        """Initialise la connexion à la base de données."""
        cls._engine = create_engine(
            settings.DATABASE_URL,
            poolclass=QueuePool,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_pre_ping=True,
            echo=settings.DEBUG
        )

        cls._session_factory = sessionmaker(
            bind=cls._engine,
            autocommit=False,
            autoflush=False
        )

        # Redis
        cls._redis = redis.from_url(settings.REDIS_URL)

        logger.info("database_connected", url=settings.DATABASE_URL[:30] + "...")

    @classmethod
    async def disconnect(cls):
        """Ferme les connexions."""
        if cls._engine:
            cls._engine.dispose()
        if cls._redis:
            await cls._redis.close()
        logger.info("database_disconnected")

    @classmethod
    async def is_healthy(cls) -> bool:
        """Vérifie que la DB est accessible."""
        try:
            with cls.get_session() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    @classmethod
    async def cache_healthy(cls) -> bool:
        """Vérifie que Redis est accessible."""
        try:
            await cls._redis.ping()
            return True
        except Exception:
            return False

    @classmethod
    @contextmanager
    def get_session(cls) -> Generator[Session, None, None]:
        """Retourne une session DB avec gestion automatique."""
        session = cls._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @classmethod
    def get_redis(cls):
        """Retourne le client Redis."""
        return cls._redis

    # =========================================================================
    # Génération de tables depuis YAML
    # =========================================================================
    @classmethod
    def create_table_from_definition(cls, module_name: str, definition: Dict[str, Any]):
        """Crée une table SQL depuis une définition YAML."""

        columns = [
            # Colonnes système (automatiques)
            Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
            Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
            Column("created_at", TIMESTAMP, server_default=text("NOW()")),
            Column("updated_at", TIMESTAMP, onupdate=text("NOW()")),
            Column("created_by", UUID(as_uuid=True)),
            Column("updated_by", UUID(as_uuid=True)),
            Column("deleted_at", TIMESTAMP),  # Soft delete
            # Colonne pour les champs personnalises (JSONB)
            Column("custom_fields", JSONB, nullable=True, default={}),
            # Colonnes d'archivage
            Column("archived", Boolean, server_default=text("false"), index=True),
            Column("archived_at", TIMESTAMP),
            Column("archived_by", UUID(as_uuid=True)),
            Column("archive_raison", Text),
        ]

        # Colonnes depuis la définition YAML - supporte liste et dict
        champs = definition.get("champs", {})
        if isinstance(champs, list):
            # Format liste: [{nom: x, type: y}, ...]
            for field_config in champs:
                if isinstance(field_config, dict) and "nom" in field_config:
                    nom = field_config["nom"]
                    col = cls._parse_column(nom, field_config)
                    if col is not None:
                        columns.append(col)
        elif isinstance(champs, dict):
            # Format dict: {nom: config, ...}
            for nom, config in champs.items():
                col = cls._parse_column(nom, config)
                if col is not None:
                    columns.append(col)

        # Créer la table
        table = Table(
            module_name,
            cls._metadata,
            *columns,
            extend_existing=True
        )

        # Créer en base si n'existe pas
        table.create(cls._engine, checkfirst=True)

        logger.info("table_created", table=module_name, columns=len(columns))
        return table

    # Tracking des champs encryptés par module
    _encrypted_fields: Dict[str, List[str]] = {}

    @classmethod
    def _parse_column(cls, nom: str, config) -> Optional[Column]:
        """Parse une définition de colonne YAML en Column SQLAlchemy."""

        # Config peut être une string simple, un dict, ou une liste (embedded)
        if isinstance(config, list):
            # Champs imbriqués (ex: lignes de facture) -> stockés en JSONB
            return Column(nom, JSONB, nullable=True, default=[])

        if isinstance(config, str):
            parts = config.split()
            type_str = parts[0]
            nullable = "requis" not in parts
            default = None
            is_encrypted = False
        else:
            type_str = config.get("type", "texte")
            nullable = not config.get("requis", False) and not config.get("obligatoire", False)
            default = config.get("defaut")
            # Support pour l'attribut chiffre: true
            is_encrypted = config.get("chiffre", False) or config.get("encrypted", False)

        # Mapper le type
        sql_type = TYPE_MAPPING.get(type_str.lower(), String(255))

        # Gérer les enums
        if type_str.startswith("enum"):
            sql_type = String(50)

        # Gérer les liens (foreign keys)
        if type_str.startswith("lien"):
            sql_type = UUID(as_uuid=True)

        # Si le champ est encrypté, utiliser Text pour stocker le ciphertext
        # (le ciphertext est plus long que le plaintext)
        if is_encrypted:
            sql_type = Text

        return Column(
            nom,
            sql_type,
            nullable=nullable,
            default=default
        )

    @classmethod
    def register_encrypted_fields(cls, module_name: str, fields: List[str]):
        """Enregistre les champs encryptés d'un module."""
        cls._encrypted_fields[module_name] = fields
        logger.debug("encrypted_fields_registered", module=module_name, fields=fields)

    @classmethod
    def get_encrypted_fields(cls, module_name: str) -> List[str]:
        """Retourne la liste des champs encryptés d'un module."""
        return cls._encrypted_fields.get(module_name, [])

    # =========================================================================
    # Requêtes avec isolation tenant
    # =========================================================================
    @classmethod
    def query(
        cls,
        table_name: str,
        tenant_id: PyUUID,
        filters: Optional[Dict] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        include_archived: bool = False,
        archived_only: bool = False
    ) -> List[Dict]:
        """
        Execute une requete SELECT avec isolation tenant OBLIGATOIRE.

        Args:
            table_name: Nom de la table
            tenant_id: ID du tenant (isolation obligatoire)
            filters: Filtres additionnels
            order_by: Ordre de tri
            limit: Limite de resultats
            offset: Offset pour pagination
            include_archived: Si True, inclut les enregistrements archives
            archived_only: Si True, retourne UNIQUEMENT les enregistrements archives
        """

        with cls.get_session() as session:
            # Construire la requête
            query = f'SELECT * FROM azalplus.{table_name} WHERE tenant_id = :tenant_id AND deleted_at IS NULL'
            params = {"tenant_id": str(tenant_id)}

            # Gestion de l'archivage
            if archived_only:
                query += " AND archived = true"
            elif not include_archived:
                query += " AND (archived = false OR archived IS NULL)"

            # Filtres additionnels
            if filters:
                for key, value in filters.items():
                    query += f" AND {key} = :{key}"
                    params[key] = value

            # Ordre
            if order_by:
                query += f" ORDER BY {order_by}"
            else:
                query += " ORDER BY created_at DESC"

            # Pagination
            if limit:
                query += f" LIMIT {limit}"
            if offset:
                query += f" OFFSET {offset}"

            result = session.execute(text(query), params)
            rows = [dict(row._mapping) for row in result]

            # Décrypter les champs sensibles
            encrypted_fields = cls.get_encrypted_fields(table_name)
            if encrypted_fields:
                from .encryption import EncryptionMiddleware
                rows = [
                    EncryptionMiddleware.decrypt_dict(row, encrypted_fields, tenant_id)
                    for row in rows
                ]

            return rows

    @classmethod
    def get(
        cls,
        table_name: str,
        tenant_id: PyUUID,
        record_id: PyUUID
    ) -> Optional[Dict]:
        """Alias pour get_by_id - Récupère un enregistrement par ID."""
        return cls.get_by_id(table_name, tenant_id, record_id)

    @classmethod
    def get_by_id(
        cls,
        table_name: str,
        tenant_id: PyUUID,
        record_id: PyUUID
    ) -> Optional[Dict]:
        """Récupère un enregistrement par ID avec isolation tenant et décryption."""

        with cls.get_session() as session:
            query = text(f'''
                SELECT * FROM azalplus.{table_name}
                WHERE id = :id AND tenant_id = :tenant_id AND deleted_at IS NULL
            ''')
            result = session.execute(query, {
                "id": str(record_id),
                "tenant_id": str(tenant_id)
            })
            row = result.fetchone()

            if not row:
                return None

            result_dict = dict(row._mapping)

            # Décrypter les champs sensibles
            encrypted_fields = cls.get_encrypted_fields(table_name)
            if encrypted_fields:
                from .encryption import EncryptionMiddleware
                result_dict = EncryptionMiddleware.decrypt_dict(result_dict, encrypted_fields, tenant_id)

            return result_dict

    @classmethod
    def insert(
        cls,
        table_name: str,
        tenant_id: PyUUID,
        data: Dict,
        user_id: Optional[PyUUID] = None
    ) -> Dict:
        """Insère un enregistrement avec tenant_id automatique et encryption."""
        from .encryption import FieldEncryption, EncryptionMiddleware

        record_id = uuid4()
        data["id"] = str(record_id)
        data["tenant_id"] = str(tenant_id)

        if user_id:
            data["created_by"] = str(user_id)

        # Encrypter les champs sensibles
        encrypted_fields = cls.get_encrypted_fields(table_name)
        if encrypted_fields:
            data = EncryptionMiddleware.encrypt_dict(data, encrypted_fields, tenant_id)

        # Sérialiser les valeurs dict/list en JSON pour JSONB PostgreSQL
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                data[key] = json.dumps(value)

        columns = ", ".join(data.keys())
        placeholders = ", ".join(f":{k}" for k in data.keys())

        with cls.get_session() as session:
            query = text(f'''
                INSERT INTO azalplus.{table_name} ({columns})
                VALUES ({placeholders})
                RETURNING *
            ''')
            result = session.execute(query, data)
            session.commit()
            row = result.fetchone()
            result_dict = dict(row._mapping)

            # Décrypter pour le retour
            if encrypted_fields:
                result_dict = EncryptionMiddleware.decrypt_dict(result_dict, encrypted_fields, tenant_id)

            return result_dict

    @classmethod
    def update(
        cls,
        table_name: str,
        tenant_id: PyUUID,
        record_id: PyUUID,
        data: Dict,
        user_id: Optional[PyUUID] = None
    ) -> Optional[Dict]:
        """Met à jour un enregistrement avec vérification tenant et encryption."""
        from .encryption import EncryptionMiddleware

        if user_id:
            data["updated_by"] = str(user_id)

        # Encrypter les champs sensibles
        encrypted_fields = cls.get_encrypted_fields(table_name)
        if encrypted_fields:
            data = EncryptionMiddleware.encrypt_dict(data, encrypted_fields, tenant_id)

        # Sérialiser les valeurs dict/list en JSON pour JSONB PostgreSQL
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                data[key] = json.dumps(value)

        set_clause = ", ".join(f"{k} = :{k}" for k in data.keys())

        with cls.get_session() as session:
            query = text(f'''
                UPDATE azalplus.{table_name}
                SET {set_clause}, updated_at = NOW()
                WHERE id = :id AND tenant_id = :tenant_id AND deleted_at IS NULL
                RETURNING *
            ''')
            data["id"] = str(record_id)
            data["tenant_id"] = str(tenant_id)
            result = session.execute(query, data)
            session.commit()
            row = result.fetchone()

            if not row:
                return None

            result_dict = dict(row._mapping)

            # Décrypter pour le retour
            if encrypted_fields:
                result_dict = EncryptionMiddleware.decrypt_dict(result_dict, encrypted_fields, tenant_id)

            return result_dict

    @classmethod
    def soft_delete(
        cls,
        table_name: str,
        tenant_id: PyUUID,
        record_id: PyUUID
    ) -> bool:
        """Suppression douce avec vérification tenant."""

        with cls.get_session() as session:
            query = text(f'''
                UPDATE azalplus.{table_name}
                SET deleted_at = NOW()
                WHERE id = :id AND tenant_id = :tenant_id AND deleted_at IS NULL
            ''')
            result = session.execute(query, {
                "id": str(record_id),
                "tenant_id": str(tenant_id)
            })
            session.commit()
            return result.rowcount > 0

    @classmethod
    def count(
        cls,
        table_name: str,
        tenant_id: PyUUID,
        filters: Optional[Dict] = None,
        include_archived: bool = False
    ) -> int:
        """
        Compte les enregistrements d'une table avec isolation tenant.

        Args:
            table_name: Nom de la table
            tenant_id: ID du tenant (isolation obligatoire)
            filters: Filtres additionnels
            include_archived: Si True, inclut les enregistrements archives

        Returns:
            Nombre d'enregistrements
        """
        with cls.get_session() as session:
            query = f'SELECT COUNT(*) FROM azalplus.{table_name} WHERE tenant_id = :tenant_id AND deleted_at IS NULL'
            params = {"tenant_id": str(tenant_id)}

            # Gestion de l'archivage
            if not include_archived:
                query += " AND (archived = false OR archived IS NULL)"

            # Filtres additionnels
            if filters:
                for key, value in filters.items():
                    query += f" AND {key} = :{key}"
                    params[key] = value

            result = session.execute(text(query), params)
            return result.scalar() or 0

    @classmethod
    def search_table(
        cls,
        table_name: str,
        tenant_id: PyUUID,
        search_query: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Recherche dans une table specifique avec ILIKE.

        Args:
            table_name: Nom de la table
            tenant_id: ID du tenant
            search_query: Terme de recherche
            limit: Nombre max de resultats

        Returns:
            Liste des enregistrements correspondants
        """
        if not search_query or len(search_query) < 2:
            return []

        search_term = f"%{search_query.lower()}%"
        default_fields = ["nom", "name", "reference", "email", "numero", "titre", "title", "description", "code"]

        with cls.get_session() as session:
            try:
                # Construire la clause WHERE avec ILIKE pour chaque champ
                where_clauses = []
                for field in default_fields:
                    where_clauses.append(f"COALESCE(CAST({field} AS TEXT), '') ILIKE :search_term")

                search_condition = " OR ".join(where_clauses)

                sql = f'''
                    SELECT * FROM azalplus.{table_name}
                    WHERE tenant_id = :tenant_id
                    AND deleted_at IS NULL
                    AND (archived = false OR archived IS NULL)
                    AND ({search_condition})
                    ORDER BY created_at DESC
                    LIMIT :limit
                '''

                result = session.execute(
                    text(sql),
                    {
                        "tenant_id": str(tenant_id),
                        "search_term": search_term,
                        "limit": limit
                    }
                )

                return [dict(row._mapping) for row in result]

            except Exception as e:
                logger.warning("search_table_error", table=table_name, error=str(e))
                return []

    @classmethod
    def search(
        cls,
        table_name: str,
        tenant_id: PyUUID,
        query: str,
        fields: Optional[List[str]] = None,
        limit: int = 20
    ) -> List[Dict]:
        """
        Recherche dans une table avec champs personnalisés.

        Args:
            table_name: Nom de la table
            tenant_id: ID du tenant
            query: Terme de recherche
            fields: Liste des champs à chercher (défaut: nom, name, code, reference)
            limit: Nombre max de résultats

        Returns:
            Liste des enregistrements correspondants
        """
        if not query or len(query) < 2:
            return []

        search_term = f"%{query.lower()}%"
        search_fields = fields or ["nom", "name", "code", "reference", "email", "titre"]

        with cls.get_session() as session:
            try:
                # Construire la clause WHERE avec ILIKE pour chaque champ
                where_clauses = []
                for field in search_fields:
                    where_clauses.append(f"COALESCE(CAST({field} AS TEXT), '') ILIKE :search_term")

                search_condition = " OR ".join(where_clauses)

                sql = f'''
                    SELECT * FROM azalplus.{table_name}
                    WHERE tenant_id = :tenant_id
                    AND deleted_at IS NULL
                    AND ({search_condition})
                    ORDER BY created_at DESC
                    LIMIT :limit
                '''

                result = session.execute(
                    text(sql),
                    {
                        "tenant_id": str(tenant_id),
                        "search_term": search_term,
                        "limit": limit
                    }
                )

                return [dict(row._mapping) for row in result]

            except Exception as e:
                logger.warning("search_error", table=table_name, error=str(e))
                return []

    # =========================================================================
    # Séquences (numérotation auto)
    # =========================================================================
    @classmethod
    def next_sequence(cls, tenant_id: PyUUID, entite: str) -> str:
        """Génère le prochain numéro de séquence."""

        with cls.get_session() as session:
            result = session.execute(
                text("SELECT azalplus.next_sequence(:tenant_id, :entite)"),
                {"tenant_id": str(tenant_id), "entite": entite}
            )
            return result.scalar()

    # =========================================================================
    # Recherche globale
    # =========================================================================
    @classmethod
    def global_search(
        cls,
        tenant_id: PyUUID,
        query: str,
        tables: List[str],
        search_fields: Optional[Dict[str, List[str]]] = None,
        limit_per_table: int = 10,
        include_archived: bool = False
    ) -> Dict[str, List[Dict]]:
        """
        Recherche globale sur plusieurs tables.

        Args:
            tenant_id: ID du tenant (isolation obligatoire)
            query: Terme de recherche
            tables: Liste des tables a parcourir
            search_fields: Champs a chercher par table (optionnel, defaut: nom, reference, email)
            limit_per_table: Limite de resultats par table
            include_archived: Si True, inclut les enregistrements archives

        Returns:
            Dict avec resultats groupes par table
        """
        if not query or len(query) < 2:
            return {}

        results = {}
        search_term = f"%{query.lower()}%"

        # Champs par defaut a chercher
        default_fields = ["nom", "reference", "raison_sociale", "email", "numero", "titre", "description"]

        # Condition d'archivage
        archive_condition = "" if include_archived else "AND (archived = false OR archived IS NULL)"

        with cls.get_session() as session:
            for table_name in tables:
                try:
                    # Determiner les champs a chercher pour cette table
                    if search_fields and table_name in search_fields:
                        fields_to_search = search_fields[table_name]
                    else:
                        fields_to_search = default_fields

                    # Construire la clause WHERE avec ILIKE pour chaque champ
                    where_clauses = []
                    for field in fields_to_search:
                        where_clauses.append(f"COALESCE(CAST({field} AS TEXT), '') ILIKE :search_term")

                    if not where_clauses:
                        continue

                    search_condition = " OR ".join(where_clauses)

                    sql = f'''
                        SELECT * FROM azalplus.{table_name}
                        WHERE tenant_id = :tenant_id
                        AND deleted_at IS NULL
                        {archive_condition}
                        AND ({search_condition})
                        ORDER BY created_at DESC
                        LIMIT :limit
                    '''

                    result = session.execute(
                        text(sql),
                        {
                            "tenant_id": str(tenant_id),
                            "search_term": search_term,
                            "limit": limit_per_table
                        }
                    )

                    rows = [dict(row._mapping) for row in result]
                    if rows:
                        results[table_name] = rows

                except Exception as e:
                    # Table n'existe pas ou erreur SQL - on continue
                    logger.debug("search_table_error", table=table_name, error=str(e))
                    continue

        return results

    @classmethod
    def search_table(
        cls,
        table_name: str,
        tenant_id: PyUUID,
        query: str,
        search_fields: Optional[List[str]] = None,
        limit: int = 50,
        include_archived: bool = False
    ) -> List[Dict]:
        """
        Recherche dans une table specifique.

        Args:
            table_name: Nom de la table
            tenant_id: ID du tenant (isolation obligatoire)
            query: Terme de recherche
            search_fields: Champs a chercher (optionnel)
            limit: Limite de resultats
            include_archived: Si True, inclut les enregistrements archives

        Returns:
            Liste des resultats
        """
        if not query or len(query) < 2:
            return []

        search_term = f"%{query.lower()}%"

        # Champs par defaut a chercher
        if not search_fields:
            search_fields = ["nom", "reference", "raison_sociale", "email", "numero", "titre", "description", "prenom"]

        # Condition d'archivage
        archive_condition = "" if include_archived else "AND (archived = false OR archived IS NULL)"

        with cls.get_session() as session:
            try:
                # Construire la clause WHERE avec ILIKE pour chaque champ
                where_clauses = []
                for field in search_fields:
                    where_clauses.append(f"COALESCE(CAST({field} AS TEXT), '') ILIKE :search_term")

                if not where_clauses:
                    return []

                search_condition = " OR ".join(where_clauses)

                sql = f'''
                    SELECT * FROM azalplus.{table_name}
                    WHERE tenant_id = :tenant_id
                    AND deleted_at IS NULL
                    {archive_condition}
                    AND ({search_condition})
                    ORDER BY created_at DESC
                    LIMIT :limit
                '''

                result = session.execute(
                    text(sql),
                    {
                        "tenant_id": str(tenant_id),
                        "search_term": search_term,
                        "limit": limit
                    }
                )

                return [dict(row._mapping) for row in result]

            except Exception as e:
                logger.debug("search_table_error", table=table_name, error=str(e))
                return []

    # =========================================================================
    # Gestion des champs personnalises (Custom Fields)
    # =========================================================================
    @classmethod
    def update_custom_fields(
        cls,
        table_name: str,
        tenant_id: PyUUID,
        record_id: PyUUID,
        custom_fields: Dict[str, Any],
        user_id: Optional[PyUUID] = None
    ) -> Optional[Dict]:
        """
        Met a jour les champs personnalises d'un enregistrement.

        Args:
            table_name: Nom de la table
            tenant_id: ID du tenant (isolation obligatoire)
            record_id: ID de l'enregistrement
            custom_fields: Dictionnaire des champs personnalises
            user_id: ID de l'utilisateur effectuant la modification

        Returns:
            Enregistrement mis a jour ou None
        """
        with cls.get_session() as session:
            # Fusionner avec les champs existants
            sql = text(f'''
                UPDATE azalplus.{table_name}
                SET custom_fields = COALESCE(custom_fields, '{{}}'::jsonb) || :custom_fields::jsonb,
                    updated_at = NOW(),
                    updated_by = :user_id
                WHERE id = :id AND tenant_id = :tenant_id AND deleted_at IS NULL
                RETURNING *
            ''')

            import json
            result = session.execute(sql, {
                "id": str(record_id),
                "tenant_id": str(tenant_id),
                "custom_fields": json.dumps(custom_fields),
                "user_id": str(user_id) if user_id else None
            })
            session.commit()
            row = result.fetchone()
            return dict(row._mapping) if row else None

    @classmethod
    def get_custom_field_value(
        cls,
        table_name: str,
        tenant_id: PyUUID,
        record_id: PyUUID,
        field_name: str
    ) -> Any:
        """
        Recupere la valeur d'un champ personnalise specifique.

        Args:
            table_name: Nom de la table
            tenant_id: ID du tenant
            record_id: ID de l'enregistrement
            field_name: Nom du champ personnalise

        Returns:
            Valeur du champ ou None
        """
        with cls.get_session() as session:
            sql = text(f'''
                SELECT custom_fields->>:field_name as value
                FROM azalplus.{table_name}
                WHERE id = :id AND tenant_id = :tenant_id AND deleted_at IS NULL
            ''')

            result = session.execute(sql, {
                "id": str(record_id),
                "tenant_id": str(tenant_id),
                "field_name": field_name
            })
            row = result.fetchone()
            return row.value if row else None

    @classmethod
    def search_by_custom_field(
        cls,
        table_name: str,
        tenant_id: PyUUID,
        field_name: str,
        value: Any,
        limit: int = 50
    ) -> List[Dict]:
        """
        Recherche des enregistrements par valeur de champ personnalise.

        Args:
            table_name: Nom de la table
            tenant_id: ID du tenant
            field_name: Nom du champ personnalise
            value: Valeur recherchee
            limit: Limite de resultats

        Returns:
            Liste des enregistrements correspondants
        """
        with cls.get_session() as session:
            sql = text(f'''
                SELECT * FROM azalplus.{table_name}
                WHERE tenant_id = :tenant_id
                AND deleted_at IS NULL
                AND custom_fields->>:field_name = :value
                ORDER BY created_at DESC
                LIMIT :limit
            ''')

            result = session.execute(sql, {
                "tenant_id": str(tenant_id),
                "field_name": field_name,
                "value": str(value),
                "limit": limit
            })

            return [dict(row._mapping) for row in result]

    @classmethod
    def add_custom_fields_column(cls, table_name: str) -> bool:
        """
        Ajoute la colonne custom_fields a une table existante si elle n'existe pas.

        Args:
            table_name: Nom de la table

        Returns:
            True si la colonne a ete ajoutee, False sinon
        """
        with cls.get_session() as session:
            try:
                # Verifier si la colonne existe
                check_sql = text('''
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'azalplus'
                    AND table_name = :table_name
                    AND column_name = 'custom_fields'
                ''')
                result = session.execute(check_sql, {"table_name": table_name.lower()})

                if result.fetchone():
                    return False  # La colonne existe deja

                # Ajouter la colonne
                alter_sql = text(f'''
                    ALTER TABLE azalplus.{table_name}
                    ADD COLUMN IF NOT EXISTS custom_fields JSONB DEFAULT '{{}}'::jsonb
                ''')
                session.execute(alter_sql)
                session.commit()

                logger.info("custom_fields_column_added", table=table_name)
                return True

            except Exception as e:
                logger.error("custom_fields_column_error", table=table_name, error=str(e))
                return False

    @classmethod
    def migrate_custom_fields_to_all_tables(cls) -> Dict[str, bool]:
        """
        Ajoute la colonne custom_fields a toutes les tables du schema azalplus.

        Returns:
            Dictionnaire {table_name: success}
        """
        results = {}

        with cls.get_session() as session:
            # Lister toutes les tables
            sql = text('''
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'azalplus'
                AND table_type = 'BASE TABLE'
            ''')
            result = session.execute(sql)
            tables = [row.table_name for row in result]

        for table_name in tables:
            results[table_name] = cls.add_custom_fields_column(table_name)

        return results
