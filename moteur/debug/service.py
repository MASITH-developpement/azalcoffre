# =============================================================================
# AZALPLUS - Debug Service
# =============================================================================
"""
Service métier pour le module Debug.
Gère les bugs, tests, conversations et la connexion avec AutoPilot.
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy import text
import structlog

from ..db import Database
from ..tenant import TenantContext
from .models import (
    BugStatut, BugSource, TestStatut, ConversationRole,
    generate_bug_numero, create_debug_tables
)
from .schemas import (
    BugCreate, BugFromReplay, BugResponse, BugListItem, BugListResponse,
    TestResponse, TestValidation, TestListResponse,
    ChatMessage, ChatResponse, AnalyzeResponse,
    GuardianErrorItem, GuardianErrorListResponse, DebugStats
)
from .simon import simon

logger = structlog.get_logger()


# =============================================================================
# Debug Service
# =============================================================================
class DebugService:
    """Service pour la gestion des bugs et tests."""

    # =========================================================================
    # Initialisation des tables
    # =========================================================================
    @staticmethod
    async def init_tables():
        """Crée les tables debug si nécessaire."""
        await create_debug_tables()

    # =========================================================================
    # Bugs - CRUD
    # =========================================================================
    @staticmethod
    async def create_bug(
        tenant_id: UUID,
        user_id: UUID,
        data: BugCreate,
        source: BugSource = BugSource.TICKET
    ) -> Dict[str, Any]:
        """Crée un nouveau bug."""
        numero = generate_bug_numero(str(tenant_id))

        with Database.get_session() as session:
            result = session.execute(
                text("""
                    INSERT INTO azalplus.debug_bugs
                    (tenant_id, numero, titre, description, logs_texte, screenshot_url, source, cree_par)
                    VALUES (:tenant_id, :numero, :titre, :description, :logs_texte, :screenshot_url, :source, :cree_par)
                    RETURNING id, created_at
                """),
                {
                    "tenant_id": str(tenant_id),
                    "numero": numero,
                    "titre": data.titre,
                    "description": data.description,
                    "logs_texte": data.logs_texte,
                    "screenshot_url": data.screenshot_url,
                    "source": source.value,
                    "cree_par": str(user_id)
                }
            )
            row = result.fetchone()
            session.commit()

        # Audit
        await DebugService._audit(tenant_id, user_id, "bug_created", bug_id=row[0])

        logger.info("debug_bug_created", numero=numero, tenant_id=str(tenant_id))

        return {
            "id": row[0],
            "numero": numero,
            "created_at": row[1]
        }

    @staticmethod
    async def create_bug_from_replay(
        tenant_id: UUID,
        user_id: UUID,
        data: BugFromReplay
    ) -> Dict[str, Any]:
        """Crée un bug depuis une erreur Guardian."""
        # Récupérer l'erreur Guardian
        with Database.get_session() as session:
            result = session.execute(
                text("""
                    SELECT action, description
                    FROM azalplus.guardian_log
                    WHERE id = :log_id AND tenant_id = :tenant_id
                """),
                {"log_id": str(data.guardian_log_id), "tenant_id": str(tenant_id)}
            )
            error = result.fetchone()

        if not error:
            raise ValueError("Erreur Guardian non trouvée")

        numero = generate_bug_numero(str(tenant_id))
        titre = data.titre or f"Erreur: {error[0]}"

        with Database.get_session() as session:
            result = session.execute(
                text("""
                    INSERT INTO azalplus.debug_bugs
                    (tenant_id, numero, titre, description, source, guardian_log_id, cree_par)
                    VALUES (:tenant_id, :numero, :titre, :description, 'replay', :guardian_log_id, :cree_par)
                    RETURNING id, created_at
                """),
                {
                    "tenant_id": str(tenant_id),
                    "numero": numero,
                    "titre": titre,
                    "description": error[1] or "Erreur système",
                    "guardian_log_id": str(data.guardian_log_id),
                    "cree_par": str(user_id)
                }
            )
            row = result.fetchone()
            session.commit()

        await DebugService._audit(tenant_id, user_id, "bug_created_replay", bug_id=row[0])

        return {"id": row[0], "numero": numero, "created_at": row[1]}

    @staticmethod
    async def get_bug(tenant_id: UUID, bug_id: UUID) -> Optional[Dict[str, Any]]:
        """Récupère un bug par son ID."""
        with Database.get_session() as session:
            result = session.execute(
                text("""
                    SELECT b.*,
                           COUNT(t.id) as tests_count,
                           COUNT(CASE WHEN t.statut = 'ok' THEN 1 END) as tests_ok,
                           COUNT(CASE WHEN t.statut = 'ko' THEN 1 END) as tests_ko
                    FROM azalplus.debug_bugs b
                    LEFT JOIN azalplus.debug_tests t ON t.bug_id = b.id
                    WHERE b.id = :bug_id AND b.tenant_id = :tenant_id
                    GROUP BY b.id
                """),
                {"bug_id": str(bug_id), "tenant_id": str(tenant_id)}
            )
            row = result.fetchone()

        if not row:
            return None

        return dict(row._mapping)

    @staticmethod
    async def list_bugs(
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 25,
        statut: Optional[str] = None,
        user_id: Optional[UUID] = None
    ) -> BugListResponse:
        """Liste les bugs avec pagination."""
        filters = ["b.tenant_id = :tenant_id"]
        params = {"tenant_id": str(tenant_id), "skip": skip, "limit": limit}

        if statut:
            filters.append("b.statut = :statut")
            params["statut"] = statut

        if user_id:
            filters.append("b.cree_par = :user_id")
            params["user_id"] = str(user_id)

        where_clause = " AND ".join(filters)

        with Database.get_session() as session:
            # Count
            count_result = session.execute(
                text(f"SELECT COUNT(*) FROM azalplus.debug_bugs b WHERE {where_clause}"),
                params
            )
            total = count_result.scalar()

            # Items
            result = session.execute(
                text(f"""
                    SELECT b.id, b.numero, b.titre, b.source, b.statut, b.created_at,
                           COUNT(t.id) as tests_count,
                           COUNT(CASE WHEN t.statut = 'ok' THEN 1 END) as tests_ok
                    FROM azalplus.debug_bugs b
                    LEFT JOIN azalplus.debug_tests t ON t.bug_id = b.id
                    WHERE {where_clause}
                    GROUP BY b.id
                    ORDER BY b.created_at DESC
                    OFFSET :skip LIMIT :limit
                """),
                params
            )
            rows = result.fetchall()

        items = [
            BugListItem(
                id=row[0], numero=row[1], titre=row[2],
                source=BugSource(row[3]), statut=BugStatut(row[4]),
                created_at=row[5], tests_count=row[6], tests_ok=row[7]
            )
            for row in rows
        ]

        return BugListResponse(
            items=items, total=total, skip=skip, limit=limit,
            has_more=(skip + limit) < total
        )

    @staticmethod
    async def update_bug_statut(
        tenant_id: UUID,
        bug_id: UUID,
        statut: BugStatut,
        user_id: UUID
    ) -> bool:
        """Met à jour le statut d'un bug."""
        with Database.get_session() as session:
            result = session.execute(
                text("""
                    UPDATE azalplus.debug_bugs
                    SET statut = :statut, updated_at = NOW()
                    WHERE id = :bug_id AND tenant_id = :tenant_id
                    RETURNING id
                """),
                {"statut": statut.value, "bug_id": str(bug_id), "tenant_id": str(tenant_id)}
            )
            updated = result.fetchone() is not None
            session.commit()

        if updated:
            await DebugService._audit(tenant_id, user_id, f"bug_statut_{statut.value}", bug_id=bug_id)

        return updated

    # =========================================================================
    # Simon - Analyse
    # =========================================================================
    @staticmethod
    async def analyze_bug(
        tenant_id: UUID,
        bug_id: UUID,
        user_id: UUID
    ) -> AnalyzeResponse:
        """Demande à Simon d'analyser un bug et proposer des tests."""
        bug = await DebugService.get_bug(tenant_id, bug_id)
        if not bug:
            raise ValueError("Bug non trouvé")

        # Appeler Simon
        result = await simon.analyze_bug(
            titre=bug["titre"],
            description=bug["description"],
            logs_texte=bug.get("logs_texte")
        )

        if not result["success"]:
            raise ValueError(result["message"])

        # Sauvegarder les tests proposés
        tests = []
        with Database.get_session() as session:
            for i, test_data in enumerate(result["tests"], 1):
                res = session.execute(
                    text("""
                        INSERT INTO azalplus.debug_tests
                        (bug_id, numero, action, resultat_attendu)
                        VALUES (:bug_id, :numero, :action, :resultat_attendu)
                        RETURNING id, created_at
                    """),
                    {
                        "bug_id": str(bug_id),
                        "numero": test_data.get("numero", i),
                        "action": test_data["action"],
                        "resultat_attendu": test_data["resultat_attendu"]
                    }
                )
                row = res.fetchone()
                tests.append(TestResponse(
                    id=row[0],
                    numero=test_data.get("numero", i),
                    action=test_data["action"],
                    resultat_attendu=test_data["resultat_attendu"],
                    statut=TestStatut.PENDING,
                    commentaire=None,
                    valide_par=None,
                    valide_at=None,
                    created_at=row[1]
                ))

            # Mettre à jour le statut du bug
            session.execute(
                text("""
                    UPDATE azalplus.debug_bugs
                    SET statut = 'tests_proposes', updated_at = NOW()
                    WHERE id = :bug_id
                """),
                {"bug_id": str(bug_id)}
            )
            session.commit()

        await DebugService._audit(tenant_id, user_id, "bug_analyzed", bug_id=bug_id)

        return AnalyzeResponse(
            bug_id=bug_id,
            statut=BugStatut.TESTS_PROPOSES,
            tests=tests,
            message=result["message"]
        )

    # =========================================================================
    # Tests - Validation
    # =========================================================================
    @staticmethod
    async def get_tests(tenant_id: UUID, bug_id: UUID) -> TestListResponse:
        """Récupère les tests d'un bug."""
        # Vérifier que le bug appartient au tenant
        bug = await DebugService.get_bug(tenant_id, bug_id)
        if not bug:
            raise ValueError("Bug non trouvé")

        with Database.get_session() as session:
            result = session.execute(
                text("""
                    SELECT * FROM azalplus.debug_tests
                    WHERE bug_id = :bug_id
                    ORDER BY numero
                """),
                {"bug_id": str(bug_id)}
            )
            rows = result.fetchall()

        tests = [TestResponse(**dict(row._mapping)) for row in rows]
        pending = sum(1 for t in tests if t.statut == TestStatut.PENDING)
        ok = sum(1 for t in tests if t.statut == TestStatut.OK)
        ko = sum(1 for t in tests if t.statut == TestStatut.KO)

        return TestListResponse(
            bug_id=bug_id, tests=tests, total=len(tests),
            pending=pending, ok=ok, ko=ko
        )

    @staticmethod
    async def validate_test(
        tenant_id: UUID,
        test_id: UUID,
        user_id: UUID,
        data: TestValidation
    ) -> bool:
        """Valide un test (OK ou KO)."""
        with Database.get_session() as session:
            # Vérifier que le test appartient à un bug du tenant
            check = session.execute(
                text("""
                    SELECT t.bug_id FROM azalplus.debug_tests t
                    JOIN azalplus.debug_bugs b ON b.id = t.bug_id
                    WHERE t.id = :test_id AND b.tenant_id = :tenant_id
                """),
                {"test_id": str(test_id), "tenant_id": str(tenant_id)}
            )
            row = check.fetchone()
            if not row:
                raise ValueError("Test non trouvé")

            bug_id = row[0]

            # Mettre à jour le test
            session.execute(
                text("""
                    UPDATE azalplus.debug_tests
                    SET statut = :statut, commentaire = :commentaire,
                        valide_par = :valide_par, valide_at = NOW()
                    WHERE id = :test_id
                """),
                {
                    "statut": data.statut.value,
                    "commentaire": data.commentaire,
                    "valide_par": str(user_id),
                    "test_id": str(test_id)
                }
            )

            # Mettre à jour le statut du bug si nécessaire
            session.execute(
                text("""
                    UPDATE azalplus.debug_bugs
                    SET statut = 'en_test', updated_at = NOW()
                    WHERE id = :bug_id AND statut = 'tests_proposes'
                """),
                {"bug_id": str(bug_id)}
            )
            session.commit()

        await DebugService._audit(tenant_id, user_id, f"test_validated_{data.statut.value}", bug_id=bug_id)

        # Vérifier si tous les tests sont validés
        await DebugService._check_bug_completion(tenant_id, bug_id, user_id)

        return True

    @staticmethod
    async def _check_bug_completion(tenant_id: UUID, bug_id: UUID, user_id: UUID):
        """Vérifie si tous les tests sont validés et agit en conséquence."""
        tests = await DebugService.get_tests(tenant_id, bug_id)

        if tests.pending > 0:
            return  # Encore des tests en attente

        if tests.ko == 0:
            # Tous les tests OK → Bug résolu
            await DebugService.update_bug_statut(tenant_id, bug_id, BugStatut.RESOLU, user_id)
            logger.info("debug_bug_resolved", bug_id=str(bug_id))
        else:
            # Des tests KO → Envoyer à AutoPilot pour correction
            await DebugService._send_to_autopilot(tenant_id, bug_id)

    @staticmethod
    async def _send_to_autopilot(tenant_id: UUID, bug_id: UUID):
        """Envoie un bug confirmé à AutoPilot pour correction."""
        bug = await DebugService.get_bug(tenant_id, bug_id)
        tests = await DebugService.get_tests(tenant_id, bug_id)

        failed_tests = [t for t in tests.tests if t.statut == TestStatut.KO]

        # Préparer les données pour AutoPilot
        fix_request = {
            "source": "simon",
            "bug_id": str(bug_id),
            "bug_numero": bug["numero"],
            "titre": bug["titre"],
            "description": bug["description"],
            "failed_tests": [
                {
                    "action": t.action,
                    "resultat_attendu": t.resultat_attendu,
                    "commentaire": t.commentaire
                }
                for t in failed_tests
            ],
            "tenant_id": str(tenant_id)
        }

        # Envoyer à AutoPilot via Redis (file d'attente)
        redis = Database.get_redis()
        await redis.lpush("autopilot:fix_requests", json.dumps(fix_request))

        logger.info(
            "debug_bug_sent_to_autopilot",
            bug_id=str(bug_id),
            failed_tests=len(failed_tests)
        )

    # =========================================================================
    # Chat
    # =========================================================================
    @staticmethod
    async def send_chat_message(
        tenant_id: UUID,
        bug_id: UUID,
        user_id: UUID,
        message: str
    ) -> Dict[str, Any]:
        """Envoie un message dans le chat et obtient la réponse de Simon."""
        bug = await DebugService.get_bug(tenant_id, bug_id)
        if not bug:
            raise ValueError("Bug non trouvé")

        # Récupérer l'historique
        with Database.get_session() as session:
            result = session.execute(
                text("""
                    SELECT role, message FROM azalplus.debug_conversations
                    WHERE bug_id = :bug_id
                    ORDER BY created_at
                """),
                {"bug_id": str(bug_id)}
            )
            history = [{"role": row[0], "message": row[1]} for row in result.fetchall()]

        # Sauvegarder le message utilisateur
        with Database.get_session() as session:
            session.execute(
                text("""
                    INSERT INTO azalplus.debug_conversations (bug_id, role, message)
                    VALUES (:bug_id, 'user', :message)
                """),
                {"bug_id": str(bug_id), "message": message}
            )
            session.commit()

        # Appeler Simon
        result = await simon.chat(
            titre=bug["titre"],
            description=bug["description"],
            conversation_history=history,
            user_message=message
        )

        # Sauvegarder la réponse de Simon
        with Database.get_session() as session:
            session.execute(
                text("""
                    INSERT INTO azalplus.debug_conversations (bug_id, role, message)
                    VALUES (:bug_id, 'simon', :message)
                """),
                {"bug_id": str(bug_id), "message": result["message"]}
            )
            session.commit()

        # Si Simon a proposé des tests, les sauvegarder
        if result.get("tests"):
            await DebugService._save_tests_from_chat(bug_id, result["tests"])
            await DebugService.update_bug_statut(
                tenant_id, bug_id, BugStatut.TESTS_PROPOSES, user_id
            )

        await DebugService._audit(tenant_id, user_id, "chat_message", bug_id=bug_id)

        return result

    @staticmethod
    async def _save_tests_from_chat(bug_id: UUID, tests: List[Dict[str, Any]]):
        """Sauvegarde les tests proposés via le chat."""
        with Database.get_session() as session:
            for i, test_data in enumerate(tests, 1):
                session.execute(
                    text("""
                        INSERT INTO azalplus.debug_tests
                        (bug_id, numero, action, resultat_attendu)
                        VALUES (:bug_id, :numero, :action, :resultat_attendu)
                        ON CONFLICT (bug_id, numero) DO NOTHING
                    """),
                    {
                        "bug_id": str(bug_id),
                        "numero": test_data.get("numero", i),
                        "action": test_data["action"],
                        "resultat_attendu": test_data["resultat_attendu"]
                    }
                )
            session.commit()

    @staticmethod
    async def get_chat_history(tenant_id: UUID, bug_id: UUID) -> ChatResponse:
        """Récupère l'historique de conversation."""
        bug = await DebugService.get_bug(tenant_id, bug_id)
        if not bug:
            raise ValueError("Bug non trouvé")

        with Database.get_session() as session:
            result = session.execute(
                text("""
                    SELECT role, message, created_at
                    FROM azalplus.debug_conversations
                    WHERE bug_id = :bug_id
                    ORDER BY created_at
                """),
                {"bug_id": str(bug_id)}
            )
            rows = result.fetchall()

        messages = [
            ChatMessage(role=row[0], message=row[1], created_at=row[2])
            for row in rows
        ]

        return ChatResponse(bug_id=bug_id, messages=messages, total=len(messages))

    # =========================================================================
    # Guardian Errors (Mode Replay)
    # =========================================================================
    @staticmethod
    async def get_guardian_errors(
        tenant_id: UUID,
        limit: int = 50
    ) -> GuardianErrorListResponse:
        """Récupère les erreurs Guardian récentes pour le mode replay."""
        with Database.get_session() as session:
            result = session.execute(
                text("""
                    SELECT id, niveau, action, description, ip_address, created_at
                    FROM azalplus.guardian_log
                    WHERE tenant_id = :tenant_id
                    AND niveau IN ('ERROR', 'CRITICAL', 'WARNING')
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"tenant_id": str(tenant_id), "limit": limit}
            )
            rows = result.fetchall()

        items = [
            GuardianErrorItem(
                id=row[0], niveau=row[1], action=row[2],
                description=row[3], ip_address=row[4], created_at=row[5]
            )
            for row in rows
        ]

        return GuardianErrorListResponse(items=items, total=len(items))

    # =========================================================================
    # Stats
    # =========================================================================
    @staticmethod
    async def get_stats(tenant_id: UUID) -> DebugStats:
        """Récupère les statistiques du module debug."""
        with Database.get_session() as session:
            # Stats bugs
            bugs_result = session.execute(
                text("""
                    SELECT statut, COUNT(*)
                    FROM azalplus.debug_bugs
                    WHERE tenant_id = :tenant_id
                    GROUP BY statut
                """),
                {"tenant_id": str(tenant_id)}
            )
            bugs_by_statut = {row[0]: row[1] for row in bugs_result.fetchall()}

            # Stats tests
            tests_result = session.execute(
                text("""
                    SELECT t.statut, COUNT(*)
                    FROM azalplus.debug_tests t
                    JOIN azalplus.debug_bugs b ON b.id = t.bug_id
                    WHERE b.tenant_id = :tenant_id
                    GROUP BY t.statut
                """),
                {"tenant_id": str(tenant_id)}
            )
            tests_by_statut = {row[0]: row[1] for row in tests_result.fetchall()}

        return DebugStats(
            total_bugs=sum(bugs_by_statut.values()),
            bugs_nouveaux=bugs_by_statut.get("nouveau", 0),
            bugs_en_analyse=bugs_by_statut.get("en_analyse", 0),
            bugs_en_test=bugs_by_statut.get("en_test", 0),
            bugs_resolus=bugs_by_statut.get("resolu", 0),
            bugs_fermes=bugs_by_statut.get("ferme", 0),
            total_tests=sum(tests_by_statut.values()),
            tests_ok=tests_by_statut.get("ok", 0),
            tests_ko=tests_by_statut.get("ko", 0),
            tests_pending=tests_by_statut.get("pending", 0)
        )

    # =========================================================================
    # Audit
    # =========================================================================
    @staticmethod
    async def _audit(
        tenant_id: UUID,
        user_id: UUID,
        action: str,
        bug_id: Optional[UUID] = None,
        details: Optional[Dict] = None,
        ip_address: Optional[str] = None
    ):
        """Enregistre une action dans l'audit."""
        with Database.get_session() as session:
            session.execute(
                text("""
                    INSERT INTO azalplus.debug_audit
                    (tenant_id, user_id, action, bug_id, details, ip_address)
                    VALUES (:tenant_id, :user_id, :action, :bug_id, :details, :ip_address)
                """),
                {
                    "tenant_id": str(tenant_id),
                    "user_id": str(user_id),
                    "action": action,
                    "bug_id": str(bug_id) if bug_id else None,
                    "details": json.dumps(details) if details else None,
                    "ip_address": ip_address
                }
            )
            session.commit()


# Import json en haut du fichier manquant, ajoutons-le
import json
