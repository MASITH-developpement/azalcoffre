# =============================================================================
# AZALPLUS - Sequence Service
# =============================================================================
"""
Service de gestion des sequences de numerotation automatique.

Fonctionnalites:
- Generation thread-safe de numeros uniques par tenant
- Formats personnalisables (prefixe, date, compteur)
- Reset automatique (jamais, annuel, mensuel)
- Verrouillage pour eviter les doublons

IMPORTANT: Isolation multi-tenant obligatoire sur chaque operation.
"""

from datetime import datetime, date
from typing import Dict, Any, Optional, List
from uuid import UUID
import threading
import asyncio
import yaml
from pathlib import Path
import structlog
from sqlalchemy import text

from .db import Database
from .config import settings

logger = structlog.get_logger()

# =============================================================================
# Verrou global pour la thread-safety
# =============================================================================
_sequence_locks: Dict[str, threading.Lock] = {}
_lock_manager = threading.Lock()


def _get_lock(tenant_id: UUID, module: str) -> threading.Lock:
    """Obtient ou cree un verrou pour un tenant/module."""
    key = f"{tenant_id}:{module}"
    with _lock_manager:
        if key not in _sequence_locks:
            _sequence_locks[key] = threading.Lock()
        return _sequence_locks[key]


# =============================================================================
# Classe de configuration de sequence
# =============================================================================
class SequenceConfig:
    """Configuration d'une sequence de numerotation."""

    def __init__(self, data: Dict[str, Any]):
        self.nom_affichage = data.get("nom_affichage", "")
        self.prefixe = data.get("prefixe", "")
        self.suffixe = data.get("suffixe", "")
        self.format = data.get("format", "{PREFIXE}{SEP}{0000}")
        self.exemple = data.get("exemple", "")
        self.separateur = data.get("separateur", "-")
        self.padding = data.get("padding", 4)
        self.format_date = data.get("format_date")  # YYYY, YYMM, YYMMDD, ou None
        self.reset = data.get("reset", "jamais")  # jamais, annuel, mensuel
        self.description = data.get("description", "")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nom_affichage": self.nom_affichage,
            "prefixe": self.prefixe,
            "suffixe": self.suffixe,
            "format": self.format,
            "exemple": self.exemple,
            "separateur": self.separateur,
            "padding": self.padding,
            "format_date": self.format_date,
            "reset": self.reset,
            "description": self.description,
        }


# =============================================================================
# Service de Sequences
# =============================================================================
class SequenceService:
    """
    Service de gestion des sequences de numerotation.

    Toutes les operations sont isolees par tenant_id (OBLIGATOIRE).
    """

    _default_config: Dict[str, SequenceConfig] = {}
    _loaded = False

    @classmethod
    def load_defaults(cls) -> None:
        """Charge la configuration par defaut depuis sequences.yml."""
        if cls._loaded:
            return

        sequences_path = Path(__file__).parent.parent / "modules" / "sequences.yml"

        if not sequences_path.exists():
            logger.warning("sequences_config_not_found", path=str(sequences_path))
            cls._loaded = True
            return

        try:
            with open(sequences_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            sequences = data.get("sequences", {})
            for module, config in sequences.items():
                cls._default_config[module] = SequenceConfig(config)

            logger.info("sequences_loaded", count=len(cls._default_config))
            cls._loaded = True

        except Exception as e:
            logger.error("sequences_load_error", error=str(e))
            cls._loaded = True

    @classmethod
    def get_default_config(cls, module: str) -> Optional[SequenceConfig]:
        """Retourne la configuration par defaut d'une sequence."""
        cls.load_defaults()
        return cls._default_config.get(module)

    @classmethod
    def list_available_sequences(cls) -> List[str]:
        """Liste toutes les sequences disponibles."""
        cls.load_defaults()
        return list(cls._default_config.keys())

    @classmethod
    def get_all_configs(cls) -> Dict[str, Dict[str, Any]]:
        """Retourne toutes les configurations par defaut."""
        cls.load_defaults()
        return {k: v.to_dict() for k, v in cls._default_config.items()}

    # =========================================================================
    # Operations CRUD pour les configurations tenant
    # =========================================================================

    @classmethod
    def get_tenant_config(cls, tenant_id: UUID, module: str) -> Optional[Dict[str, Any]]:
        """
        Recupere la configuration de sequence pour un tenant.

        Si le tenant n'a pas de config personnalisee, retourne la config par defaut.
        """
        with Database.get_session() as session:
            result = session.execute(
                text("""
                    SELECT config FROM azalplus.sequence_configs
                    WHERE tenant_id = :tenant_id AND module = :module
                """),
                {"tenant_id": str(tenant_id), "module": module}
            )
            row = result.fetchone()

            if row:
                return row[0]  # JSONB retourne directement un dict

        # Fallback sur la config par defaut
        default = cls.get_default_config(module)
        return default.to_dict() if default else None

    @classmethod
    def save_tenant_config(
        cls,
        tenant_id: UUID,
        module: str,
        config: Dict[str, Any],
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Sauvegarde la configuration de sequence pour un tenant.
        """
        with Database.get_session() as session:
            # Upsert (INSERT ... ON CONFLICT)
            session.execute(
                text("""
                    INSERT INTO azalplus.sequence_configs (tenant_id, module, config, updated_by, updated_at)
                    VALUES (:tenant_id, :module, :config::jsonb, :user_id, NOW())
                    ON CONFLICT (tenant_id, module)
                    DO UPDATE SET config = :config::jsonb, updated_by = :user_id, updated_at = NOW()
                """),
                {
                    "tenant_id": str(tenant_id),
                    "module": module,
                    "config": yaml.dump(config),  # Convertir en string JSONB
                    "user_id": str(user_id) if user_id else None
                }
            )
            session.commit()

        logger.info(
            "sequence_config_saved",
            tenant_id=str(tenant_id),
            module=module
        )
        return config

    @classmethod
    def get_all_tenant_configs(cls, tenant_id: UUID) -> Dict[str, Dict[str, Any]]:
        """
        Recupere toutes les configurations de sequence pour un tenant.

        Fusionne les configs personnalisees avec les configs par defaut.
        """
        cls.load_defaults()

        # Commencer avec les configs par defaut
        result = {k: v.to_dict() for k, v in cls._default_config.items()}

        # Surcharger avec les configs tenant
        with Database.get_session() as session:
            rows = session.execute(
                text("""
                    SELECT module, config FROM azalplus.sequence_configs
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": str(tenant_id)}
            )
            for row in rows:
                module, config = row
                if config:
                    result[module] = config

        return result

    # =========================================================================
    # Generation de numeros
    # =========================================================================

    @classmethod
    def get_next_number(cls, tenant_id: UUID, module: str) -> str:
        """
        Genere le prochain numero de sequence pour un tenant/module.

        Cette methode est THREAD-SAFE et garantit l'unicite des numeros.

        Args:
            tenant_id: ID du tenant (OBLIGATOIRE pour isolation)
            module: Type de document (devis, facture, intervention, etc.)

        Returns:
            Le numero formate (ex: "DEV-2026-0001")
        """
        lock = _get_lock(tenant_id, module)

        with lock:
            # Recuperer la config
            config = cls.get_tenant_config(tenant_id, module)
            if not config:
                # Generer un numero simple si pas de config
                return cls._generate_fallback_number(tenant_id, module)

            # Determiner la periode de reset
            now = datetime.now()
            reset_key = cls._get_reset_key(config.get("reset", "jamais"), now)

            # Recuperer et incrementer le compteur
            counter = cls._get_and_increment_counter(tenant_id, module, reset_key)

            # Formater le numero
            number = cls._format_number(config, counter, now)

            logger.debug(
                "sequence_generated",
                tenant_id=str(tenant_id),
                module=module,
                number=number,
                counter=counter
            )

            return number

    @classmethod
    def _get_reset_key(cls, reset_type: str, dt: datetime) -> str:
        """Calcule la cle de reset en fonction du type."""
        if reset_type == "annuel":
            return str(dt.year)
        elif reset_type == "mensuel":
            return f"{dt.year}-{dt.month:02d}"
        else:  # jamais
            return "all"

    @classmethod
    def _get_and_increment_counter(
        cls,
        tenant_id: UUID,
        module: str,
        reset_key: str
    ) -> int:
        """
        Recupere et incremente le compteur de maniere atomique.

        Utilise SELECT FOR UPDATE pour le verrouillage.
        """
        with Database.get_session() as session:
            # Tenter de mettre a jour le compteur existant
            result = session.execute(
                text("""
                    UPDATE azalplus.sequence_counters
                    SET counter = counter + 1, updated_at = NOW()
                    WHERE tenant_id = :tenant_id AND module = :module AND reset_key = :reset_key
                    RETURNING counter
                """),
                {
                    "tenant_id": str(tenant_id),
                    "module": module,
                    "reset_key": reset_key
                }
            )
            row = result.fetchone()

            if row:
                session.commit()
                return row[0]

            # Creer un nouveau compteur si n'existe pas
            try:
                session.execute(
                    text("""
                        INSERT INTO azalplus.sequence_counters (tenant_id, module, reset_key, counter)
                        VALUES (:tenant_id, :module, :reset_key, 1)
                    """),
                    {
                        "tenant_id": str(tenant_id),
                        "module": module,
                        "reset_key": reset_key
                    }
                )
                session.commit()
                return 1
            except Exception:
                # Conflit d'insertion - reessayer l'update
                session.rollback()
                result = session.execute(
                    text("""
                        UPDATE azalplus.sequence_counters
                        SET counter = counter + 1, updated_at = NOW()
                        WHERE tenant_id = :tenant_id AND module = :module AND reset_key = :reset_key
                        RETURNING counter
                    """),
                    {
                        "tenant_id": str(tenant_id),
                        "module": module,
                        "reset_key": reset_key
                    }
                )
                row = result.fetchone()
                session.commit()
                return row[0] if row else 1

    @classmethod
    def _format_number(
        cls,
        config: Dict[str, Any],
        counter: int,
        dt: datetime
    ) -> str:
        """
        Formate le numero selon la configuration.

        Variables supportees:
        - {PREFIXE}: Prefixe de la sequence
        - {SUFFIXE}: Suffixe de la sequence
        - {SEP}: Separateur
        - {YYYY}: Annee complete
        - {YY}: Annee courte
        - {MM}: Mois
        - {DD}: Jour
        - {0000}: Compteur avec padding
        """
        format_str = config.get("format", "{PREFIXE}{SEP}{0000}")
        prefixe = config.get("prefixe", "")
        suffixe = config.get("suffixe", "")
        separateur = config.get("separateur", "-")
        padding = config.get("padding", 4)

        # Construire le numero du compteur avec padding
        counter_str = str(counter).zfill(padding)

        # Pattern de remplacement pour le compteur (detecte le nombre de 0)
        import re
        counter_pattern = re.compile(r'\{0+\}')

        def replace_counter(match):
            # Utilise le nombre de 0 dans le pattern pour le padding
            zeros = len(match.group()) - 2  # Enlever { et }
            return str(counter).zfill(zeros)

        # Remplacer les variables
        result = format_str
        result = result.replace("{PREFIXE}", prefixe)
        result = result.replace("{SUFFIXE}", suffixe)
        result = result.replace("{SEP}", separateur)
        result = result.replace("{YYYY}", str(dt.year))
        result = result.replace("{YY}", str(dt.year)[2:])
        result = result.replace("{MM}", f"{dt.month:02d}")
        result = result.replace("{DD}", f"{dt.day:02d}")
        result = counter_pattern.sub(replace_counter, result)

        # Nettoyer les separateurs doubles
        while separateur + separateur in result:
            result = result.replace(separateur + separateur, separateur)

        # Nettoyer les separateurs en debut/fin
        result = result.strip(separateur)

        return result

    @classmethod
    def _generate_fallback_number(cls, tenant_id: UUID, module: str) -> str:
        """Genere un numero simple si pas de configuration."""
        counter = cls._get_and_increment_counter(tenant_id, module, "all")
        prefix = module.upper()[:3]
        return f"{prefix}-{counter:04d}"

    @classmethod
    def preview_number(
        cls,
        config: Dict[str, Any],
        counter: int = 1,
        dt: Optional[datetime] = None
    ) -> str:
        """
        Previsualise un numero sans l'incrementer.

        Utile pour l'interface de configuration.
        """
        if dt is None:
            dt = datetime.now()
        return cls._format_number(config, counter, dt)

    # =========================================================================
    # Reset des compteurs
    # =========================================================================

    @classmethod
    async def reset_counters(cls, reset_type: str = "all") -> int:
        """
        Reinitialise les compteurs selon le type de reset.

        Cette methode est destinee aux taches planifiees (cron).

        Args:
            reset_type: "annuel", "mensuel", ou "all"

        Returns:
            Nombre de compteurs reinitialises
        """
        now = datetime.now()

        with Database.get_session() as session:
            if reset_type == "annuel":
                # Supprimer les compteurs de l'annee precedente
                old_key = str(now.year - 1)
                result = session.execute(
                    text("""
                        DELETE FROM azalplus.sequence_counters
                        WHERE reset_key = :old_key
                    """),
                    {"old_key": old_key}
                )

            elif reset_type == "mensuel":
                # Supprimer les compteurs du mois precedent
                prev_month = now.month - 1 if now.month > 1 else 12
                prev_year = now.year if now.month > 1 else now.year - 1
                old_key = f"{prev_year}-{prev_month:02d}"
                result = session.execute(
                    text("""
                        DELETE FROM azalplus.sequence_counters
                        WHERE reset_key = :old_key
                    """),
                    {"old_key": old_key}
                )

            else:
                # Reset tout (pour debug/maintenance)
                result = session.execute(
                    text("DELETE FROM azalplus.sequence_counters")
                )

            session.commit()
            count = result.rowcount

        logger.info(
            "sequence_counters_reset",
            reset_type=reset_type,
            count=count
        )

        return count

    @classmethod
    def get_current_counter(
        cls,
        tenant_id: UUID,
        module: str
    ) -> Optional[int]:
        """
        Retourne le compteur actuel sans l'incrementer.

        Utile pour l'affichage dans l'interface.
        """
        cls.load_defaults()

        # Determiner la periode de reset
        config = cls.get_tenant_config(tenant_id, module)
        reset_type = config.get("reset", "jamais") if config else "jamais"
        reset_key = cls._get_reset_key(reset_type, datetime.now())

        with Database.get_session() as session:
            result = session.execute(
                text("""
                    SELECT counter FROM azalplus.sequence_counters
                    WHERE tenant_id = :tenant_id AND module = :module AND reset_key = :reset_key
                """),
                {
                    "tenant_id": str(tenant_id),
                    "module": module,
                    "reset_key": reset_key
                }
            )
            row = result.fetchone()
            return row[0] if row else 0


# =============================================================================
# SQL pour creer les tables necessaires
# =============================================================================
CREATE_TABLES_SQL = """
-- Table des configurations de sequence par tenant
CREATE TABLE IF NOT EXISTS azalplus.sequence_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    module VARCHAR(50) NOT NULL,
    config JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by UUID,
    UNIQUE(tenant_id, module)
);

CREATE INDEX IF NOT EXISTS idx_sequence_configs_tenant ON azalplus.sequence_configs(tenant_id);

-- Table des compteurs de sequence
CREATE TABLE IF NOT EXISTS azalplus.sequence_counters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    module VARCHAR(50) NOT NULL,
    reset_key VARCHAR(20) NOT NULL DEFAULT 'all',
    counter INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(tenant_id, module, reset_key)
);

CREATE INDEX IF NOT EXISTS idx_sequence_counters_tenant ON azalplus.sequence_counters(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sequence_counters_lookup ON azalplus.sequence_counters(tenant_id, module, reset_key);
"""


async def init_sequence_tables():
    """Initialise les tables de sequence si elles n'existent pas."""
    with Database.get_session() as session:
        session.execute(text(CREATE_TABLES_SQL))
        session.commit()
    logger.info("sequence_tables_initialized")
