# =============================================================================
# AZALPLUS - Archive Service
# =============================================================================
"""
Service d'archivage des donnees.
- Archivage/desarchivage d'enregistrements
- Regles d'archivage automatique par module
- Statistiques d'archivage
- Nettoyage et conformite RGPD
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, date, timedelta
from pydantic import BaseModel
import structlog

from .db import Database
from .tenant import get_current_tenant, get_current_user_id
from .auth import require_auth
from .audit import AuditLogger, AuditContext

logger = structlog.get_logger()

# =============================================================================
# Router
# =============================================================================
archive_router = APIRouter()

# =============================================================================
# Schemas
# =============================================================================
class ArchiveRequest(BaseModel):
    """Requete d'archivage."""
    raison: Optional[str] = None

class ArchiveStats(BaseModel):
    """Statistiques d'archivage."""
    total_archived: int
    total_active: int
    storage_archived_kb: float
    storage_active_kb: float
    modules: Dict[str, Dict[str, int]]

class ArchiveSuggestion(BaseModel):
    """Suggestion d'archivage."""
    module: str
    record_id: str
    record_name: str
    reason: str
    age_days: int

# =============================================================================
# Archive Rules Configuration
# =============================================================================
ARCHIVE_RULES = {
    "factures": {
        "condition": "status = 'PAID' AND date < :archive_date",
        "years": 3,
        "description": "Factures payees depuis plus de 3 ans"
    },
    "devis": {
        "condition": "status IN ('REFUSE', 'EXPIRE', 'CANCELLED') AND created_at < :archive_date",
        "years": 1,
        "description": "Devis refuses/expires depuis plus d'1 an"
    },
    "clients": {
        "condition": "last_order_date < :archive_date OR (last_order_date IS NULL AND created_at < :archive_date)",
        "years": 2,
        "description": "Clients sans activite depuis plus de 2 ans"
    },
    "interventions": {
        "condition": "statut = 'TERMINEE' AND created_at < :archive_date",
        "years": 2,
        "description": "Interventions terminees depuis plus de 2 ans"
    },
    "paiements": {
        "condition": "status = 'VALIDATED' AND date < :archive_date",
        "years": 3,
        "description": "Paiements valides depuis plus de 3 ans"
    }
}

# =============================================================================
# Archive Service
# =============================================================================
class ArchiveService:
    """Service d'archivage des enregistrements."""

    @staticmethod
    def archive_record(
        table_name: str,
        tenant_id: UUID,
        record_id: UUID,
        user_id: UUID,
        raison: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Archive un enregistrement.

        Args:
            table_name: Nom de la table
            tenant_id: ID du tenant (isolation OBLIGATOIRE)
            record_id: ID de l'enregistrement
            user_id: ID de l'utilisateur qui archive
            raison: Raison de l'archivage (optionnel)

        Returns:
            L'enregistrement mis a jour ou None si non trouve
        """
        with Database.get_session() as session:
            from sqlalchemy import text

            # Verifier que l'enregistrement existe et n'est pas deja archive
            check_query = text(f'''
                SELECT id, archived FROM azalplus.{table_name}
                WHERE id = :id AND tenant_id = :tenant_id AND deleted_at IS NULL
            ''')
            result = session.execute(check_query, {
                "id": str(record_id),
                "tenant_id": str(tenant_id)
            })
            row = result.fetchone()

            if not row:
                return None

            if row._mapping.get('archived', False):
                raise HTTPException(
                    status_code=400,
                    detail="Cet enregistrement est deja archive"
                )

            # Archiver
            update_query = text(f'''
                UPDATE azalplus.{table_name}
                SET archived = true,
                    archived_at = NOW(),
                    archived_by = :user_id,
                    archive_raison = :raison,
                    updated_at = NOW()
                WHERE id = :id AND tenant_id = :tenant_id
                RETURNING *
            ''')
            result = session.execute(update_query, {
                "id": str(record_id),
                "tenant_id": str(tenant_id),
                "user_id": str(user_id),
                "raison": raison
            })
            session.commit()

            updated_row = result.fetchone()
            if updated_row:
                logger.info(
                    "record_archived",
                    table=table_name,
                    record_id=str(record_id),
                    tenant_id=str(tenant_id),
                    user_id=str(user_id)
                )
                return dict(updated_row._mapping)

            return None

    @staticmethod
    def unarchive_record(
        table_name: str,
        tenant_id: UUID,
        record_id: UUID,
        user_id: UUID
    ) -> Optional[Dict]:
        """
        Desarchive un enregistrement.

        Args:
            table_name: Nom de la table
            tenant_id: ID du tenant (isolation OBLIGATOIRE)
            record_id: ID de l'enregistrement
            user_id: ID de l'utilisateur qui desarchive

        Returns:
            L'enregistrement mis a jour ou None si non trouve
        """
        with Database.get_session() as session:
            from sqlalchemy import text

            # Verifier que l'enregistrement existe et est archive
            check_query = text(f'''
                SELECT id, archived FROM azalplus.{table_name}
                WHERE id = :id AND tenant_id = :tenant_id AND deleted_at IS NULL
            ''')
            result = session.execute(check_query, {
                "id": str(record_id),
                "tenant_id": str(tenant_id)
            })
            row = result.fetchone()

            if not row:
                return None

            if not row._mapping.get('archived', False):
                raise HTTPException(
                    status_code=400,
                    detail="Cet enregistrement n'est pas archive"
                )

            # Desarchiver
            update_query = text(f'''
                UPDATE azalplus.{table_name}
                SET archived = false,
                    archived_at = NULL,
                    archived_by = NULL,
                    archive_raison = NULL,
                    updated_at = NOW(),
                    updated_by = :user_id
                WHERE id = :id AND tenant_id = :tenant_id
                RETURNING *
            ''')
            result = session.execute(update_query, {
                "id": str(record_id),
                "tenant_id": str(tenant_id),
                "user_id": str(user_id)
            })
            session.commit()

            updated_row = result.fetchone()
            if updated_row:
                logger.info(
                    "record_unarchived",
                    table=table_name,
                    record_id=str(record_id),
                    tenant_id=str(tenant_id),
                    user_id=str(user_id)
                )
                return dict(updated_row._mapping)

            return None

    @staticmethod
    def get_archive_stats(tenant_id: UUID) -> ArchiveStats:
        """
        Calcule les statistiques d'archivage pour un tenant.

        Args:
            tenant_id: ID du tenant (isolation OBLIGATOIRE)

        Returns:
            Statistiques d'archivage
        """
        from .parser import ModuleParser

        modules_stats = {}
        total_archived = 0
        total_active = 0

        with Database.get_session() as session:
            from sqlalchemy import text

            for module_name in ModuleParser.list_all():
                try:
                    # Compter les enregistrements archives et actifs
                    count_query = text(f'''
                        SELECT
                            COUNT(*) FILTER (WHERE archived = true) as archived_count,
                            COUNT(*) FILTER (WHERE archived = false OR archived IS NULL) as active_count
                        FROM azalplus.{module_name.lower()}
                        WHERE tenant_id = :tenant_id AND deleted_at IS NULL
                    ''')
                    result = session.execute(count_query, {"tenant_id": str(tenant_id)})
                    row = result.fetchone()

                    if row:
                        archived_count = row._mapping.get('archived_count', 0) or 0
                        active_count = row._mapping.get('active_count', 0) or 0

                        modules_stats[module_name] = {
                            "archived": archived_count,
                            "active": active_count
                        }
                        total_archived += archived_count
                        total_active += active_count
                except Exception as e:
                    # Table n'existe pas ou n'a pas les colonnes d'archivage
                    logger.debug("archive_stats_skip", module=module_name, error=str(e))
                    continue

        return ArchiveStats(
            total_archived=total_archived,
            total_active=total_active,
            storage_archived_kb=0.0,  # A implementer avec pg_relation_size
            storage_active_kb=0.0,
            modules=modules_stats
        )

    @staticmethod
    def get_archive_suggestions(tenant_id: UUID, limit: int = 50) -> List[ArchiveSuggestion]:
        """
        Retourne les suggestions d'archivage basees sur les regles.

        Args:
            tenant_id: ID du tenant (isolation OBLIGATOIRE)
            limit: Nombre max de suggestions

        Returns:
            Liste des suggestions d'archivage
        """
        suggestions = []

        with Database.get_session() as session:
            from sqlalchemy import text

            for module_name, rule in ARCHIVE_RULES.items():
                try:
                    # Calculer la date limite
                    archive_date = date.today() - timedelta(days=rule["years"] * 365)

                    # Requete pour trouver les candidats a l'archivage
                    query = text(f'''
                        SELECT id,
                               COALESCE(nom, raison_sociale, numero, reference, titre, '') as display_name,
                               created_at,
                               EXTRACT(DAY FROM NOW() - created_at) as age_days
                        FROM azalplus.{module_name}
                        WHERE tenant_id = :tenant_id
                        AND deleted_at IS NULL
                        AND (archived = false OR archived IS NULL)
                        AND ({rule["condition"]})
                        ORDER BY created_at ASC
                        LIMIT :limit
                    ''')

                    result = session.execute(query, {
                        "tenant_id": str(tenant_id),
                        "archive_date": archive_date,
                        "limit": limit
                    })

                    for row in result:
                        mapping = row._mapping
                        suggestions.append(ArchiveSuggestion(
                            module=module_name,
                            record_id=str(mapping.get('id')),
                            record_name=mapping.get('display_name', ''),
                            reason=rule["description"],
                            age_days=int(mapping.get('age_days', 0))
                        ))

                        if len(suggestions) >= limit:
                            break

                    if len(suggestions) >= limit:
                        break

                except Exception as e:
                    logger.debug("archive_suggestion_error", module=module_name, error=str(e))
                    continue

        return suggestions[:limit]

    @staticmethod
    def bulk_archive(
        table_name: str,
        tenant_id: UUID,
        record_ids: List[UUID],
        user_id: UUID,
        raison: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Archive plusieurs enregistrements en une seule operation.

        Args:
            table_name: Nom de la table
            tenant_id: ID du tenant (isolation OBLIGATOIRE)
            record_ids: Liste des IDs a archiver
            user_id: ID de l'utilisateur
            raison: Raison de l'archivage

        Returns:
            Statistiques de l'operation
        """
        if not record_ids:
            return {"archived": 0, "errors": 0}

        archived_count = 0
        error_count = 0

        with Database.get_session() as session:
            from sqlalchemy import text

            ids_str = ",".join([f"'{str(rid)}'" for rid in record_ids])

            update_query = text(f'''
                UPDATE azalplus.{table_name}
                SET archived = true,
                    archived_at = NOW(),
                    archived_by = :user_id,
                    archive_raison = :raison,
                    updated_at = NOW()
                WHERE id IN ({ids_str})
                AND tenant_id = :tenant_id
                AND deleted_at IS NULL
                AND (archived = false OR archived IS NULL)
            ''')

            try:
                result = session.execute(update_query, {
                    "tenant_id": str(tenant_id),
                    "user_id": str(user_id),
                    "raison": raison
                })
                session.commit()
                archived_count = result.rowcount
            except Exception as e:
                logger.error("bulk_archive_error", error=str(e))
                error_count = len(record_ids)

        logger.info(
            "bulk_archive_completed",
            table=table_name,
            archived=archived_count,
            errors=error_count,
            tenant_id=str(tenant_id)
        )

        return {
            "archived": archived_count,
            "errors": error_count,
            "total_requested": len(record_ids)
        }


# =============================================================================
# API Routes
# =============================================================================

@archive_router.post("/{module_name}/{item_id}/archiver", tags=["Archives"])
async def archive_item(
    module_name: str,
    item_id: UUID,
    request: ArchiveRequest = None,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Archive un enregistrement.

    L'enregistrement reste dans la base mais n'apparait plus dans les listes par defaut.
    """
    raison = request.raison if request else None

    result = ArchiveService.archive_record(
        table_name=module_name.lower(),
        tenant_id=tenant_id,
        record_id=item_id,
        user_id=user_id,
        raison=raison
    )

    if not result:
        raise HTTPException(status_code=404, detail="Enregistrement non trouve")

    return {
        "status": "archived",
        "id": str(item_id),
        "archived_at": result.get("archived_at")
    }


@archive_router.post("/{module_name}/{item_id}/desarchiver", tags=["Archives"])
async def unarchive_item(
    module_name: str,
    item_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Desarchive un enregistrement.

    L'enregistrement reapparait dans les listes normales.
    """
    result = ArchiveService.unarchive_record(
        table_name=module_name.lower(),
        tenant_id=tenant_id,
        record_id=item_id,
        user_id=user_id
    )

    if not result:
        raise HTTPException(status_code=404, detail="Enregistrement non trouve")

    return {
        "status": "unarchived",
        "id": str(item_id)
    }


@archive_router.get("/stats", tags=["Archives"])
async def get_stats(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Retourne les statistiques d'archivage.

    Inclut le nombre d'enregistrements archives par module.
    """
    stats = ArchiveService.get_archive_stats(tenant_id)
    return stats


@archive_router.get("/suggestions", tags=["Archives"])
async def get_suggestions(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth),
    limit: int = Query(50, ge=1, le=200)
):
    """
    Retourne les suggestions d'archivage.

    Base sur les regles configurees:
    - Factures payees > 3 ans
    - Devis refuses > 1 an
    - Clients inactifs > 2 ans
    """
    suggestions = ArchiveService.get_archive_suggestions(tenant_id, limit)
    return {
        "suggestions": [s.model_dump() for s in suggestions],
        "count": len(suggestions)
    }


@archive_router.post("/{module_name}/bulk-archive", tags=["Archives"])
async def bulk_archive(
    module_name: str,
    record_ids: List[UUID],
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth),
    raison: Optional[str] = None
):
    """
    Archive plusieurs enregistrements en une seule operation.
    """
    result = ArchiveService.bulk_archive(
        table_name=module_name.lower(),
        tenant_id=tenant_id,
        record_ids=record_ids,
        user_id=user_id,
        raison=raison
    )
    return result
