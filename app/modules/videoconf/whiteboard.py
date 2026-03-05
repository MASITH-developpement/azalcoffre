# =============================================================================
# AZALPLUS - VideoConf Whiteboard Service
# =============================================================================
"""
Service de gestion du tableau blanc collaboratif.

Fonctionnalites:
- Etat synchronise en temps reel
- Operations CRDT-like (versioning)
- Export en PNG/SVG
- Stockage persistant
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from enum import Enum
import json
import base64
import io

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = structlog.get_logger()


class WhiteboardTool(str, Enum):
    """Outils du tableau blanc."""
    PEN = "pen"
    HIGHLIGHTER = "highlighter"
    ERASER = "eraser"
    TEXT = "text"
    SHAPE = "shape"
    LINE = "line"
    ARROW = "arrow"
    STICKY_NOTE = "sticky_note"
    IMAGE = "image"


class OperationType(str, Enum):
    """Types d'operations sur le whiteboard."""
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
    MOVE = "move"
    CLEAR = "clear"
    UNDO = "undo"
    REDO = "redo"


class WhiteboardService:
    """Service de gestion du tableau blanc collaboratif."""

    def __init__(self, db: Session, tenant_id: UUID):
        """
        Initialise le service whiteboard.

        Args:
            db: Session SQLAlchemy
            tenant_id: ID du tenant (isolation obligatoire)
        """
        self.db = db
        self.tenant_id = tenant_id
        self._table_name = "reunion_whiteboard_state"

    # =========================================================================
    # Helpers
    # =========================================================================
    def _verify_meeting_access(self, meeting_id: UUID) -> bool:
        """Verifie que la reunion appartient au tenant."""
        query = text("""
            SELECT id FROM azalplus.reunions
            WHERE id = :meeting_id
            AND tenant_id = :tenant_id
            AND deleted_at IS NULL
        """)
        result = self.db.execute(query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        return result.fetchone() is not None

    def _get_or_create_whiteboard(self, meeting_id: UUID) -> Dict[str, Any]:
        """Recupere ou cree l'etat du whiteboard."""
        # Verifier si le whiteboard existe
        query = text("""
            SELECT * FROM azalplus.reunion_whiteboard_state
            WHERE reunion_id = :meeting_id
            AND tenant_id = :tenant_id
        """)
        result = self.db.execute(query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        row = result.fetchone()

        if row:
            return dict(row._mapping)

        # Creer un nouveau whiteboard
        whiteboard_id = uuid4()
        now = datetime.utcnow()
        initial_state = {
            "objects": [],
            "background": {
                "type": "color",
                "value": "#FFFFFF"
            },
            "viewport": {
                "x": 0,
                "y": 0,
                "zoom": 1.0
            }
        }

        insert_query = text("""
            INSERT INTO azalplus.reunion_whiteboard_state
            (id, tenant_id, reunion_id, state, version, created_at, updated_at)
            VALUES (:id, :tenant_id, :reunion_id, :state, 1, :created_at, :updated_at)
            RETURNING *
        """)

        insert_result = self.db.execute(insert_query, {
            "id": str(whiteboard_id),
            "tenant_id": str(self.tenant_id),
            "reunion_id": str(meeting_id),
            "state": json.dumps(initial_state),
            "created_at": now,
            "updated_at": now
        })
        self.db.commit()

        insert_row = insert_result.fetchone()

        logger.info(
            "whiteboard_created",
            whiteboard_id=str(whiteboard_id),
            meeting_id=str(meeting_id)
        )

        return dict(insert_row._mapping) if insert_row else None

    # =========================================================================
    # State Management
    # =========================================================================
    async def get_state(
        self,
        meeting_id: UUID,
        include_history: bool = False
    ) -> Dict[str, Any]:
        """
        Recupere l'etat actuel du tableau blanc.

        Args:
            meeting_id: ID de la reunion
            include_history: Inclure l'historique des operations

        Returns:
            Etat du whiteboard avec metadonnees
        """
        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        whiteboard = self._get_or_create_whiteboard(meeting_id)

        # Parser l'etat JSON
        state = json.loads(whiteboard["state"]) if isinstance(whiteboard["state"], str) else whiteboard["state"]

        response = {
            "id": whiteboard["id"],
            "meeting_id": str(meeting_id),
            "state": state,
            "version": whiteboard["version"],
            "object_count": len(state.get("objects", [])),
            "updated_at": whiteboard["updated_at"].isoformat() if whiteboard.get("updated_at") else None
        }

        if include_history:
            # Recuperer les dernieres operations
            history_query = text("""
                SELECT * FROM azalplus.reunion_whiteboard_operations
                WHERE whiteboard_id = :whiteboard_id
                AND tenant_id = :tenant_id
                ORDER BY created_at DESC
                LIMIT 50
            """)
            history_result = self.db.execute(history_query, {
                "whiteboard_id": str(whiteboard["id"]),
                "tenant_id": str(self.tenant_id)
            })
            response["history"] = [dict(row._mapping) for row in history_result]

        return response

    async def update_state(
        self,
        meeting_id: UUID,
        operations: List[Dict[str, Any]],
        expected_version: int,
        participant_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Applique des operations au tableau blanc.

        Args:
            meeting_id: ID de la reunion
            operations: Liste des operations a appliquer
            expected_version: Version attendue (optimistic locking)
            participant_id: ID du participant effectuant les modifications

        Returns:
            Nouvel etat du whiteboard

        Raises:
            ValueError: Si conflit de version
        """
        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        whiteboard = self._get_or_create_whiteboard(meeting_id)
        current_version = whiteboard["version"]

        # Verifier la version (optimistic locking)
        if expected_version != current_version:
            logger.warning(
                "whiteboard_version_conflict",
                meeting_id=str(meeting_id),
                expected=expected_version,
                current=current_version
            )
            raise ValueError(f"Conflit de version: attendu {expected_version}, actuel {current_version}")

        # Appliquer les operations
        state = json.loads(whiteboard["state"]) if isinstance(whiteboard["state"], str) else whiteboard["state"]
        objects = state.get("objects", [])

        for op in operations:
            op_type = op.get("type")
            obj_id = op.get("object_id")
            obj_data = op.get("data", {})

            if op_type == OperationType.ADD.value:
                # Ajouter un objet
                new_obj = {
                    "id": str(uuid4()),
                    "tool": obj_data.get("tool", WhiteboardTool.PEN.value),
                    "created_at": datetime.utcnow().isoformat(),
                    "created_by": str(participant_id) if participant_id else None,
                    **obj_data
                }
                objects.append(new_obj)

            elif op_type == OperationType.UPDATE.value:
                # Mettre a jour un objet
                for i, obj in enumerate(objects):
                    if obj.get("id") == obj_id:
                        objects[i] = {**obj, **obj_data, "updated_at": datetime.utcnow().isoformat()}
                        break

            elif op_type == OperationType.DELETE.value:
                # Supprimer un objet
                objects = [obj for obj in objects if obj.get("id") != obj_id]

            elif op_type == OperationType.MOVE.value:
                # Deplacer un objet
                for i, obj in enumerate(objects):
                    if obj.get("id") == obj_id:
                        objects[i]["x"] = obj_data.get("x", obj.get("x", 0))
                        objects[i]["y"] = obj_data.get("y", obj.get("y", 0))
                        objects[i]["updated_at"] = datetime.utcnow().isoformat()
                        break

        state["objects"] = objects
        new_version = current_version + 1
        now = datetime.utcnow()

        # Mettre a jour en base
        update_query = text("""
            UPDATE azalplus.reunion_whiteboard_state
            SET state = :state, version = :version, updated_at = :updated_at
            WHERE id = :id AND tenant_id = :tenant_id AND version = :expected_version
            RETURNING *
        """)

        update_result = self.db.execute(update_query, {
            "id": str(whiteboard["id"]),
            "tenant_id": str(self.tenant_id),
            "state": json.dumps(state),
            "version": new_version,
            "updated_at": now,
            "expected_version": current_version
        })
        self.db.commit()

        updated_row = update_result.fetchone()
        if not updated_row:
            raise ValueError("Conflit de version lors de la mise a jour")

        # Enregistrer les operations dans l'historique
        for op in operations:
            op_insert = text("""
                INSERT INTO azalplus.reunion_whiteboard_operations
                (id, tenant_id, whiteboard_id, operation_type, object_id, data,
                 participant_id, version, created_at)
                VALUES (:id, :tenant_id, :whiteboard_id, :operation_type, :object_id, :data,
                        :participant_id, :version, :created_at)
            """)
            self.db.execute(op_insert, {
                "id": str(uuid4()),
                "tenant_id": str(self.tenant_id),
                "whiteboard_id": str(whiteboard["id"]),
                "operation_type": op.get("type"),
                "object_id": op.get("object_id"),
                "data": json.dumps(op.get("data")),
                "participant_id": str(participant_id) if participant_id else None,
                "version": new_version,
                "created_at": now
            })
        self.db.commit()

        logger.info(
            "whiteboard_updated",
            meeting_id=str(meeting_id),
            operations_count=len(operations),
            new_version=new_version,
            object_count=len(objects)
        )

        return {
            "id": str(whiteboard["id"]),
            "meeting_id": str(meeting_id),
            "state": state,
            "version": new_version,
            "object_count": len(objects),
            "updated_at": now.isoformat()
        }

    async def clear_whiteboard(
        self,
        meeting_id: UUID,
        cleared_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Efface tout le contenu du tableau blanc.

        Args:
            meeting_id: ID de la reunion
            cleared_by: ID du participant

        Returns:
            Whiteboard vide
        """
        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        whiteboard = self._get_or_create_whiteboard(meeting_id)
        current_version = whiteboard["version"]
        new_version = current_version + 1
        now = datetime.utcnow()

        # Etat vide
        empty_state = {
            "objects": [],
            "background": {
                "type": "color",
                "value": "#FFFFFF"
            },
            "viewport": {
                "x": 0,
                "y": 0,
                "zoom": 1.0
            }
        }

        # Mettre a jour en base
        update_query = text("""
            UPDATE azalplus.reunion_whiteboard_state
            SET state = :state, version = :version, updated_at = :updated_at
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)

        self.db.execute(update_query, {
            "id": str(whiteboard["id"]),
            "tenant_id": str(self.tenant_id),
            "state": json.dumps(empty_state),
            "version": new_version,
            "updated_at": now
        })

        # Enregistrer l'operation clear
        op_insert = text("""
            INSERT INTO azalplus.reunion_whiteboard_operations
            (id, tenant_id, whiteboard_id, operation_type, data, participant_id, version, created_at)
            VALUES (:id, :tenant_id, :whiteboard_id, 'clear', :data, :participant_id, :version, :created_at)
        """)
        self.db.execute(op_insert, {
            "id": str(uuid4()),
            "tenant_id": str(self.tenant_id),
            "whiteboard_id": str(whiteboard["id"]),
            "data": json.dumps({"previous_object_count": len(json.loads(whiteboard["state"]).get("objects", []))}),
            "participant_id": str(cleared_by) if cleared_by else None,
            "version": new_version,
            "created_at": now
        })
        self.db.commit()

        logger.info(
            "whiteboard_cleared",
            meeting_id=str(meeting_id),
            cleared_by=str(cleared_by) if cleared_by else None
        )

        return {
            "id": str(whiteboard["id"]),
            "meeting_id": str(meeting_id),
            "state": empty_state,
            "version": new_version,
            "object_count": 0,
            "updated_at": now.isoformat()
        }

    # =========================================================================
    # Export
    # =========================================================================
    async def export_image(
        self,
        meeting_id: UUID,
        format: str = "png",
        width: int = 1920,
        height: int = 1080,
        background_color: str = "#FFFFFF"
    ) -> bytes:
        """
        Exporte le tableau blanc en image.

        Args:
            meeting_id: ID de la reunion
            format: Format d'export (png, svg)
            width: Largeur de l'image
            height: Hauteur de l'image
            background_color: Couleur de fond

        Returns:
            Contenu de l'image en bytes
        """
        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        whiteboard = self._get_or_create_whiteboard(meeting_id)
        state = json.loads(whiteboard["state"]) if isinstance(whiteboard["state"], str) else whiteboard["state"]
        objects = state.get("objects", [])

        if format.lower() == "svg":
            return self._export_svg(objects, width, height, background_color)
        else:
            return await self._export_png(objects, width, height, background_color)

    def _export_svg(
        self,
        objects: List[dict],
        width: int,
        height: int,
        background_color: str
    ) -> bytes:
        """Genere un SVG a partir des objets."""
        svg_elements = []

        # En-tete SVG
        svg_header = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="{background_color}"/>
'''

        for obj in objects:
            tool = obj.get("tool", "pen")
            color = obj.get("color", "#000000")
            stroke_width = obj.get("stroke_width", 2)

            if tool in ["pen", "highlighter"]:
                # Chemin de dessin
                points = obj.get("points", [])
                if points and len(points) >= 2:
                    path_data = f"M {points[0][0]} {points[0][1]}"
                    for point in points[1:]:
                        path_data += f" L {point[0]} {point[1]}"

                    opacity = "0.5" if tool == "highlighter" else "1"
                    svg_elements.append(
                        f'  <path d="{path_data}" stroke="{color}" stroke-width="{stroke_width}" '
                        f'fill="none" stroke-linecap="round" stroke-linejoin="round" opacity="{opacity}"/>'
                    )

            elif tool == "line":
                x1 = obj.get("x1", 0)
                y1 = obj.get("y1", 0)
                x2 = obj.get("x2", 100)
                y2 = obj.get("y2", 100)
                svg_elements.append(
                    f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                    f'stroke="{color}" stroke-width="{stroke_width}"/>'
                )

            elif tool == "arrow":
                x1 = obj.get("x1", 0)
                y1 = obj.get("y1", 0)
                x2 = obj.get("x2", 100)
                y2 = obj.get("y2", 100)
                # Fleche simplifiee
                svg_elements.append(
                    f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                    f'stroke="{color}" stroke-width="{stroke_width}" marker-end="url(#arrow)"/>'
                )

            elif tool == "shape":
                shape_type = obj.get("shape_type", "rectangle")
                x = obj.get("x", 0)
                y = obj.get("y", 0)
                w = obj.get("width", 100)
                h = obj.get("height", 100)
                fill = obj.get("fill", "none")

                if shape_type == "rectangle":
                    svg_elements.append(
                        f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" '
                        f'stroke="{color}" stroke-width="{stroke_width}" fill="{fill}"/>'
                    )
                elif shape_type == "ellipse":
                    cx = x + w / 2
                    cy = y + h / 2
                    rx = w / 2
                    ry = h / 2
                    svg_elements.append(
                        f'  <ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" '
                        f'stroke="{color}" stroke-width="{stroke_width}" fill="{fill}"/>'
                    )

            elif tool == "text":
                x = obj.get("x", 0)
                y = obj.get("y", 0)
                text_content = obj.get("text", "")
                font_size = obj.get("font_size", 16)
                # Echapper le texte pour XML
                text_escaped = text_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                svg_elements.append(
                    f'  <text x="{x}" y="{y}" fill="{color}" font-size="{font_size}">{text_escaped}</text>'
                )

            elif tool == "sticky_note":
                x = obj.get("x", 0)
                y = obj.get("y", 0)
                w = obj.get("width", 150)
                h = obj.get("height", 150)
                note_color = obj.get("note_color", "#FFEB3B")
                text_content = obj.get("text", "")
                text_escaped = text_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                svg_elements.append(
                    f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{note_color}" stroke="#999" stroke-width="1"/>'
                )
                svg_elements.append(
                    f'  <text x="{x + 10}" y="{y + 25}" fill="#000" font-size="14">{text_escaped}</text>'
                )

        # Marqueur fleche
        arrow_marker = '''  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <path d="M0,0 L0,6 L9,3 z" fill="currentColor"/>
    </marker>
  </defs>
'''

        svg_content = svg_header + arrow_marker + "\n".join(svg_elements) + "\n</svg>"

        logger.info(
            "whiteboard_exported_svg",
            object_count=len(objects),
            size=len(svg_content)
        )

        return svg_content.encode("utf-8")

    async def _export_png(
        self,
        objects: List[dict],
        width: int,
        height: int,
        background_color: str
    ) -> bytes:
        """Genere un PNG a partir des objets."""
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            logger.warning("pillow_not_available", fallback="svg")
            # Fallback vers SVG si Pillow non disponible
            svg_content = self._export_svg(objects, width, height, background_color)
            return svg_content

        # Creer l'image
        # Convertir la couleur hex en RGB
        bg_color = tuple(int(background_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
        image = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(image)

        for obj in objects:
            tool = obj.get("tool", "pen")
            color = obj.get("color", "#000000")
            stroke_width = obj.get("stroke_width", 2)

            # Convertir la couleur
            try:
                rgb_color = tuple(int(color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
            except Exception:
                rgb_color = (0, 0, 0)

            if tool in ["pen", "highlighter"]:
                points = obj.get("points", [])
                if points and len(points) >= 2:
                    flat_points = [(p[0], p[1]) for p in points]
                    draw.line(flat_points, fill=rgb_color, width=stroke_width)

            elif tool == "line":
                x1 = obj.get("x1", 0)
                y1 = obj.get("y1", 0)
                x2 = obj.get("x2", 100)
                y2 = obj.get("y2", 100)
                draw.line([(x1, y1), (x2, y2)], fill=rgb_color, width=stroke_width)

            elif tool == "shape":
                shape_type = obj.get("shape_type", "rectangle")
                x = obj.get("x", 0)
                y = obj.get("y", 0)
                w = obj.get("width", 100)
                h = obj.get("height", 100)
                fill = obj.get("fill")
                fill_color = None
                if fill and fill != "none":
                    try:
                        fill_color = tuple(int(fill.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
                    except Exception:
                        fill_color = None

                if shape_type == "rectangle":
                    draw.rectangle([x, y, x + w, y + h], outline=rgb_color, fill=fill_color, width=stroke_width)
                elif shape_type == "ellipse":
                    draw.ellipse([x, y, x + w, y + h], outline=rgb_color, fill=fill_color, width=stroke_width)

            elif tool == "text":
                x = obj.get("x", 0)
                y = obj.get("y", 0)
                text_content = obj.get("text", "")
                draw.text((x, y), text_content, fill=rgb_color)

            elif tool == "sticky_note":
                x = obj.get("x", 0)
                y = obj.get("y", 0)
                w = obj.get("width", 150)
                h = obj.get("height", 150)
                note_color = obj.get("note_color", "#FFEB3B")
                text_content = obj.get("text", "")
                try:
                    note_rgb = tuple(int(note_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
                except Exception:
                    note_rgb = (255, 235, 59)
                draw.rectangle([x, y, x + w, y + h], fill=note_rgb, outline=(100, 100, 100))
                draw.text((x + 10, y + 10), text_content, fill=(0, 0, 0))

        # Convertir en bytes
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        png_bytes = buffer.getvalue()

        logger.info(
            "whiteboard_exported_png",
            object_count=len(objects),
            size=len(png_bytes)
        )

        return png_bytes

    # =========================================================================
    # Background Management
    # =========================================================================
    async def set_background(
        self,
        meeting_id: UUID,
        background_type: str = "color",
        value: str = "#FFFFFF"
    ) -> Dict[str, Any]:
        """
        Definit le fond du tableau blanc.

        Args:
            meeting_id: ID de la reunion
            background_type: Type de fond (color, image, grid)
            value: Valeur (couleur hex, URL image, type grille)

        Returns:
            Etat mis a jour
        """
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        whiteboard = self._get_or_create_whiteboard(meeting_id)
        state = json.loads(whiteboard["state"]) if isinstance(whiteboard["state"], str) else whiteboard["state"]

        state["background"] = {
            "type": background_type,
            "value": value
        }

        new_version = whiteboard["version"] + 1
        now = datetime.utcnow()

        update_query = text("""
            UPDATE azalplus.reunion_whiteboard_state
            SET state = :state, version = :version, updated_at = :updated_at
            WHERE id = :id AND tenant_id = :tenant_id
        """)

        self.db.execute(update_query, {
            "id": str(whiteboard["id"]),
            "tenant_id": str(self.tenant_id),
            "state": json.dumps(state),
            "version": new_version,
            "updated_at": now
        })
        self.db.commit()

        logger.info(
            "whiteboard_background_set",
            meeting_id=str(meeting_id),
            background_type=background_type
        )

        return {
            "id": str(whiteboard["id"]),
            "meeting_id": str(meeting_id),
            "background": state["background"],
            "version": new_version
        }

    # =========================================================================
    # Undo / Redo
    # =========================================================================
    async def undo(
        self,
        meeting_id: UUID,
        participant_id: UUID
    ) -> Dict[str, Any]:
        """
        Annule la derniere operation du participant.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant

        Returns:
            Etat mis a jour
        """
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        whiteboard = self._get_or_create_whiteboard(meeting_id)

        # Trouver la derniere operation du participant
        query = text("""
            SELECT * FROM azalplus.reunion_whiteboard_operations
            WHERE whiteboard_id = :whiteboard_id
            AND tenant_id = :tenant_id
            AND participant_id = :participant_id
            AND operation_type != 'undo'
            ORDER BY created_at DESC
            LIMIT 1
        """)
        result = self.db.execute(query, {
            "whiteboard_id": str(whiteboard["id"]),
            "tenant_id": str(self.tenant_id),
            "participant_id": str(participant_id)
        })
        last_op = result.fetchone()

        if not last_op:
            raise ValueError("Aucune operation a annuler")

        # Appliquer l'operation inverse
        state = json.loads(whiteboard["state"]) if isinstance(whiteboard["state"], str) else whiteboard["state"]
        objects = state.get("objects", [])

        op_type = last_op.operation_type
        op_data = json.loads(last_op.data) if last_op.data else {}
        object_id = last_op.object_id

        if op_type == OperationType.ADD.value:
            # Supprimer l'objet ajoute
            objects = [obj for obj in objects if obj.get("id") != object_id]
        elif op_type == OperationType.DELETE.value:
            # Restaurer l'objet supprime
            if op_data.get("deleted_object"):
                objects.append(op_data["deleted_object"])

        state["objects"] = objects
        new_version = whiteboard["version"] + 1
        now = datetime.utcnow()

        # Mettre a jour
        update_query = text("""
            UPDATE azalplus.reunion_whiteboard_state
            SET state = :state, version = :version, updated_at = :updated_at
            WHERE id = :id AND tenant_id = :tenant_id
        """)
        self.db.execute(update_query, {
            "id": str(whiteboard["id"]),
            "tenant_id": str(self.tenant_id),
            "state": json.dumps(state),
            "version": new_version,
            "updated_at": now
        })

        # Enregistrer l'operation undo
        undo_insert = text("""
            INSERT INTO azalplus.reunion_whiteboard_operations
            (id, tenant_id, whiteboard_id, operation_type, data, participant_id, version, created_at)
            VALUES (:id, :tenant_id, :whiteboard_id, 'undo', :data, :participant_id, :version, :created_at)
        """)
        self.db.execute(undo_insert, {
            "id": str(uuid4()),
            "tenant_id": str(self.tenant_id),
            "whiteboard_id": str(whiteboard["id"]),
            "data": json.dumps({"undone_operation_id": str(last_op.id)}),
            "participant_id": str(participant_id),
            "version": new_version,
            "created_at": now
        })
        self.db.commit()

        logger.info(
            "whiteboard_undo",
            meeting_id=str(meeting_id),
            participant_id=str(participant_id),
            undone_operation=str(last_op.id)
        )

        return {
            "id": str(whiteboard["id"]),
            "meeting_id": str(meeting_id),
            "state": state,
            "version": new_version,
            "object_count": len(objects)
        }
