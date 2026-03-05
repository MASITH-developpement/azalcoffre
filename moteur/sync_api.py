# =============================================================================
# AZALPLUS - Sync API for Offline Support
# =============================================================================
"""
API endpoints for mobile offline synchronization.

Endpoints:
    GET  /api/v1/{module}/sync       - Pull changes since timestamp (delta sync)
    POST /api/v1/{module}/sync/push  - Push batched mutations from offline queue
    GET  /api/v1/sync/status         - Get sync status for all modules
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body, status
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional, Union
from uuid import UUID
from datetime import datetime
from enum import Enum
import structlog

from .db import Database
from .parser import ModuleParser
from .tenant import get_current_tenant, get_current_user_id
from .auth import require_auth

logger = structlog.get_logger()

# =============================================================================
# Router Sync API
# =============================================================================
router_sync = APIRouter(
    tags=["Sync"]
)


# =============================================================================
# Enums
# =============================================================================
class MutationOperation(str, Enum):
    """Types of mutation operations."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


# =============================================================================
# Pydantic Models - Request
# =============================================================================
class MutationItem(BaseModel):
    """A single mutation from the offline queue."""

    client_id: str = Field(..., description="Client-side unique ID for this mutation")
    record_id: Optional[UUID] = Field(None, description="Server record ID (null for create)")
    operation: MutationOperation = Field(..., description="Type of operation")
    payload: Optional[Dict[str, Any]] = Field(None, description="Data payload (for create/update)")
    base_version: Optional[datetime] = Field(
        None,
        description="Base version timestamp for conflict detection (updated_at of record when fetched)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "client_id": "offline_1234567890",
                "record_id": "550e8400-e29b-41d4-a716-446655440000",
                "operation": "update",
                "payload": {"nom": "Updated Name", "statut": "ACTIF"},
                "base_version": "2024-01-15T10:30:00Z"
            }
        }


class SyncPushRequest(BaseModel):
    """Request body for pushing offline mutations."""

    mutations: List[MutationItem] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of mutations to apply (max 100)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "mutations": [
                    {
                        "client_id": "offline_001",
                        "record_id": None,
                        "operation": "create",
                        "payload": {"nom": "New Client", "email": "client@example.com"},
                        "base_version": None
                    },
                    {
                        "client_id": "offline_002",
                        "record_id": "550e8400-e29b-41d4-a716-446655440000",
                        "operation": "update",
                        "payload": {"statut": "ACTIF"},
                        "base_version": "2024-01-15T10:30:00Z"
                    }
                ]
            }
        }


# =============================================================================
# Pydantic Models - Response
# =============================================================================
class SyncPullResponse(BaseModel):
    """Response for delta sync pull endpoint."""

    items: List[Dict[str, Any]] = Field(..., description="Changed/new records since timestamp")
    deleted_ids: List[UUID] = Field(default_factory=list, description="IDs of soft-deleted records")
    next_cursor: Optional[str] = Field(None, description="Cursor for next page (if has_more is true)")
    has_more: bool = Field(False, description="Whether more records are available")
    server_timestamp: datetime = Field(..., description="Current server timestamp for next sync")
    total_changes: int = Field(0, description="Total number of changes available")

    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {"id": "uuid1", "nom": "Client A", "updated_at": "2024-01-15T10:30:00Z"},
                    {"id": "uuid2", "nom": "Client B", "updated_at": "2024-01-15T11:00:00Z"}
                ],
                "deleted_ids": ["uuid3", "uuid4"],
                "next_cursor": "eyJ1cGRhdGVkX2F0IjoiMjAyNC0wMS0xNVQxMTowMDowMFoifQ==",
                "has_more": True,
                "server_timestamp": "2024-01-15T12:00:00Z",
                "total_changes": 50
            }
        }


class MutationResult(BaseModel):
    """Result of a single mutation."""

    client_id: str = Field(..., description="Client-side ID from the request")
    success: bool = Field(..., description="Whether the mutation was applied successfully")
    record_id: Optional[UUID] = Field(None, description="Server record ID (new ID for creates)")
    server_version: Optional[datetime] = Field(None, description="New updated_at timestamp")
    error: Optional[str] = Field(None, description="Error message if failed")
    error_code: Optional[str] = Field(None, description="Error code for client handling")
    conflict_data: Optional[Dict[str, Any]] = Field(
        None,
        description="Current server data if conflict detected"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "client_id": "offline_001",
                "success": True,
                "record_id": "550e8400-e29b-41d4-a716-446655440000",
                "server_version": "2024-01-15T12:00:00Z",
                "error": None,
                "conflict_data": None
            }
        }


class SyncPushResponse(BaseModel):
    """Response for pushing offline mutations."""

    results: List[MutationResult] = Field(..., description="Results for each mutation")
    server_timestamp: datetime = Field(..., description="Current server timestamp")
    success_count: int = Field(0, description="Number of successful mutations")
    failure_count: int = Field(0, description="Number of failed mutations")
    conflict_count: int = Field(0, description="Number of conflicts detected")

    class Config:
        json_schema_extra = {
            "example": {
                "results": [
                    {"client_id": "offline_001", "success": True, "record_id": "uuid1"},
                    {"client_id": "offline_002", "success": False, "error": "Conflict detected"}
                ],
                "server_timestamp": "2024-01-15T12:00:00Z",
                "success_count": 1,
                "failure_count": 1,
                "conflict_count": 1
            }
        }


class ModuleSyncStatus(BaseModel):
    """Sync status for a single module."""

    module: str = Field(..., description="Module name")
    record_count: int = Field(0, description="Total number of records")
    last_modified: Optional[datetime] = Field(None, description="Most recent update timestamp")
    pending_mutations: int = Field(0, description="Number of pending server-side mutations")

    class Config:
        json_schema_extra = {
            "example": {
                "module": "clients",
                "record_count": 150,
                "last_modified": "2024-01-15T12:00:00Z",
                "pending_mutations": 0
            }
        }


class SyncStatusResponse(BaseModel):
    """Response for sync status endpoint."""

    modules: List[ModuleSyncStatus] = Field(..., description="Status for each module")
    server_timestamp: datetime = Field(..., description="Current server timestamp")
    total_records: int = Field(0, description="Total records across all modules")

    class Config:
        json_schema_extra = {
            "example": {
                "modules": [
                    {"module": "clients", "record_count": 150, "last_modified": "2024-01-15T12:00:00Z"},
                    {"module": "factures", "record_count": 300, "last_modified": "2024-01-15T11:30:00Z"}
                ],
                "server_timestamp": "2024-01-15T12:00:00Z",
                "total_records": 450
            }
        }


class ErrorDetail(BaseModel):
    """Error detail response."""
    detail: str = Field(..., description="Error message")
    code: Optional[str] = Field(None, description="Error code")


# =============================================================================
# Sync Service
# =============================================================================
class SyncService:
    """Service for offline synchronization operations."""

    @staticmethod
    def pull_changes(
        module_name: str,
        tenant_id: UUID,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        limit: int = 100
    ) -> SyncPullResponse:
        """
        Pull changes since a timestamp for delta sync.

        Args:
            module_name: Name of the module to sync
            tenant_id: Tenant ID for isolation
            since: Timestamp to get changes since (ISO format)
            cursor: Pagination cursor
            limit: Maximum number of records to return

        Returns:
            SyncPullResponse with changed items and deleted IDs
        """
        from sqlalchemy import text
        import base64
        import json

        server_timestamp = datetime.utcnow()

        # Decode cursor if provided
        offset = 0
        if cursor:
            try:
                cursor_data = json.loads(base64.b64decode(cursor).decode())
                offset = cursor_data.get("offset", 0)
            except Exception:
                offset = 0

        with Database.get_session() as session:
            # Build query for changed/new records (including soft-deleted for sync)
            # We need records where updated_at > since OR deleted_at > since
            params = {"tenant_id": str(tenant_id), "limit": limit + 1, "offset": offset}

            if since:
                # Get active records updated since timestamp
                items_query = f'''
                    SELECT * FROM azalplus.{module_name}
                    WHERE tenant_id = :tenant_id
                    AND deleted_at IS NULL
                    AND updated_at > :since
                    ORDER BY updated_at ASC
                    LIMIT :limit OFFSET :offset
                '''
                params["since"] = since

                # Get deleted records since timestamp
                deleted_query = f'''
                    SELECT id FROM azalplus.{module_name}
                    WHERE tenant_id = :tenant_id
                    AND deleted_at IS NOT NULL
                    AND deleted_at > :since
                    ORDER BY deleted_at ASC
                '''
            else:
                # Initial sync - get all active records
                items_query = f'''
                    SELECT * FROM azalplus.{module_name}
                    WHERE tenant_id = :tenant_id
                    AND deleted_at IS NULL
                    AND (archived = false OR archived IS NULL)
                    ORDER BY updated_at ASC
                    LIMIT :limit OFFSET :offset
                '''
                deleted_query = None

            # Execute items query
            result = session.execute(text(items_query), params)
            rows = [dict(row._mapping) for row in result]

            # Check if there are more records
            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]

            # Get deleted IDs if since is provided
            deleted_ids = []
            if deleted_query:
                deleted_result = session.execute(text(deleted_query), params)
                deleted_ids = [row.id for row in deleted_result]

            # Count total changes for info
            total_changes = len(rows) + len(deleted_ids)

            # Generate next cursor
            next_cursor = None
            if has_more:
                cursor_data = {"offset": offset + limit}
                next_cursor = base64.b64encode(
                    json.dumps(cursor_data).encode()
                ).decode()

            # Decrypt sensitive fields if needed
            encrypted_fields = Database.get_encrypted_fields(module_name)
            if encrypted_fields:
                from .encryption import EncryptionMiddleware
                rows = [
                    EncryptionMiddleware.decrypt_dict(row, encrypted_fields, tenant_id)
                    for row in rows
                ]

            return SyncPullResponse(
                items=rows,
                deleted_ids=deleted_ids,
                next_cursor=next_cursor,
                has_more=has_more,
                server_timestamp=server_timestamp,
                total_changes=total_changes
            )

    @staticmethod
    def push_mutations(
        module_name: str,
        tenant_id: UUID,
        user_id: UUID,
        mutations: List[MutationItem]
    ) -> SyncPushResponse:
        """
        Push batched mutations from offline queue.

        Args:
            module_name: Name of the module
            tenant_id: Tenant ID for isolation
            user_id: User ID for audit
            mutations: List of mutations to apply

        Returns:
            SyncPushResponse with results for each mutation
        """
        from sqlalchemy import text

        results = []
        success_count = 0
        failure_count = 0
        conflict_count = 0
        server_timestamp = datetime.utcnow()

        for mutation in mutations:
            try:
                result = SyncService._apply_mutation(
                    module_name=module_name,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    mutation=mutation
                )
                results.append(result)

                if result.success:
                    success_count += 1
                else:
                    failure_count += 1
                    if result.conflict_data:
                        conflict_count += 1

            except Exception as e:
                logger.error(
                    "sync_mutation_error",
                    module=module_name,
                    client_id=mutation.client_id,
                    error=str(e)
                )
                results.append(MutationResult(
                    client_id=mutation.client_id,
                    success=False,
                    error=str(e),
                    error_code="INTERNAL_ERROR"
                ))
                failure_count += 1

        return SyncPushResponse(
            results=results,
            server_timestamp=server_timestamp,
            success_count=success_count,
            failure_count=failure_count,
            conflict_count=conflict_count
        )

    @staticmethod
    def _apply_mutation(
        module_name: str,
        tenant_id: UUID,
        user_id: UUID,
        mutation: MutationItem
    ) -> MutationResult:
        """
        Apply a single mutation with conflict detection.

        Args:
            module_name: Name of the module
            tenant_id: Tenant ID for isolation
            user_id: User ID for audit
            mutation: The mutation to apply

        Returns:
            MutationResult with success status or conflict data
        """
        from sqlalchemy import text

        if mutation.operation == MutationOperation.CREATE:
            return SyncService._apply_create(module_name, tenant_id, user_id, mutation)

        elif mutation.operation == MutationOperation.UPDATE:
            return SyncService._apply_update(module_name, tenant_id, user_id, mutation)

        elif mutation.operation == MutationOperation.DELETE:
            return SyncService._apply_delete(module_name, tenant_id, user_id, mutation)

        return MutationResult(
            client_id=mutation.client_id,
            success=False,
            error="Unknown operation",
            error_code="INVALID_OPERATION"
        )

    @staticmethod
    def _apply_create(
        module_name: str,
        tenant_id: UUID,
        user_id: UUID,
        mutation: MutationItem
    ) -> MutationResult:
        """Apply a create mutation."""
        try:
            if not mutation.payload:
                return MutationResult(
                    client_id=mutation.client_id,
                    success=False,
                    error="Payload required for create",
                    error_code="MISSING_PAYLOAD"
                )

            record = Database.insert(
                table_name=module_name,
                tenant_id=tenant_id,
                data=mutation.payload,
                user_id=user_id
            )

            return MutationResult(
                client_id=mutation.client_id,
                success=True,
                record_id=UUID(str(record["id"])),
                server_version=record.get("updated_at") or record.get("created_at")
            )

        except Exception as e:
            logger.error("sync_create_error", module=module_name, error=str(e))
            return MutationResult(
                client_id=mutation.client_id,
                success=False,
                error=str(e),
                error_code="CREATE_FAILED"
            )

    @staticmethod
    def _apply_update(
        module_name: str,
        tenant_id: UUID,
        user_id: UUID,
        mutation: MutationItem
    ) -> MutationResult:
        """Apply an update mutation with optimistic locking."""
        from sqlalchemy import text

        if not mutation.record_id:
            return MutationResult(
                client_id=mutation.client_id,
                success=False,
                error="Record ID required for update",
                error_code="MISSING_RECORD_ID"
            )

        if not mutation.payload:
            return MutationResult(
                client_id=mutation.client_id,
                success=False,
                error="Payload required for update",
                error_code="MISSING_PAYLOAD"
            )

        # Get current record for conflict detection
        current = Database.get_by_id(module_name, tenant_id, mutation.record_id)

        if not current:
            return MutationResult(
                client_id=mutation.client_id,
                success=False,
                error="Record not found",
                error_code="NOT_FOUND"
            )

        # Check for conflict using optimistic locking
        if mutation.base_version:
            current_updated_at = current.get("updated_at")
            if current_updated_at and current_updated_at > mutation.base_version:
                # Conflict detected - record was modified since client fetched it
                return MutationResult(
                    client_id=mutation.client_id,
                    success=False,
                    error="Conflict detected - record was modified on server",
                    error_code="CONFLICT",
                    conflict_data=current
                )

        # Apply update
        try:
            record = Database.update(
                table_name=module_name,
                tenant_id=tenant_id,
                record_id=mutation.record_id,
                data=mutation.payload,
                user_id=user_id
            )

            if not record:
                return MutationResult(
                    client_id=mutation.client_id,
                    success=False,
                    error="Update failed",
                    error_code="UPDATE_FAILED"
                )

            return MutationResult(
                client_id=mutation.client_id,
                success=True,
                record_id=mutation.record_id,
                server_version=record.get("updated_at")
            )

        except Exception as e:
            logger.error("sync_update_error", module=module_name, error=str(e))
            return MutationResult(
                client_id=mutation.client_id,
                success=False,
                error=str(e),
                error_code="UPDATE_FAILED"
            )

    @staticmethod
    def _apply_delete(
        module_name: str,
        tenant_id: UUID,
        user_id: UUID,
        mutation: MutationItem
    ) -> MutationResult:
        """Apply a delete mutation (soft delete)."""
        if not mutation.record_id:
            return MutationResult(
                client_id=mutation.client_id,
                success=False,
                error="Record ID required for delete",
                error_code="MISSING_RECORD_ID"
            )

        # Check if record exists and for conflicts
        current = Database.get_by_id(module_name, tenant_id, mutation.record_id)

        if not current:
            # Already deleted or doesn't exist - consider it success
            return MutationResult(
                client_id=mutation.client_id,
                success=True,
                record_id=mutation.record_id
            )

        # Check for conflict if base_version provided
        if mutation.base_version:
            current_updated_at = current.get("updated_at")
            if current_updated_at and current_updated_at > mutation.base_version:
                return MutationResult(
                    client_id=mutation.client_id,
                    success=False,
                    error="Conflict detected - record was modified on server",
                    error_code="CONFLICT",
                    conflict_data=current
                )

        # Perform soft delete
        try:
            success = Database.soft_delete(module_name, tenant_id, mutation.record_id)

            return MutationResult(
                client_id=mutation.client_id,
                success=success,
                record_id=mutation.record_id,
                error=None if success else "Delete failed",
                error_code=None if success else "DELETE_FAILED"
            )

        except Exception as e:
            logger.error("sync_delete_error", module=module_name, error=str(e))
            return MutationResult(
                client_id=mutation.client_id,
                success=False,
                error=str(e),
                error_code="DELETE_FAILED"
            )

    @staticmethod
    def get_sync_status(tenant_id: UUID, modules: Optional[List[str]] = None) -> SyncStatusResponse:
        """
        Get sync status for all or specified modules.

        Args:
            tenant_id: Tenant ID for isolation
            modules: Optional list of module names to check

        Returns:
            SyncStatusResponse with status for each module
        """
        from sqlalchemy import text

        server_timestamp = datetime.utcnow()
        module_statuses = []
        total_records = 0

        # Get list of modules to check
        if modules:
            module_names = modules
        else:
            module_names = [
                name for name in ModuleParser.list_all()
                if ModuleParser.get(name) and ModuleParser.get(name).actif
            ]

        with Database.get_session() as session:
            for module_name in module_names:
                try:
                    # Get record count and last modified
                    stats_query = text(f'''
                        SELECT
                            COUNT(*) as record_count,
                            MAX(updated_at) as last_modified
                        FROM azalplus.{module_name}
                        WHERE tenant_id = :tenant_id
                        AND deleted_at IS NULL
                        AND (archived = false OR archived IS NULL)
                    ''')

                    result = session.execute(stats_query, {"tenant_id": str(tenant_id)})
                    row = result.fetchone()

                    if row:
                        record_count = row.record_count or 0
                        last_modified = row.last_modified

                        module_statuses.append(ModuleSyncStatus(
                            module=module_name,
                            record_count=record_count,
                            last_modified=last_modified,
                            pending_mutations=0  # Server-side mutations tracking (future enhancement)
                        ))
                        total_records += record_count

                except Exception as e:
                    logger.debug("sync_status_module_error", module=module_name, error=str(e))
                    # Module might not exist as a table - skip it
                    continue

        return SyncStatusResponse(
            modules=module_statuses,
            server_timestamp=server_timestamp,
            total_records=total_records
        )


# =============================================================================
# Endpoints
# =============================================================================

@router_sync.get(
    "/{module}/sync",
    response_model=SyncPullResponse,
    summary="Pull changes for delta sync",
    description="""
Pull changes since a timestamp for delta synchronization.

### Delta Sync

Returns records that have been created, modified, or deleted since the provided timestamp.
Use this endpoint to keep the mobile app in sync with the server.

### Pagination

Results are paginated. Use the `cursor` parameter with the `next_cursor` from the previous
response to get the next page of results.

### Initial Sync

For the first sync (no `since` parameter), all active records are returned.

### Response

- `items`: Array of changed/new records
- `deleted_ids`: Array of IDs for soft-deleted records (for removal from local DB)
- `next_cursor`: Cursor for the next page (if `has_more` is true)
- `server_timestamp`: Use this as the `since` parameter for the next sync
    """,
    responses={
        200: {"description": "Changes since timestamp"},
        401: {"description": "Not authenticated", "model": ErrorDetail},
        404: {"description": "Module not found", "model": ErrorDetail}
    }
)
async def sync_pull(
    module: str = Path(..., description="Module name"),
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth),
    since: Optional[datetime] = Query(
        None,
        description="ISO timestamp to get changes since (e.g., 2024-01-15T10:30:00Z)"
    ),
    cursor: Optional[str] = Query(
        None,
        description="Pagination cursor from previous response"
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Maximum number of records to return (default: 100, max: 500)"
    )
) -> SyncPullResponse:
    """Pull changes since timestamp for delta sync."""

    # Validate module exists
    module_def = ModuleParser.get(module)
    if not module_def or not module_def.actif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module}' not found"
        )

    logger.info(
        "sync_pull",
        module=module,
        tenant_id=str(tenant_id),
        since=since.isoformat() if since else None,
        user_email=user.get("email")
    )

    return SyncService.pull_changes(
        module_name=module,
        tenant_id=tenant_id,
        since=since,
        cursor=cursor,
        limit=limit
    )


@router_sync.post(
    "/{module}/sync/push",
    response_model=SyncPushResponse,
    summary="Push offline mutations",
    description="""
Push batched mutations from the offline queue.

### Mutation Types

- `create`: Create a new record (payload required, record_id should be null)
- `update`: Update an existing record (payload and record_id required)
- `delete`: Soft-delete a record (record_id required)

### Conflict Detection

For updates and deletes, provide `base_version` (the `updated_at` timestamp from when the
record was fetched). If the server record has been modified since then, a conflict is detected.

### Conflict Resolution

When a conflict is detected:
- `success` will be `false`
- `error_code` will be `"CONFLICT"`
- `conflict_data` will contain the current server record

The client can then decide how to resolve the conflict (keep local, keep server, or merge).

### Batch Processing

Mutations are processed in order. Each mutation is independent - a failure in one mutation
does not prevent others from being applied.

### Maximum Batch Size

Maximum 100 mutations per request.
    """,
    responses={
        200: {"description": "Mutation results"},
        400: {"description": "Invalid request", "model": ErrorDetail},
        401: {"description": "Not authenticated", "model": ErrorDetail},
        404: {"description": "Module not found", "model": ErrorDetail}
    }
)
async def sync_push(
    module: str = Path(..., description="Module name"),
    request: SyncPushRequest = Body(...),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
) -> SyncPushResponse:
    """Push batched mutations from offline queue."""

    # Validate module exists
    module_def = ModuleParser.get(module)
    if not module_def or not module_def.actif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module}' not found"
        )

    logger.info(
        "sync_push",
        module=module,
        tenant_id=str(tenant_id),
        mutation_count=len(request.mutations),
        user_email=user.get("email")
    )

    return SyncService.push_mutations(
        module_name=module,
        tenant_id=tenant_id,
        user_id=user_id,
        mutations=request.mutations
    )


@router_sync.get(
    "/sync/status",
    response_model=SyncStatusResponse,
    summary="Get sync status for all modules",
    description="""
Get synchronization status for all active modules.

### Response

Returns for each module:
- `module`: Module name
- `record_count`: Total number of active records
- `last_modified`: Timestamp of most recently modified record
- `pending_mutations`: Number of pending server-side mutations (for future use)

### Use Cases

- Display sync status in the mobile app
- Determine which modules need synchronization
- Show data freshness indicators
    """,
    responses={
        200: {"description": "Sync status for all modules"},
        401: {"description": "Not authenticated", "model": ErrorDetail}
    }
)
async def sync_status(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth),
    modules: Optional[str] = Query(
        None,
        description="Comma-separated list of module names to check (all if not specified)"
    )
) -> SyncStatusResponse:
    """Get sync status for all modules."""

    # Parse module list if provided
    module_list = None
    if modules:
        module_list = [m.strip() for m in modules.split(",") if m.strip()]

    logger.debug(
        "sync_status",
        tenant_id=str(tenant_id),
        modules=module_list,
        user_email=user.get("email")
    )

    return SyncService.get_sync_status(
        tenant_id=tenant_id,
        modules=module_list
    )
