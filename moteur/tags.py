# =============================================================================
# AZALPLUS - Tags Service
# =============================================================================
"""
Service de gestion des tags pour AZALPLUS.
Permet d'organiser les entites avec des etiquettes colorees.
Support multi-tenant obligatoire.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
from datetime import datetime
import structlog
import re

from .db import Database
from .config import settings

logger = structlog.get_logger()


# =============================================================================
# Tag Service
# =============================================================================
class TagService:
    """Service de gestion des tags."""

    # Couleurs predefinies
    PREDEFINED_COLORS = [
        {"nom": "Bleu", "couleur": "#3B82F6", "couleur_texte": "#FFFFFF"},
        {"nom": "Vert", "couleur": "#22C55E", "couleur_texte": "#FFFFFF"},
        {"nom": "Jaune", "couleur": "#F59E0B", "couleur_texte": "#000000"},
        {"nom": "Rouge", "couleur": "#EF4444", "couleur_texte": "#FFFFFF"},
        {"nom": "Violet", "couleur": "#8B5CF6", "couleur_texte": "#FFFFFF"},
        {"nom": "Rose", "couleur": "#EC4899", "couleur_texte": "#FFFFFF"},
        {"nom": "Cyan", "couleur": "#06B6D4", "couleur_texte": "#FFFFFF"},
        {"nom": "Orange", "couleur": "#F97316", "couleur_texte": "#FFFFFF"},
        {"nom": "Gris", "couleur": "#6B7280", "couleur_texte": "#FFFFFF"},
        {"nom": "Noir", "couleur": "#1F2937", "couleur_texte": "#FFFFFF"},
    ]

    # Tags systeme par defaut
    DEFAULT_TAGS = [
        {"nom": "VIP", "couleur": "#F59E0B", "couleur_texte": "#000000", "groupe": "Client", "global": False, "module": "Clients", "is_system": True},
        {"nom": "Urgent", "couleur": "#EF4444", "couleur_texte": "#FFFFFF", "groupe": "Priorite", "global": True, "is_system": True},
        {"nom": "A relancer", "couleur": "#F97316", "couleur_texte": "#FFFFFF", "groupe": "Suivi", "global": True, "is_system": True},
        {"nom": "Nouveau", "couleur": "#22C55E", "couleur_texte": "#FFFFFF", "groupe": "Statut", "global": True, "is_system": True},
        {"nom": "En attente", "couleur": "#6B7280", "couleur_texte": "#FFFFFF", "groupe": "Statut", "global": True, "is_system": True},
        {"nom": "Important", "couleur": "#8B5CF6", "couleur_texte": "#FFFFFF", "groupe": "Priorite", "global": True, "is_system": True},
    ]

    @classmethod
    def slugify(cls, text: str) -> str:
        """Genere un slug URL-friendly depuis un texte."""
        slug = text.lower().strip()
        slug = re.sub(r'[àâäáã]', 'a', slug)
        slug = re.sub(r'[éèêë]', 'e', slug)
        slug = re.sub(r'[îïíì]', 'i', slug)
        slug = re.sub(r'[ôöóòõ]', 'o', slug)
        slug = re.sub(r'[ûüúù]', 'u', slug)
        slug = re.sub(r'[ç]', 'c', slug)
        slug = re.sub(r'[^a-z0-9\-]', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        slug = slug.strip('-')
        return slug

    @classmethod
    def create_tag(
        cls,
        tenant_id: UUID,
        nom: str,
        couleur: str = "#6366F1",
        couleur_texte: str = "#FFFFFF",
        module: Optional[str] = None,
        groupe: Optional[str] = None,
        user_id: Optional[UUID] = None,
        is_system: bool = False,
        keywords: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Cree un nouveau tag.

        Args:
            tenant_id: ID du tenant (obligatoire)
            nom: Nom du tag
            couleur: Couleur hexadecimale
            couleur_texte: Couleur du texte
            module: Module specifique (null = global)
            groupe: Groupe de tags
            user_id: Utilisateur createur
            is_system: Tag systeme (non supprimable)
            keywords: Mots-cles pour auto-suggestion

        Returns:
            Tag cree avec son ID
        """
        slug = cls.slugify(nom)

        data = {
            "nom": nom,
            "slug": slug,
            "couleur": couleur,
            "couleur_texte": couleur_texte,
            "module": module,
            "global": module is None,
            "groupe": groupe,
            "is_system": is_system,
            "is_active": True,
            "usage_count": 0,
            "keywords": keywords or [],
            "created_by": str(user_id) if user_id else None,
            "created_at": datetime.utcnow().isoformat()
        }

        tag = Database.insert("tags", tenant_id, data, user_id)

        logger.info(
            "tag_created",
            tenant_id=str(tenant_id),
            tag_id=tag.get("id"),
            nom=nom
        )

        return tag

    @classmethod
    def get_all_tags(
        cls,
        tenant_id: UUID,
        module: Optional[str] = None,
        groupe: Optional[str] = None,
        include_global: bool = True,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Recupere tous les tags.

        Args:
            tenant_id: ID du tenant
            module: Filtrer par module specifique
            groupe: Filtrer par groupe
            include_global: Inclure les tags globaux
            active_only: Uniquement les tags actifs

        Returns:
            Liste des tags
        """
        tags = Database.query(
            "tags",
            tenant_id,
            limit=1000,
            order_by="groupe ASC, ordre ASC, nom ASC"
        )

        # Filtrer
        filtered = []
        for tag in tags:
            # Filtre actif
            if active_only and not tag.get("is_active", True):
                continue

            # Filtre module
            tag_module = tag.get("module")
            is_global = tag.get("global", True)

            if module:
                if not (tag_module == module or (include_global and is_global)):
                    continue
            elif not include_global and not is_global:
                continue

            # Filtre groupe
            if groupe and tag.get("groupe") != groupe:
                continue

            filtered.append(tag)

        return filtered

    @classmethod
    def get_tag_by_id(cls, tenant_id: UUID, tag_id: UUID) -> Optional[Dict[str, Any]]:
        """Recupere un tag par son ID."""
        return Database.get_by_id("tags", tenant_id, tag_id)

    @classmethod
    def get_tag_by_slug(cls, tenant_id: UUID, slug: str) -> Optional[Dict[str, Any]]:
        """Recupere un tag par son slug."""
        tags = Database.query("tags", tenant_id, limit=1)
        for tag in tags:
            if tag.get("slug") == slug:
                return tag
        return None

    @classmethod
    def update_tag(
        cls,
        tenant_id: UUID,
        tag_id: UUID,
        data: Dict[str, Any],
        user_id: Optional[UUID] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Met a jour un tag.

        Args:
            tenant_id: ID du tenant
            tag_id: ID du tag
            data: Donnees a mettre a jour
            user_id: Utilisateur effectuant la modification

        Returns:
            Tag mis a jour ou None si non trouve
        """
        # Verifier que le tag existe
        existing = cls.get_tag_by_id(tenant_id, tag_id)
        if not existing:
            return None

        # Ne pas permettre la modification des tags systeme (sauf couleur)
        if existing.get("is_system"):
            allowed_fields = {"couleur", "couleur_texte", "icone", "ordre", "groupe"}
            data = {k: v for k, v in data.items() if k in allowed_fields}

        # Regenerer le slug si le nom change
        if "nom" in data:
            data["slug"] = cls.slugify(data["nom"])

        # Mettre a jour le global si module change
        if "module" in data:
            data["global"] = data["module"] is None

        data["updated_at"] = datetime.utcnow().isoformat()

        tag = Database.update("tags", tenant_id, tag_id, data, user_id)

        logger.info(
            "tag_updated",
            tenant_id=str(tenant_id),
            tag_id=str(tag_id)
        )

        return tag

    @classmethod
    def delete_tag(
        cls,
        tenant_id: UUID,
        tag_id: UUID,
        force: bool = False
    ) -> bool:
        """
        Supprime un tag.

        Args:
            tenant_id: ID du tenant
            tag_id: ID du tag
            force: Forcer la suppression meme si tag systeme

        Returns:
            True si supprime, False sinon
        """
        existing = cls.get_tag_by_id(tenant_id, tag_id)
        if not existing:
            return False

        # Interdire la suppression des tags systeme sauf si force
        if existing.get("is_system") and not force:
            logger.warning(
                "cannot_delete_system_tag",
                tenant_id=str(tenant_id),
                tag_id=str(tag_id)
            )
            return False

        # Supprimer les associations entity_tags
        cls._remove_all_tag_associations(tenant_id, tag_id)

        # Supprimer le tag
        success = Database.soft_delete("tags", tenant_id, tag_id)

        if success:
            logger.info(
                "tag_deleted",
                tenant_id=str(tenant_id),
                tag_id=str(tag_id)
            )

        return success

    @classmethod
    def merge_tags(
        cls,
        tenant_id: UUID,
        source_tag_ids: List[UUID],
        target_tag_id: UUID,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Fusionne plusieurs tags en un seul.

        Toutes les associations des tags sources sont transferees vers le tag cible.
        Les tags sources sont ensuite supprimes.

        Args:
            tenant_id: ID du tenant
            source_tag_ids: IDs des tags a fusionner
            target_tag_id: ID du tag cible
            user_id: Utilisateur effectuant l'operation

        Returns:
            Resultat de la fusion
        """
        target = cls.get_tag_by_id(tenant_id, target_tag_id)
        if not target:
            raise ValueError("Tag cible non trouve")

        merged_count = 0
        deleted_count = 0

        for source_id in source_tag_ids:
            if source_id == target_tag_id:
                continue

            source = cls.get_tag_by_id(tenant_id, source_id)
            if not source:
                continue

            # Transferer les associations
            associations = cls.get_tag_associations(tenant_id, source_id)
            for assoc in associations:
                # Ajouter au tag cible si pas deja present
                cls.apply_tag(
                    tenant_id=tenant_id,
                    tag_id=target_tag_id,
                    entity_type=assoc["entity_type"],
                    entity_id=UUID(assoc["entity_id"]),
                    user_id=user_id
                )
                merged_count += 1

            # Supprimer le tag source
            if cls.delete_tag(tenant_id, source_id, force=True):
                deleted_count += 1

        # Mettre a jour le compteur du tag cible
        cls._update_usage_count(tenant_id, target_tag_id)

        logger.info(
            "tags_merged",
            tenant_id=str(tenant_id),
            target_tag_id=str(target_tag_id),
            merged_count=merged_count,
            deleted_count=deleted_count
        )

        return {
            "status": "success",
            "merged_associations": merged_count,
            "deleted_tags": deleted_count,
            "target_tag": target
        }

    # =========================================================================
    # Association Tags <-> Entites
    # =========================================================================

    @classmethod
    def apply_tag(
        cls,
        tenant_id: UUID,
        tag_id: UUID,
        entity_type: str,
        entity_id: UUID,
        user_id: Optional[UUID] = None,
        source: str = "MANUAL"
    ) -> Dict[str, Any]:
        """
        Applique un tag a une entite.

        Args:
            tenant_id: ID du tenant
            tag_id: ID du tag
            entity_type: Type d'entite (Client, Produit, etc.)
            entity_id: ID de l'entite
            user_id: Utilisateur ayant applique le tag
            source: Source de l'application (MANUAL, AUTO, IMPORT, API)

        Returns:
            Association creee
        """
        # Verifier que le tag existe
        tag = cls.get_tag_by_id(tenant_id, tag_id)
        if not tag:
            raise ValueError("Tag non trouve")

        # Verifier que le tag est compatible avec le type d'entite
        tag_module = tag.get("module")
        if tag_module and tag_module != entity_type and not tag.get("global"):
            raise ValueError(f"Tag non compatible avec le module {entity_type}")

        # Verifier si l'association existe deja
        existing = cls._get_association(tenant_id, tag_id, entity_type, entity_id)
        if existing:
            return existing

        # Creer l'association
        data = {
            "tag_id": str(tag_id),
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "applied_by": str(user_id) if user_id else None,
            "applied_at": datetime.utcnow().isoformat(),
            "source": source
        }

        association = Database.insert("entity_tags", tenant_id, data, user_id)

        # Mettre a jour le compteur du tag
        cls._update_usage_count(tenant_id, tag_id)

        # Mettre a jour le champ tags de l'entite
        cls._sync_entity_tags(tenant_id, entity_type, entity_id)

        logger.info(
            "tag_applied",
            tenant_id=str(tenant_id),
            tag_id=str(tag_id),
            entity_type=entity_type,
            entity_id=str(entity_id)
        )

        return association

    @classmethod
    def remove_tag(
        cls,
        tenant_id: UUID,
        tag_id: UUID,
        entity_type: str,
        entity_id: UUID
    ) -> bool:
        """
        Retire un tag d'une entite.

        Args:
            tenant_id: ID du tenant
            tag_id: ID du tag
            entity_type: Type d'entite
            entity_id: ID de l'entite

        Returns:
            True si retire, False sinon
        """
        # Trouver l'association
        associations = Database.query("entity_tags", tenant_id, limit=1000)
        for assoc in associations:
            if (assoc.get("tag_id") == str(tag_id) and
                assoc.get("entity_type") == entity_type and
                assoc.get("entity_id") == str(entity_id)):

                # Supprimer l'association
                Database.soft_delete("entity_tags", tenant_id, UUID(assoc["id"]))

                # Mettre a jour le compteur du tag
                cls._update_usage_count(tenant_id, tag_id)

                # Mettre a jour le champ tags de l'entite
                cls._sync_entity_tags(tenant_id, entity_type, entity_id)

                logger.info(
                    "tag_removed",
                    tenant_id=str(tenant_id),
                    tag_id=str(tag_id),
                    entity_type=entity_type,
                    entity_id=str(entity_id)
                )

                return True

        return False

    @classmethod
    def get_entity_tags(
        cls,
        tenant_id: UUID,
        entity_type: str,
        entity_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Recupere tous les tags d'une entite.

        Args:
            tenant_id: ID du tenant
            entity_type: Type d'entite
            entity_id: ID de l'entite

        Returns:
            Liste des tags avec leurs details
        """
        associations = Database.query("entity_tags", tenant_id, limit=1000)

        tag_ids = []
        for assoc in associations:
            if (assoc.get("entity_type") == entity_type and
                assoc.get("entity_id") == str(entity_id)):
                tag_ids.append(UUID(assoc.get("tag_id")))

        # Recuperer les details des tags
        tags = []
        for tag_id in tag_ids:
            tag = cls.get_tag_by_id(tenant_id, tag_id)
            if tag:
                tags.append(tag)

        return tags

    @classmethod
    def get_tag_associations(
        cls,
        tenant_id: UUID,
        tag_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Recupere toutes les associations d'un tag.

        Args:
            tenant_id: ID du tenant
            tag_id: ID du tag

        Returns:
            Liste des associations
        """
        associations = Database.query("entity_tags", tenant_id, limit=1000)
        return [a for a in associations if a.get("tag_id") == str(tag_id)]

    @classmethod
    def get_entities_by_tag(
        cls,
        tenant_id: UUID,
        tag_id: UUID,
        entity_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Recupere toutes les entites associees a un tag.

        Args:
            tenant_id: ID du tenant
            tag_id: ID du tag
            entity_type: Filtrer par type d'entite

        Returns:
            Liste des entites avec leur type et ID
        """
        associations = cls.get_tag_associations(tenant_id, tag_id)

        if entity_type:
            associations = [a for a in associations if a.get("entity_type") == entity_type]

        return associations

    @classmethod
    def set_entity_tags(
        cls,
        tenant_id: UUID,
        entity_type: str,
        entity_id: UUID,
        tag_ids: List[UUID],
        user_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Definit les tags d'une entite (remplace les tags existants).

        Args:
            tenant_id: ID du tenant
            entity_type: Type d'entite
            entity_id: ID de l'entite
            tag_ids: Liste des IDs de tags a appliquer
            user_id: Utilisateur effectuant l'operation

        Returns:
            Liste des tags appliques
        """
        # Recuperer les tags actuels
        current_tags = cls.get_entity_tags(tenant_id, entity_type, entity_id)
        current_tag_ids = {UUID(t["id"]) for t in current_tags}

        # Tags a ajouter
        tags_to_add = set(tag_ids) - current_tag_ids

        # Tags a retirer
        tags_to_remove = current_tag_ids - set(tag_ids)

        # Appliquer les modifications
        for tag_id in tags_to_remove:
            cls.remove_tag(tenant_id, tag_id, entity_type, entity_id)

        for tag_id in tags_to_add:
            try:
                cls.apply_tag(tenant_id, tag_id, entity_type, entity_id, user_id)
            except ValueError as e:
                logger.warning("cannot_apply_tag", error=str(e))

        return cls.get_entity_tags(tenant_id, entity_type, entity_id)

    # =========================================================================
    # Suggestions
    # =========================================================================

    @classmethod
    def get_recent_tags(
        cls,
        tenant_id: UUID,
        user_id: UUID,
        module: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Recupere les tags recemment utilises par un utilisateur.

        Args:
            tenant_id: ID du tenant
            user_id: ID de l'utilisateur
            module: Filtrer par module
            limit: Nombre maximum de tags

        Returns:
            Liste des tags recents
        """
        associations = Database.query(
            "entity_tags",
            tenant_id,
            limit=100,
            order_by="applied_at DESC"
        )

        # Filtrer par utilisateur
        user_associations = [a for a in associations if a.get("applied_by") == str(user_id)]

        # Recuperer les tags uniques
        seen_tags = set()
        recent_tags = []

        for assoc in user_associations:
            tag_id = UUID(assoc.get("tag_id"))
            if tag_id not in seen_tags:
                tag = cls.get_tag_by_id(tenant_id, tag_id)
                if tag:
                    # Filtrer par module si specifie
                    if module:
                        tag_module = tag.get("module")
                        if tag_module and tag_module != module and not tag.get("global"):
                            continue

                    recent_tags.append(tag)
                    seen_tags.add(tag_id)

                    if len(recent_tags) >= limit:
                        break

        return recent_tags

    @classmethod
    def get_popular_tags(
        cls,
        tenant_id: UUID,
        module: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Recupere les tags les plus populaires.

        Args:
            tenant_id: ID du tenant
            module: Filtrer par module
            limit: Nombre maximum de tags

        Returns:
            Liste des tags populaires (tries par usage_count)
        """
        tags = cls.get_all_tags(tenant_id, module=module, include_global=True)

        # Trier par usage_count
        sorted_tags = sorted(tags, key=lambda t: t.get("usage_count", 0), reverse=True)

        return sorted_tags[:limit]

    @classmethod
    def suggest_tags(
        cls,
        tenant_id: UUID,
        entity_type: str,
        entity_data: Dict[str, Any],
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Suggere des tags pour une entite basee sur son contenu.

        Args:
            tenant_id: ID du tenant
            entity_type: Type d'entite
            entity_data: Donnees de l'entite
            limit: Nombre maximum de suggestions

        Returns:
            Liste des tags suggeres
        """
        suggestions = []

        # Recuperer tous les tags disponibles pour ce module
        tags = cls.get_all_tags(tenant_id, module=entity_type, include_global=True)

        # Extraire le texte de l'entite
        text_fields = ["nom", "name", "description", "notes", "titre", "objet"]
        entity_text = " ".join([
            str(entity_data.get(f, "")) for f in text_fields
        ]).lower()

        # Verifier les mots-cles de chaque tag
        for tag in tags:
            keywords = tag.get("keywords", [])
            if keywords:
                for keyword in keywords:
                    if keyword.lower() in entity_text:
                        suggestions.append(tag)
                        break

            # Verifier aussi le nom du tag
            if tag.get("nom", "").lower() in entity_text:
                if tag not in suggestions:
                    suggestions.append(tag)

        # Verifier les regles d'application automatique
        for tag in tags:
            rules = tag.get("auto_apply_rules", {})
            if rules:
                field = rules.get("field")
                operator = rules.get("operator")
                value = rules.get("value")

                if field and operator and value is not None:
                    entity_value = entity_data.get(field)
                    if entity_value is not None:
                        try:
                            if operator == ">" and float(entity_value) > float(value):
                                if tag not in suggestions:
                                    suggestions.append(tag)
                            elif operator == "<" and float(entity_value) < float(value):
                                if tag not in suggestions:
                                    suggestions.append(tag)
                            elif operator == "=" and str(entity_value) == str(value):
                                if tag not in suggestions:
                                    suggestions.append(tag)
                            elif operator == "contains" and str(value).lower() in str(entity_value).lower():
                                if tag not in suggestions:
                                    suggestions.append(tag)
                        except (ValueError, TypeError):
                            pass

        return suggestions[:limit]

    # =========================================================================
    # Initialisation
    # =========================================================================

    @classmethod
    def initialize_default_tags(cls, tenant_id: UUID, user_id: Optional[UUID] = None):
        """
        Initialise les tags par defaut pour un tenant.

        Args:
            tenant_id: ID du tenant
            user_id: Utilisateur createur
        """
        for tag_data in cls.DEFAULT_TAGS:
            # Verifier si le tag existe deja
            existing = cls.get_tag_by_slug(tenant_id, cls.slugify(tag_data["nom"]))
            if existing:
                continue

            cls.create_tag(
                tenant_id=tenant_id,
                nom=tag_data["nom"],
                couleur=tag_data["couleur"],
                couleur_texte=tag_data["couleur_texte"],
                module=tag_data.get("module"),
                groupe=tag_data.get("groupe"),
                user_id=user_id,
                is_system=tag_data.get("is_system", False)
            )

        logger.info(
            "default_tags_initialized",
            tenant_id=str(tenant_id)
        )

    # =========================================================================
    # Methodes privees
    # =========================================================================

    @classmethod
    def _get_association(
        cls,
        tenant_id: UUID,
        tag_id: UUID,
        entity_type: str,
        entity_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Recupere une association tag-entite."""
        associations = Database.query("entity_tags", tenant_id, limit=1000)
        for assoc in associations:
            if (assoc.get("tag_id") == str(tag_id) and
                assoc.get("entity_type") == entity_type and
                assoc.get("entity_id") == str(entity_id)):
                return assoc
        return None

    @classmethod
    def _remove_all_tag_associations(cls, tenant_id: UUID, tag_id: UUID):
        """Supprime toutes les associations d'un tag."""
        associations = cls.get_tag_associations(tenant_id, tag_id)
        for assoc in associations:
            Database.soft_delete("entity_tags", tenant_id, UUID(assoc["id"]))

    @classmethod
    def _update_usage_count(cls, tenant_id: UUID, tag_id: UUID):
        """Met a jour le compteur d'utilisation d'un tag."""
        associations = cls.get_tag_associations(tenant_id, tag_id)
        count = len(associations)

        Database.update("tags", tenant_id, tag_id, {
            "usage_count": count,
            "last_used_at": datetime.utcnow().isoformat() if count > 0 else None
        })

    @classmethod
    def _sync_entity_tags(cls, tenant_id: UUID, entity_type: str, entity_id: UUID):
        """
        Synchronise le champ tags de l'entite avec les associations.
        Met a jour les champs tags (liste d'IDs) et tags_display (noms).
        """
        tags = cls.get_entity_tags(tenant_id, entity_type, entity_id)

        tag_ids = [t.get("id") for t in tags]
        tags_display = ", ".join([t.get("nom", "") for t in tags])

        # Mettre a jour l'entite
        Database.update(
            entity_type.lower(),
            tenant_id,
            entity_id,
            {
                "tags": tag_ids,
                "tags_display": tags_display
            }
        )
