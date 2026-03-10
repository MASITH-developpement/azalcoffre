# =============================================================================
# AZALPLUS - Debug Schemas (Pydantic)
# =============================================================================
"""
Schemas Pydantic pour validation des données debug.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from enum import Enum


# =============================================================================
# Enums
# =============================================================================
class BugStatut(str, Enum):
    NOUVEAU = "nouveau"
    EN_ANALYSE = "en_analyse"
    TESTS_PROPOSES = "tests_proposes"
    EN_TEST = "en_test"
    RESOLU = "resolu"
    FERME = "ferme"


class BugSource(str, Enum):
    TICKET = "ticket"
    CHAT = "chat"
    REPLAY = "replay"


class TestStatut(str, Enum):
    PENDING = "pending"
    OK = "ok"
    KO = "ko"


# =============================================================================
# Bug Schemas
# =============================================================================
class BugCreate(BaseModel):
    """Création d'un bug (mode ticket)."""
    titre: str = Field(..., min_length=5, max_length=200, description="Titre du bug")
    description: str = Field(..., min_length=20, description="Description détaillée du bug")
    logs_texte: Optional[str] = Field(None, description="Logs ou messages d'erreur")
    screenshot_url: Optional[str] = Field(None, max_length=500, description="URL du screenshot")

    @field_validator("titre")
    @classmethod
    def titre_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le titre ne peut pas être vide")
        return v.strip()

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("La description ne peut pas être vide")
        return v.strip()


class BugFromReplay(BaseModel):
    """Création d'un bug depuis une erreur Guardian (mode replay)."""
    guardian_log_id: UUID = Field(..., description="ID du log Guardian")
    titre: Optional[str] = Field(None, max_length=200, description="Titre personnalisé")


class BugResponse(BaseModel):
    """Réponse détaillée d'un bug."""
    id: UUID
    numero: str
    titre: str
    description: str
    logs_texte: Optional[str]
    screenshot_url: Optional[str]
    source: BugSource
    guardian_log_id: Optional[UUID]
    statut: BugStatut
    cree_par: UUID
    created_at: datetime
    updated_at: datetime
    tests_count: int = 0
    tests_ok: int = 0
    tests_ko: int = 0

    class Config:
        from_attributes = True


class BugListItem(BaseModel):
    """Item de liste de bugs (simplifié)."""
    id: UUID
    numero: str
    titre: str
    source: BugSource
    statut: BugStatut
    created_at: datetime
    tests_count: int = 0
    tests_ok: int = 0

    class Config:
        from_attributes = True


class BugListResponse(BaseModel):
    """Liste paginée de bugs."""
    items: List[BugListItem]
    total: int
    skip: int
    limit: int
    has_more: bool


# =============================================================================
# Test Schemas
# =============================================================================
class TestResponse(BaseModel):
    """Test proposé par Simon."""
    id: UUID
    numero: int
    action: str
    resultat_attendu: str
    statut: TestStatut
    commentaire: Optional[str]
    valide_par: Optional[UUID]
    valide_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class TestValidation(BaseModel):
    """Validation d'un test par le debugger."""
    statut: TestStatut = Field(..., description="Résultat: ok ou ko")
    commentaire: Optional[str] = Field(None, max_length=1000, description="Commentaire si KO")

    @field_validator("commentaire")
    @classmethod
    def commentaire_if_ko(cls, v: Optional[str], info) -> Optional[str]:
        # Le commentaire est recommandé si KO mais pas obligatoire
        return v.strip() if v else None


class TestListResponse(BaseModel):
    """Liste des tests d'un bug."""
    bug_id: UUID
    tests: List[TestResponse]
    total: int
    pending: int
    ok: int
    ko: int


# =============================================================================
# Conversation Schemas (Mode Chat)
# =============================================================================
class ChatMessage(BaseModel):
    """Message dans une conversation."""
    role: str  # 'user' ou 'simon'
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSend(BaseModel):
    """Envoi d'un message dans le chat."""
    message: str = Field(..., min_length=1, max_length=2000, description="Message")

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le message ne peut pas être vide")
        return v.strip()


class ChatResponse(BaseModel):
    """Historique de conversation."""
    bug_id: UUID
    messages: List[ChatMessage]
    total: int


# =============================================================================
# Analyse Schemas
# =============================================================================
class AnalyzeRequest(BaseModel):
    """Demande d'analyse à Simon."""
    contexte_supplementaire: Optional[str] = Field(
        None,
        max_length=1000,
        description="Contexte additionnel pour l'analyse"
    )


class AnalyzeResponse(BaseModel):
    """Réponse de Simon après analyse."""
    bug_id: UUID
    statut: BugStatut
    tests: List[TestResponse]
    message: str  # Message de Simon expliquant les tests


# =============================================================================
# Guardian Errors (Mode Replay)
# =============================================================================
class GuardianErrorItem(BaseModel):
    """Erreur Guardian pour le mode replay."""
    id: UUID
    niveau: str
    action: str
    description: str
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class GuardianErrorListResponse(BaseModel):
    """Liste des erreurs Guardian récentes."""
    items: List[GuardianErrorItem]
    total: int


# =============================================================================
# Stats
# =============================================================================
class DebugStats(BaseModel):
    """Statistiques du module debug."""
    total_bugs: int
    bugs_nouveaux: int
    bugs_en_analyse: int
    bugs_en_test: int
    bugs_resolus: int
    bugs_fermes: int
    total_tests: int
    tests_ok: int
    tests_ko: int
    tests_pending: int
