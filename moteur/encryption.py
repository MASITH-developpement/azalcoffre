# =============================================================================
# AZALPLUS - Field Encryption Module
# =============================================================================
"""
Encryption transparente des champs sensibles.

Fonctionnalites:
- Encryption Fernet (AES-128-CBC)
- Cles derivees par tenant (isolation)
- Encryption/decryption transparente
- Support attribut YAML 'chiffre: true'
- Key rotation support
- Compression optionnelle

Utilisation YAML:
    champs:
      - nom: iban
        type: text
        chiffre: true  # ← Active l'encryption
"""

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64
import hashlib
import zlib
from typing import Optional, Union
from uuid import UUID
import structlog

from .config import settings

logger = structlog.get_logger()

# =============================================================================
# CONFIGURATION
# =============================================================================
# Prefixe pour identifier les valeurs encryptees
ENCRYPTED_PREFIX = "enc:v1:"

# Prefixe pour les valeurs compressees puis encryptees
COMPRESSED_PREFIX = "enc:v1:z:"

# Taille minimum pour compresser (bytes)
COMPRESSION_THRESHOLD = 100


# =============================================================================
# KEY DERIVATION
# =============================================================================
class KeyDerivation:
    """Derivation de cles securisee."""

    # Cache des cles derivees (en memoire)
    _key_cache: dict = {}

    @classmethod
    def derive_tenant_key(cls, master_key: str, tenant_id: Union[str, UUID]) -> bytes:
        """
        Derive une cle unique pour un tenant.

        Utilise PBKDF2 avec le tenant_id comme salt pour
        garantir l'isolation des cles entre tenants.

        Args:
            master_key: Cle maitre de l'application (settings.ENCRYPTION_KEY)
            tenant_id: ID du tenant

        Returns:
            Cle Fernet de 32 bytes encodee en base64
        """
        tenant_str = str(tenant_id)

        # Verifier le cache
        cache_key = f"{master_key[:8]}:{tenant_str}"
        if cache_key in cls._key_cache:
            return cls._key_cache[cache_key]

        # Salt = hash du tenant_id (pour avoir une longueur fixe)
        salt = hashlib.sha256(tenant_str.encode()).digest()[:16]

        # Derivation PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,  # Securite vs performance
            backend=default_backend()
        )

        key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))

        # Mettre en cache
        cls._key_cache[cache_key] = key

        return key

    @classmethod
    def clear_cache(cls):
        """Vide le cache des cles (pour rotation)."""
        cls._key_cache.clear()
        logger.info("encryption_key_cache_cleared")


# =============================================================================
# FIELD ENCRYPTION
# =============================================================================
class FieldEncryption:
    """
    Encryption transparente des champs.

    Utilisation:
        # Encryption
        encrypted = FieldEncryption.encrypt("valeur sensible", tenant_id)

        # Decryption
        value = FieldEncryption.decrypt(encrypted, tenant_id)
    """

    @classmethod
    def get_fernet(cls, tenant_id: Union[str, UUID]) -> Fernet:
        """
        Obtient une instance Fernet pour un tenant.

        Args:
            tenant_id: ID du tenant

        Returns:
            Instance Fernet configuree
        """
        master_key = getattr(settings, 'ENCRYPTION_KEY', settings.SECRET_KEY)
        key = KeyDerivation.derive_tenant_key(master_key, tenant_id)
        return Fernet(key)

    @classmethod
    def encrypt(
        cls,
        value: str,
        tenant_id: Union[str, UUID],
        compress: bool = True
    ) -> str:
        """
        Encrypte une valeur pour un tenant.

        Args:
            value: Valeur a encrypter
            tenant_id: ID du tenant
            compress: Compresser si la valeur est grande

        Returns:
            Valeur encryptee avec prefixe

        Example:
            >>> encrypted = FieldEncryption.encrypt("secret", "tenant-123")
            >>> print(encrypted)
            enc:v1:gAAAAABk...
        """
        if not value:
            return value

        # Deja encrypte ?
        if value.startswith(ENCRYPTED_PREFIX):
            return value

        fernet = cls.get_fernet(tenant_id)

        # Compression optionnelle
        data = value.encode('utf-8')
        prefix = ENCRYPTED_PREFIX

        if compress and len(data) >= COMPRESSION_THRESHOLD:
            data = zlib.compress(data, level=6)
            prefix = COMPRESSED_PREFIX

        # Encryption
        encrypted = fernet.encrypt(data)

        return prefix + encrypted.decode('utf-8')

    @classmethod
    def decrypt(
        cls,
        value: str,
        tenant_id: Union[str, UUID]
    ) -> str:
        """
        Decrypte une valeur pour un tenant.

        Args:
            value: Valeur encryptee
            tenant_id: ID du tenant

        Returns:
            Valeur decryptee

        Raises:
            ValueError: Si la decryption echoue

        Example:
            >>> decrypted = FieldEncryption.decrypt(encrypted, "tenant-123")
            >>> print(decrypted)
            secret
        """
        if not value:
            return value

        # Non encrypte ?
        if not value.startswith(ENCRYPTED_PREFIX):
            return value

        # Determiner si compresse
        is_compressed = value.startswith(COMPRESSED_PREFIX)
        prefix = COMPRESSED_PREFIX if is_compressed else ENCRYPTED_PREFIX

        try:
            fernet = cls.get_fernet(tenant_id)

            # Extraire les donnees encryptees
            encrypted_data = value[len(prefix):].encode('utf-8')

            # Decryption
            decrypted = fernet.decrypt(encrypted_data)

            # Decompression si necessaire
            if is_compressed:
                decrypted = zlib.decompress(decrypted)

            return decrypted.decode('utf-8')

        except InvalidToken:
            logger.error(
                "encryption_decrypt_failed",
                tenant_id=str(tenant_id),
                reason="invalid_token"
            )
            raise ValueError("Impossible de decrypter: token invalide")

        except Exception as e:
            logger.error(
                "encryption_decrypt_error",
                tenant_id=str(tenant_id),
                error=str(e)
            )
            raise ValueError(f"Erreur de decryption: {str(e)}")

    @classmethod
    def is_encrypted(cls, value: str) -> bool:
        """
        Verifie si une valeur est encryptee.

        Args:
            value: Valeur a verifier

        Returns:
            True si la valeur est encryptee
        """
        if not value:
            return False
        return value.startswith(ENCRYPTED_PREFIX)

    @classmethod
    def rotate_key(
        cls,
        value: str,
        tenant_id: Union[str, UUID],
        old_master_key: str,
        new_master_key: str
    ) -> str:
        """
        Re-encrypte une valeur avec une nouvelle cle maitre.

        Utile pour la rotation de cles.

        Args:
            value: Valeur encryptee avec l'ancienne cle
            tenant_id: ID du tenant
            old_master_key: Ancienne cle maitre
            new_master_key: Nouvelle cle maitre

        Returns:
            Valeur re-encryptee avec la nouvelle cle
        """
        if not cls.is_encrypted(value):
            return value

        # Decrypter avec l'ancienne cle
        old_key = KeyDerivation.derive_tenant_key(old_master_key, tenant_id)
        old_fernet = Fernet(old_key)

        is_compressed = value.startswith(COMPRESSED_PREFIX)
        prefix = COMPRESSED_PREFIX if is_compressed else ENCRYPTED_PREFIX
        encrypted_data = value[len(prefix):].encode('utf-8')

        decrypted = old_fernet.decrypt(encrypted_data)

        if is_compressed:
            decrypted = zlib.decompress(decrypted)

        # Re-encrypter avec la nouvelle cle
        new_key = KeyDerivation.derive_tenant_key(new_master_key, tenant_id)
        new_fernet = Fernet(new_key)

        data = decrypted
        new_prefix = ENCRYPTED_PREFIX

        if is_compressed:
            data = zlib.compress(decrypted, level=6)
            new_prefix = COMPRESSED_PREFIX

        new_encrypted = new_fernet.encrypt(data)

        return new_prefix + new_encrypted.decode('utf-8')


# =============================================================================
# ENCRYPTED FIELD TYPES (pour integration SQLAlchemy)
# =============================================================================
# Liste des types de champs automatiquement encryptes
AUTO_ENCRYPTED_TYPES = [
    "password",
    "secret",
    "api_key",
    "token",
    "iban",
    "credit_card",
    "bank_account",
    "ssn",  # Social Security Number
    "tax_id_encrypted",
]


def should_encrypt_field(field_config: dict) -> bool:
    """
    Determine si un champ doit etre encrypte.

    Args:
        field_config: Configuration du champ depuis YAML

    Returns:
        True si le champ doit etre encrypte
    """
    # Attribut explicite
    if field_config.get("chiffre") or field_config.get("encrypted"):
        return True

    # Type auto-encrypte
    field_type = field_config.get("type", "").lower()
    if field_type in AUTO_ENCRYPTED_TYPES:
        return True

    return False


# =============================================================================
# ENCRYPTION MIDDLEWARE HELPERS
# =============================================================================
class EncryptionMiddleware:
    """
    Helpers pour l'encryption automatique dans le pipeline de donnees.
    """

    @classmethod
    def encrypt_dict(
        cls,
        data: dict,
        encrypted_fields: list,
        tenant_id: Union[str, UUID]
    ) -> dict:
        """
        Encrypte les champs specifies dans un dictionnaire.

        Args:
            data: Dictionnaire de donnees
            encrypted_fields: Liste des noms de champs a encrypter
            tenant_id: ID du tenant

        Returns:
            Dictionnaire avec les champs encryptes
        """
        result = data.copy()

        for field in encrypted_fields:
            if field in result and result[field]:
                result[field] = FieldEncryption.encrypt(
                    str(result[field]),
                    tenant_id
                )

        return result

    @classmethod
    def decrypt_dict(
        cls,
        data: dict,
        encrypted_fields: list,
        tenant_id: Union[str, UUID]
    ) -> dict:
        """
        Decrypte les champs specifies dans un dictionnaire.

        Args:
            data: Dictionnaire de donnees
            encrypted_fields: Liste des noms de champs a decrypter
            tenant_id: ID du tenant

        Returns:
            Dictionnaire avec les champs decryptes
        """
        result = data.copy()

        for field in encrypted_fields:
            if field in result and result[field]:
                try:
                    result[field] = FieldEncryption.decrypt(
                        str(result[field]),
                        tenant_id
                    )
                except ValueError:
                    # Garder la valeur originale si decryption echoue
                    logger.warning(
                        "field_decryption_failed",
                        field=field,
                        tenant_id=str(tenant_id)
                    )

        return result


# =============================================================================
# INITIALIZATION
# =============================================================================
def verify_encryption_setup() -> bool:
    """
    Verifie que l'encryption est correctement configuree.

    Returns:
        True si tout est OK
    """
    try:
        # Verifier la cle
        master_key = getattr(settings, 'ENCRYPTION_KEY', settings.SECRET_KEY)

        if len(master_key) < 32:
            logger.warning("encryption_key_too_short", length=len(master_key))

        # Test d'encryption/decryption
        test_tenant = "test-tenant-verify"
        test_value = "test_encryption_value_123"

        encrypted = FieldEncryption.encrypt(test_value, test_tenant)
        decrypted = FieldEncryption.decrypt(encrypted, test_tenant)

        if decrypted != test_value:
            logger.error("encryption_verification_failed")
            return False

        logger.info("encryption_setup_verified")
        return True

    except Exception as e:
        logger.error("encryption_setup_error", error=str(e))
        return False
