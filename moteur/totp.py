# =============================================================================
# AZALPLUS - Two-Factor Authentication (TOTP)
# =============================================================================
"""
Service d'authentification a deux facteurs (2FA) base sur TOTP.

Fonctionnalites :
- Generation de secrets TOTP
- Generation de QR codes pour les applications d'authentification
- Verification des codes TOTP
- Generation et gestion des codes de secours

Utilise pyotp pour la compatibilite avec Google Authenticator, Authy, etc.
"""

import pyotp
import qrcode
import qrcode.image.svg
import secrets
import hashlib
import base64
from io import BytesIO
from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import structlog

from .config import settings
from .db import Database

logger = structlog.get_logger()

# =============================================================================
# Encryption Helper
# =============================================================================
def _get_fernet() -> Fernet:
    """Retourne une instance Fernet pour le chiffrement."""
    key = settings.ENCRYPTION_KEY or settings.SECRET_KEY
    # Derive a 32-byte key from the secret
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"azalplus_totp_salt",  # Salt fixe pour reproductibilite
        iterations=100000,
    )
    derived_key = base64.urlsafe_b64encode(kdf.derive(key.encode()))
    return Fernet(derived_key)


def encrypt_secret(secret: str) -> str:
    """Chiffre un secret TOTP."""
    fernet = _get_fernet()
    encrypted = fernet.encrypt(secret.encode())
    return base64.urlsafe_b64encode(encrypted).decode()


def decrypt_secret(encrypted_secret: str) -> str:
    """Dechiffre un secret TOTP."""
    fernet = _get_fernet()
    encrypted = base64.urlsafe_b64decode(encrypted_secret.encode())
    return fernet.decrypt(encrypted).decode()


# =============================================================================
# TOTP Service
# =============================================================================
class TOTPService:
    """
    Service de gestion TOTP (Time-based One-Time Password).

    Compatible avec :
    - Google Authenticator
    - Authy
    - Microsoft Authenticator
    - 1Password
    - etc.
    """

    ISSUER = "AZALPLUS"
    BACKUP_CODE_LENGTH = 8
    BACKUP_CODE_COUNT = 10

    @classmethod
    def generate_secret(cls) -> str:
        """
        Genere un nouveau secret TOTP.

        Returns:
            Secret en base32 (format standard TOTP)
        """
        return pyotp.random_base32()

    @classmethod
    def generate_qr_code(cls, secret: str, email: str) -> str:
        """
        Genere un QR code pour configurer l'application d'authentification.

        Args:
            secret: Secret TOTP en base32
            email: Email de l'utilisateur (pour l'identification)

        Returns:
            Image QR code en base64 (PNG)
        """
        # Creer l'URI TOTP standard
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=email, issuer_name=cls.ISSUER)

        # Generer le QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Convertir en base64
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        return base64.b64encode(buffer.getvalue()).decode()

    @classmethod
    def generate_qr_code_svg(cls, secret: str, email: str) -> str:
        """
        Genere un QR code en SVG pour configurer l'application d'authentification.

        Args:
            secret: Secret TOTP en base32
            email: Email de l'utilisateur

        Returns:
            QR code en SVG
        """
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=email, issuer_name=cls.ISSUER)

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)

        factory = qrcode.image.svg.SvgPathImage
        img = qr.make_image(image_factory=factory)

        buffer = BytesIO()
        img.save(buffer)
        buffer.seek(0)

        return buffer.getvalue().decode()

    @classmethod
    def verify_code(cls, secret: str, code: str) -> bool:
        """
        Verifie un code TOTP.

        Args:
            secret: Secret TOTP en base32
            code: Code a 6 chiffres entre par l'utilisateur

        Returns:
            True si le code est valide
        """
        if not code or len(code) != 6:
            return False

        try:
            totp = pyotp.TOTP(secret)
            # valid_window=1 permet d'accepter le code precedent/suivant
            # pour compenser les decalages d'horloge
            return totp.verify(code, valid_window=1)
        except Exception as e:
            logger.warning("totp_verify_error", error=str(e))
            return False

    @classmethod
    def generate_backup_codes(cls) -> List[str]:
        """
        Genere des codes de secours a usage unique.

        Returns:
            Liste de 10 codes de secours
        """
        codes = []
        for _ in range(cls.BACKUP_CODE_COUNT):
            # Generer un code aleatoire de 8 caracteres (chiffres + lettres)
            code = secrets.token_hex(cls.BACKUP_CODE_LENGTH // 2).upper()
            # Formater en xxxx-xxxx pour la lisibilite
            formatted = f"{code[:4]}-{code[4:]}"
            codes.append(formatted)
        return codes

    @classmethod
    def hash_backup_code(cls, code: str) -> str:
        """
        Hash un code de secours pour le stockage securise.

        Args:
            code: Code de secours en clair

        Returns:
            Hash SHA-256 du code
        """
        # Normaliser le code (enlever les tirets, majuscules)
        normalized = code.replace("-", "").upper()
        return hashlib.sha256(normalized.encode()).hexdigest()

    @classmethod
    def verify_backup_code(cls, code: str, hashed_codes: List[str]) -> Optional[int]:
        """
        Verifie un code de secours.

        Args:
            code: Code entre par l'utilisateur
            hashed_codes: Liste des codes hashes stockes

        Returns:
            Index du code trouve, ou None si invalide
        """
        code_hash = cls.hash_backup_code(code)
        for i, stored_hash in enumerate(hashed_codes):
            if code_hash == stored_hash:
                return i
        return None


# =============================================================================
# 2FA Database Operations
# =============================================================================
class TwoFactorManager:
    """Gestionnaire 2FA avec operations en base de donnees."""

    @classmethod
    def setup_2fa(cls, tenant_id: UUID, user_id: UUID) -> Tuple[str, str]:
        """
        Demarre la configuration 2FA pour un utilisateur.

        Args:
            tenant_id: ID du tenant
            user_id: ID de l'utilisateur

        Returns:
            Tuple (secret, qr_code_base64)
        """
        # Generer un nouveau secret
        secret = TOTPService.generate_secret()

        # Recuperer l'email de l'utilisateur
        with Database.get_session() as session:
            from sqlalchemy import text
            result = session.execute(
                text("""
                    SELECT email FROM azalplus.utilisateurs
                    WHERE id = :user_id AND tenant_id = :tenant_id
                """),
                {"user_id": str(user_id), "tenant_id": str(tenant_id)}
            )
            row = result.fetchone()
            if not row:
                raise ValueError("Utilisateur non trouve")

            email = row.email

            # Stocker le secret temporaire (en attente de verification)
            encrypted_secret = encrypt_secret(secret)
            session.execute(
                text("""
                    UPDATE azalplus.utilisateurs
                    SET totp_secret_temp = :secret, updated_at = NOW()
                    WHERE id = :user_id AND tenant_id = :tenant_id
                """),
                {
                    "secret": encrypted_secret,
                    "user_id": str(user_id),
                    "tenant_id": str(tenant_id)
                }
            )
            session.commit()

        # Generer le QR code
        qr_code = TOTPService.generate_qr_code(secret, email)

        logger.info("2fa_setup_started", user_id=str(user_id))

        return secret, qr_code

    @classmethod
    def confirm_2fa_setup(
        cls,
        tenant_id: UUID,
        user_id: UUID,
        code: str
    ) -> Optional[List[str]]:
        """
        Confirme la configuration 2FA apres verification du code.

        Args:
            tenant_id: ID du tenant
            user_id: ID de l'utilisateur
            code: Code TOTP entre par l'utilisateur

        Returns:
            Liste des codes de secours si succes, None si echec
        """
        with Database.get_session() as session:
            from sqlalchemy import text

            # Recuperer le secret temporaire
            result = session.execute(
                text("""
                    SELECT totp_secret_temp FROM azalplus.utilisateurs
                    WHERE id = :user_id AND tenant_id = :tenant_id
                """),
                {"user_id": str(user_id), "tenant_id": str(tenant_id)}
            )
            row = result.fetchone()

            if not row or not row.totp_secret_temp:
                return None

            # Dechiffrer et verifier
            try:
                secret = decrypt_secret(row.totp_secret_temp)
            except Exception:
                return None

            if not TOTPService.verify_code(secret, code):
                return None

            # Generer les codes de secours
            backup_codes = TOTPService.generate_backup_codes()
            hashed_codes = [TOTPService.hash_backup_code(c) for c in backup_codes]

            # Activer la 2FA
            session.execute(
                text("""
                    UPDATE azalplus.utilisateurs
                    SET totp_enabled = true,
                        totp_secret = :secret,
                        totp_secret_temp = NULL,
                        backup_codes = :backup_codes,
                        updated_at = NOW()
                    WHERE id = :user_id AND tenant_id = :tenant_id
                """),
                {
                    "secret": row.totp_secret_temp,  # Deja chiffre
                    "backup_codes": hashed_codes,
                    "user_id": str(user_id),
                    "tenant_id": str(tenant_id)
                }
            )
            session.commit()

        logger.info("2fa_enabled", user_id=str(user_id))

        return backup_codes

    @classmethod
    def disable_2fa(cls, tenant_id: UUID, user_id: UUID, code: str) -> bool:
        """
        Desactive la 2FA apres verification du code.

        Args:
            tenant_id: ID du tenant
            user_id: ID de l'utilisateur
            code: Code TOTP ou code de secours

        Returns:
            True si desactivation reussie
        """
        with Database.get_session() as session:
            from sqlalchemy import text

            # Recuperer les infos 2FA
            result = session.execute(
                text("""
                    SELECT totp_secret, backup_codes FROM azalplus.utilisateurs
                    WHERE id = :user_id AND tenant_id = :tenant_id AND totp_enabled = true
                """),
                {"user_id": str(user_id), "tenant_id": str(tenant_id)}
            )
            row = result.fetchone()

            if not row or not row.totp_secret:
                return False

            # Verifier le code TOTP ou code de secours
            try:
                secret = decrypt_secret(row.totp_secret)
                is_valid = TOTPService.verify_code(secret, code)
            except Exception:
                is_valid = False

            # Essayer les codes de secours si TOTP echoue
            if not is_valid and row.backup_codes:
                backup_index = TOTPService.verify_backup_code(code, row.backup_codes)
                is_valid = backup_index is not None

            if not is_valid:
                return False

            # Desactiver la 2FA
            session.execute(
                text("""
                    UPDATE azalplus.utilisateurs
                    SET totp_enabled = false,
                        totp_secret = NULL,
                        totp_secret_temp = NULL,
                        backup_codes = NULL,
                        updated_at = NOW()
                    WHERE id = :user_id AND tenant_id = :tenant_id
                """),
                {"user_id": str(user_id), "tenant_id": str(tenant_id)}
            )
            session.commit()

        logger.info("2fa_disabled", user_id=str(user_id))

        return True

    @classmethod
    def verify_2fa(
        cls,
        tenant_id: UUID,
        user_id: UUID,
        code: str
    ) -> Tuple[bool, bool]:
        """
        Verifie un code 2FA lors de la connexion.

        Args:
            tenant_id: ID du tenant
            user_id: ID de l'utilisateur
            code: Code TOTP ou code de secours

        Returns:
            Tuple (is_valid, is_backup_code)
        """
        with Database.get_session() as session:
            from sqlalchemy import text

            result = session.execute(
                text("""
                    SELECT totp_secret, backup_codes FROM azalplus.utilisateurs
                    WHERE id = :user_id AND tenant_id = :tenant_id AND totp_enabled = true
                """),
                {"user_id": str(user_id), "tenant_id": str(tenant_id)}
            )
            row = result.fetchone()

            if not row or not row.totp_secret:
                return False, False

            # Verifier le code TOTP
            try:
                secret = decrypt_secret(row.totp_secret)
                if TOTPService.verify_code(secret, code):
                    return True, False
            except Exception:
                pass

            # Essayer les codes de secours
            if row.backup_codes:
                backup_index = TOTPService.verify_backup_code(code, row.backup_codes)
                if backup_index is not None:
                    # Supprimer le code utilise
                    new_codes = list(row.backup_codes)
                    new_codes.pop(backup_index)

                    session.execute(
                        text("""
                            UPDATE azalplus.utilisateurs
                            SET backup_codes = :backup_codes, updated_at = NOW()
                            WHERE id = :user_id AND tenant_id = :tenant_id
                        """),
                        {
                            "backup_codes": new_codes,
                            "user_id": str(user_id),
                            "tenant_id": str(tenant_id)
                        }
                    )
                    session.commit()

                    logger.info("backup_code_used",
                        user_id=str(user_id),
                        remaining=len(new_codes)
                    )

                    return True, True

        return False, False

    @classmethod
    def regenerate_backup_codes(
        cls,
        tenant_id: UUID,
        user_id: UUID,
        code: str
    ) -> Optional[List[str]]:
        """
        Regenere les codes de secours apres verification du code TOTP.

        Args:
            tenant_id: ID du tenant
            user_id: ID de l'utilisateur
            code: Code TOTP actuel

        Returns:
            Nouveaux codes de secours si succes, None si echec
        """
        with Database.get_session() as session:
            from sqlalchemy import text

            # Verifier que la 2FA est active et le code valide
            result = session.execute(
                text("""
                    SELECT totp_secret FROM azalplus.utilisateurs
                    WHERE id = :user_id AND tenant_id = :tenant_id AND totp_enabled = true
                """),
                {"user_id": str(user_id), "tenant_id": str(tenant_id)}
            )
            row = result.fetchone()

            if not row or not row.totp_secret:
                return None

            try:
                secret = decrypt_secret(row.totp_secret)
                if not TOTPService.verify_code(secret, code):
                    return None
            except Exception:
                return None

            # Generer de nouveaux codes
            backup_codes = TOTPService.generate_backup_codes()
            hashed_codes = [TOTPService.hash_backup_code(c) for c in backup_codes]

            session.execute(
                text("""
                    UPDATE azalplus.utilisateurs
                    SET backup_codes = :backup_codes, updated_at = NOW()
                    WHERE id = :user_id AND tenant_id = :tenant_id
                """),
                {
                    "backup_codes": hashed_codes,
                    "user_id": str(user_id),
                    "tenant_id": str(tenant_id)
                }
            )
            session.commit()

        logger.info("backup_codes_regenerated", user_id=str(user_id))

        return backup_codes

    @classmethod
    def get_2fa_status(cls, tenant_id: UUID, user_id: UUID) -> dict:
        """
        Retourne le statut 2FA d'un utilisateur.

        Args:
            tenant_id: ID du tenant
            user_id: ID de l'utilisateur

        Returns:
            Dict avec enabled et backup_codes_remaining
        """
        with Database.get_session() as session:
            from sqlalchemy import text

            result = session.execute(
                text("""
                    SELECT totp_enabled, backup_codes FROM azalplus.utilisateurs
                    WHERE id = :user_id AND tenant_id = :tenant_id
                """),
                {"user_id": str(user_id), "tenant_id": str(tenant_id)}
            )
            row = result.fetchone()

            if not row:
                return {"enabled": False, "backup_codes_remaining": 0}

            return {
                "enabled": bool(row.totp_enabled),
                "backup_codes_remaining": len(row.backup_codes) if row.backup_codes else 0
            }
