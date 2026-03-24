# =============================================================================
# AZALPLUS - Email to Intervention Service
# =============================================================================
"""
Service de création automatique d'interventions depuis les emails.

Fonctionnalités:
- Polling IMAP pour détecter les nouveaux emails
- Détection par mots-clés dans l'objet
- Matching client par email expéditeur
- Création automatique d'intervention
- Réponse automatique à l'expéditeur
"""

import imaplib
import email
from email.header import decode_header
from email.utils import parseaddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import re
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
import yaml
import structlog
from uuid import UUID
import os

from .encryption import FieldEncryption

from .db import Database
from .config import settings

logger = structlog.get_logger()

# =============================================================================
# CONFIGURATION
# =============================================================================
CONFIG_PATH = Path(__file__).parent.parent / "config" / "email_to_intervention.yml"


def load_config() -> Dict[str, Any]:
    """Charge la configuration depuis le fichier YAML."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {"actif": False}


# =============================================================================
# EMAIL SERVICE
# =============================================================================
class EmailToInterventionService:
    """Service de création d'interventions depuis les emails."""

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id
        self.config = load_config()
        self.db_config = self._load_db_config()

        # Priorité: config DB > variables d'environnement
        self.imap_host = self.db_config.get("imap_host") or os.getenv("EMAIL_IMAP_HOST", "")
        self.imap_port = int(self.db_config.get("imap_port") or os.getenv("EMAIL_IMAP_PORT", "993"))
        self.imap_user = self.db_config.get("imap_user") or os.getenv("EMAIL_IMAP_USER", "")
        self.imap_password = self.db_config.get("imap_password") or os.getenv("EMAIL_IMAP_PASSWORD", "")
        self.smtp_host = self.db_config.get("smtp_host") or os.getenv("EMAIL_SMTP_HOST", "")
        self.smtp_port = int(self.db_config.get("smtp_port") or os.getenv("EMAIL_SMTP_PORT", "587"))
        self.smtp_from_name = self.db_config.get("smtp_from_name", "")
        self.smtp_from_email = self.db_config.get("smtp_from_email") or self.imap_user

    def _load_db_config(self) -> Dict[str, Any]:
        """Charge la configuration email depuis la base de données (administration_mail)."""
        try:
            with Database.get_session() as session:
                from sqlalchemy import text
                result = session.execute(
                    text("""
                        SELECT imap_actif, imap_host, imap_port, imap_user, imap_password,
                               imap_dossier, imap_dossier_traite,
                               smtp_actif, smtp_host, smtp_port, smtp_user, smtp_password,
                               smtp_from_name, smtp_from_email,
                               intervention_auto, intervalle_polling, reponse_auto, mots_cles
                        FROM azalplus.administration_mail
                        WHERE tenant_id = :tenant_id
                        AND (archived IS NULL OR archived = false)
                        LIMIT 1
                    """),
                    {"tenant_id": str(self.tenant_id)}
                )
                row = result.fetchone()
                if row:
                    # Déchiffrer les mots de passe (champs marqués chiffre: true)
                    imap_password = row[4]
                    smtp_password = row[11]

                    if imap_password and imap_password.startswith("enc:"):
                        try:
                            imap_password = FieldEncryption.decrypt(imap_password, self.tenant_id)
                        except Exception as e:
                            logger.warning("imap_password_decrypt_failed", error=str(e))
                            imap_password = ""

                    if smtp_password and smtp_password.startswith("enc:"):
                        try:
                            smtp_password = FieldEncryption.decrypt(smtp_password, self.tenant_id)
                        except Exception as e:
                            logger.warning("smtp_password_decrypt_failed", error=str(e))
                            smtp_password = ""

                    return {
                        "imap_actif": row[0],
                        "imap_host": row[1],
                        "imap_port": row[2],
                        "imap_user": row[3],
                        "imap_password": imap_password,
                        "imap_dossier": row[5] or "INBOX",
                        "imap_dossier_traite": row[6],
                        "smtp_actif": row[7],
                        "smtp_host": row[8],
                        "smtp_port": row[9],
                        "smtp_user": row[10],
                        "smtp_password": smtp_password,
                        "smtp_from_name": row[12],
                        "smtp_from_email": row[13],
                        "intervention_auto": row[14],
                        "intervalle_polling": row[15] or 300,
                        "reponse_auto": row[16],
                        "mots_cles": row[17],
                    }
        except Exception as e:
            logger.debug("db_config_not_available", error=str(e))
        return {}

    def is_configured(self) -> bool:
        """Vérifie si le service est configuré."""
        # Vérifie config DB ou YAML
        db_active = self.db_config.get("imap_actif", False)
        yaml_active = self.config.get("actif", False)

        return bool(
            (db_active or yaml_active)
            and self.imap_host
            and self.imap_user
            and self.imap_password
        )

    def _connect_imap(self) -> imaplib.IMAP4_SSL:
        """Établit la connexion IMAP."""
        imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        imap.login(self.imap_user, self.imap_password)
        return imap

    def _decode_header_value(self, value: str) -> str:
        """Décode une valeur d'en-tête email."""
        if not value:
            return ""
        decoded_parts = decode_header(value)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or "utf-8", errors="replace"))
            else:
                result.append(part)
        return "".join(result)

    def _extract_email_address(self, header: str) -> str:
        """Extrait l'adresse email d'un header From."""
        _, email_addr = parseaddr(header)
        return email_addr.lower()

    def _matches_donneur_ordre(self, subject: str) -> Optional[Dict[str, Any]]:
        """
        Vérifie si l'objet contient un donneur d'ordre connu.
        Retourne les infos du donneur d'ordre et le numéro extrait.
        """
        donneurs = self.config.get("donneurs_ordre", [])

        # Ajouter aussi les mots-clés de la DB qui contiennent "INTERPARTNER" ou autres donneurs connus
        db_keywords = self.db_config.get("mots_cles") or []
        if isinstance(db_keywords, str):
            db_keywords = [k.strip() for k in db_keywords.split(",") if k.strip()]

        for keyword in db_keywords:
            kw_upper = keyword.upper()
            if "INTERPARTNER" in kw_upper and kw_upper in subject.upper():
                # Extraire le numéro de dossier depuis le sujet
                # Format: 0826A44724 (chiffres + lettres + chiffres)
                pattern = r'\b(\d{4}[A-Z]\d{5})\b'
                match = re.search(pattern, subject.upper())
                numero_os = match.group(1) if match else None
                return {
                    "donneur_ordre": keyword,
                    "numero_os": numero_os,
                    "priorite": "URGENTE",
                    "type_intervention": "DEPANNAGE"
                }
        for donneur in donneurs:
            nom = donneur.get("nom", "")
            if nom.upper() in subject.upper():
                # Extraire le numéro d'intervention avec le pattern
                pattern = donneur.get("pattern_numero", r'\b(\d{10})\b')
                match = re.search(pattern, subject)
                numero_os = match.group(1) if match else None

                return {
                    "donneur_ordre": nom,
                    "numero_os": numero_os,
                    "priorite": donneur.get("priorite", "NORMALE"),
                    "type_intervention": donneur.get("type_intervention", "DEPANNAGE")
                }
        return None

    def _parse_interpartner_email(self, body: str) -> Dict[str, Any]:
        """
        Parse un email d'ordre de mission INTERPARTNER ASSISTANCE.
        Extrait les champs structurés du corps du mail (format HTML).
        """
        from html import unescape
        data = {}

        # Le mail INTERPARTNER est en HTML avec structure:
        # <b>Label:</b></p></td><td...><p...>VALUE</p>
        # On utilise un pattern générique pour extraire les paires label/valeur
        html_pattern = r'<b>([^<]+)</b>\s*</p>\s*</td>\s*<td[^>]*>\s*<p[^>]*>([^<]+)</p>'
        matches = re.findall(html_pattern, body, re.DOTALL | re.IGNORECASE)

        # Mapping des labels HTML vers nos clés (regex pour gérer encodage ISO-8859-1)
        # Les caractères accentués peuvent être corrompus (é -> �)
        label_patterns = {
            r"Date\s*/\s*Heure": "date_heure_mission",
            r"N.?\s*Dossier": "numero_os",
            r"Convention": "convention",
            r"Nom\s*Assist": "contact_nom",
            r"Adresse\s*incident": "adresse_raw",
            r"T.?l.?phone\s*de\s*l.assist": "contact_telephone",
            r"Cause\s*identifi": "cause",
            r"DELAI\s*D.INTERVENTION": "delai",
            r"Pr.?nom\s*de\s*l.agent\s*exp": "expediteur_prenom",
            r"N.?\s*de\s*t.?l.?phone\s*pour\s*nous": "telephone_contact_do",
        }

        for label, value in matches:
            label_clean = unescape(label.strip()).replace(":", "").strip()
            value_clean = unescape(value.strip())

            # Ignorer les valeurs vides ou espaces
            if not value_clean or value_clean == '&nbsp;' or value_clean.isspace():
                continue

            # Chercher le mapping avec regex (gère les problèmes d'encodage)
            for pattern, key in label_patterns.items():
                if re.search(pattern, label_clean, re.IGNORECASE):
                    data[key] = value_clean
                    break

        # Fallback: patterns texte si pas trouvé en HTML (emails forwarded/plain text)
        fallback_patterns = {
            "numero_os": r"N.?\s*Dossier\s*:?\s*(\d+[A-Za-z]?\d*)",
            "convention": r"Convention\s*:?\s*(.+?)(?:\n|<|$)",
            "contact_nom": r"Nom\s*Assist.?\s*:?\s*(.+?)(?:\n|<|$)",
            "adresse_raw": r"Adresse\s*incident\s*:?\s*(.+?)(?:\n|<|$)",
            "contact_telephone": r"T.?l.?phone\s*de\s*l.assist.?\s*:?\s*([+\d\s]+)",
            # Cause: format spécial "Label: </b>Value </p>"
            "cause": r"Cause\s*identifi.?e\s*d.intervention\s*:?\s*</b>([^<]+)</p>",
            "delai": r"DELAI\s*D.INTERVENTION\s*:?\s*</b>([^<]+)</p>",
        }

        for key, pattern in fallback_patterns.items():
            if key not in data:
                match = re.search(pattern, body, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    # Nettoyer les balises HTML résiduelles
                    value = re.sub(r'<[^>]+>', '', value).strip()
                    data[key] = value

        # Parser l'adresse (format: "26, Rue de la République, 83670 Barjols")
        if data.get("adresse_raw"):
            addr = data["adresse_raw"]
            # Chercher le code postal et la ville
            cp_match = re.search(r"(\d{5})\s+(.+)$", addr)
            if cp_match:
                data["code_postal"] = cp_match.group(1)
                data["ville"] = cp_match.group(2).strip()
                # L'adresse est tout ce qui précède le CP
                data["adresse_intervention"] = addr[:cp_match.start()].strip().rstrip(",")
            else:
                data["adresse_intervention"] = addr

        # Nettoyer le téléphone
        if data.get("contact_telephone"):
            data["contact_telephone"] = re.sub(r"\s+", "", data["contact_telephone"])

        # Déterminer la priorité selon le délai
        if data.get("delai"):
            delai_lower = data["delai"].lower()
            if "4 heure" in delai_lower or "urgence" in delai_lower:
                data["priorite"] = "HAUTE"
            elif "24" in delai_lower or "lendemain" in delai_lower:
                data["priorite"] = "NORMALE"
            else:
                data["priorite"] = "NORMALE"

        # Parser la date/heure de mission (format: "16.03.2026 à 19:27" ou "16.03.2026 � 19:27")
        if data.get("date_heure_mission"):
            date_str = data["date_heure_mission"]
            # Nettoyer les caractères mal encodés (à -> �)
            date_str = re.sub(r'\s*[àâ�]\s*', ' ', date_str).strip()
            # Format attendu: "DD.MM.YYYY HH:MM"
            date_match = re.match(r'(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})', date_str)
            if date_match:
                day, month, year, hour, minute = date_match.groups()
                try:
                    data["date_demande"] = datetime(
                        int(year), int(month), int(day), int(hour), int(minute)
                    )
                except ValueError:
                    pass  # Date invalide, on garde None

        return data

    def _matches_keywords(self, subject: str) -> Optional[str]:
        """Vérifie si l'objet contient un mot-clé déclencheur (fallback)."""
        # Priorité: config DB > config YAML
        keywords = self.db_config.get("mots_cles") or self.config.get("mots_cles", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        subject_upper = subject.upper()
        for keyword in keywords:
            if keyword.upper() in subject_upper:
                return keyword.upper()
        return None

    def _get_priority_for_keyword(self, keyword: str) -> str:
        """Retourne la priorité associée à un mot-clé."""
        priorities = self.config.get("priorite_mots_cles", {})
        return priorities.get(keyword, self.config.get("defauts", {}).get("priorite", "NORMALE"))

    def _find_donneur_ordre_id(self, nom: str, sender_email: str = None, subject: str = None) -> Optional[str]:
        """
        Recherche l'ID du donneur d'ordre dans la base.
        Priorité: 1) Par nom, 2) Par pattern email expéditeur, 3) Par pattern dans sujet
        """
        with Database.get_session() as session:
            from sqlalchemy import text

            # 1) Chercher par nom exact ou partiel
            result = session.execute(
                text("""
                    SELECT id FROM azalplus.donneur_ordre
                    WHERE tenant_id = :tenant_id
                    AND UPPER(nom) LIKE UPPER(:nom)
                    AND (archived IS NULL OR archived = false)
                    LIMIT 1
                """),
                {"tenant_id": str(self.tenant_id), "nom": f"%{nom}%"}
            )
            row = result.fetchone()
            if row:
                return str(row[0])

            # 2) Chercher par pattern email (email_patterns JSONB)
            if sender_email or subject:
                result = session.execute(
                    text("""
                        SELECT id, nom, email_patterns FROM azalplus.donneur_ordre
                        WHERE tenant_id = :tenant_id
                        AND email_patterns IS NOT NULL
                        AND email_patterns != '[]'::jsonb
                        AND (archived IS NULL OR archived = false)
                    """),
                    {"tenant_id": str(self.tenant_id)}
                )
                for row in result.fetchall():
                    donneur_id, donneur_nom, patterns = row
                    if patterns:
                        for pattern in patterns:
                            pattern_upper = pattern.upper()
                            # Vérifier si le pattern match l'email ou le sujet
                            if sender_email and pattern_upper in sender_email.upper():
                                logger.info("donneur_matched_by_email", donneur=donneur_nom, pattern=pattern, email=sender_email)
                                return str(donneur_id)
                            if subject and pattern_upper in subject.upper():
                                logger.info("donneur_matched_by_subject", donneur=donneur_nom, pattern=pattern, subject=subject[:50])
                                return str(donneur_id)

            return None

    def _find_client_by_email(self, email_address: str) -> Optional[Dict[str, Any]]:
        """Recherche un client par son adresse email."""
        with Database.get_session() as session:
            from sqlalchemy import text

            # Chercher dans la table clients
            result = session.execute(
                text("""
                    SELECT id, name, email, phone
                    FROM azalplus.clients
                    WHERE tenant_id = :tenant_id
                    AND LOWER(email) = LOWER(:email)
                    AND (archived IS NULL OR archived = false)
                    LIMIT 1
                """),
                {"tenant_id": str(self.tenant_id), "email": email_address}
            )
            row = result.fetchone()
            if row:
                return {
                    "id": row[0],
                    "nom": row[1],
                    "email": row[2],
                    "telephone": row[3]
                }

            # Note: recherche dans contacts désactivée (structure table variable)

        return None

    def _find_or_create_client(
        self,
        contact_nom: str,
        contact_telephone: str = None,
        contact_email: str = None,
        adresse: str = None,
        code_postal: str = None,
        ville: str = None
    ) -> Optional[str]:
        """
        Recherche un client existant ou le crée.
        Recherche par: 1) téléphone, 2) nom exact
        Retourne l'ID du client.
        """
        if not contact_nom:
            return None

        with Database.get_session() as session:
            from sqlalchemy import text

            # 1) Chercher par téléphone (plus fiable)
            if contact_telephone:
                # Nettoyer le téléphone pour la recherche
                tel_clean = re.sub(r'[^\d+]', '', contact_telephone)
                result = session.execute(
                    text("""
                        SELECT id, name FROM azalplus.clients
                        WHERE tenant_id = :tenant_id
                        AND REPLACE(REPLACE(phone, ' ', ''), '-', '') LIKE :phone
                        AND (archived IS NULL OR archived = false)
                        LIMIT 1
                    """),
                    {"tenant_id": str(self.tenant_id), "phone": f"%{tel_clean[-9:]}%"}
                )
                row = result.fetchone()
                if row:
                    logger.info("client_found_by_phone", client_id=str(row[0]), name=row[1])
                    return str(row[0])

            # 2) Chercher par nom exact
            result = session.execute(
                text("""
                    SELECT id, name FROM azalplus.clients
                    WHERE tenant_id = :tenant_id
                    AND UPPER(name) = UPPER(:name)
                    AND (archived IS NULL OR archived = false)
                    LIMIT 1
                """),
                {"tenant_id": str(self.tenant_id), "name": contact_nom}
            )
            row = result.fetchone()
            if row:
                logger.info("client_found_by_name", client_id=str(row[0]), name=row[1])
                return str(row[0])

            # 3) Créer le client
            # Générer un code unique
            result = session.execute(
                text("SELECT COUNT(*) + 1 FROM azalplus.clients WHERE tenant_id = :tenant_id"),
                {"tenant_id": str(self.tenant_id)}
            )
            count = result.scalar() or 1
            code = f"CLI-{count:05d}"

            result = session.execute(
                text("""
                    INSERT INTO azalplus.clients (
                        id, tenant_id, code, name, phone, email,
                        address_line1, postal_code, city,
                        type, created_at
                    ) VALUES (
                        uuid_generate_v4(), :tenant_id, :code, :name, :phone, :email,
                        :address, :postal_code, :city,
                        'PARTICULIER', NOW()
                    )
                    RETURNING id
                """),
                {
                    "tenant_id": str(self.tenant_id),
                    "code": code,
                    "name": contact_nom,
                    "phone": contact_telephone,
                    "email": contact_email,
                    "address": adresse,
                    "postal_code": code_postal,
                    "city": ville
                }
            )
            session.commit()
            client_id = result.scalar()
            logger.info("client_created", client_id=str(client_id), name=contact_nom, code=code)
            return str(client_id)

    def _get_email_body(self, msg: email.message.Message) -> str:
        """Extrait le corps du mail (texte brut de préférence)."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body = payload.decode(charset, errors="replace")
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="replace")
        return body.strip()

    def _create_intervention(
        self,
        client: Optional[Dict[str, Any]],
        subject: str,
        body: str,
        sender_email: str,
        keyword: Optional[str] = None,
        donneur_info: Optional[Dict[str, Any]] = None,
        parsed_data: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Crée une intervention depuis les données email."""
        defauts = self.config.get("defauts", {})
        extraction = self.config.get("extraction", {})

        # Si données parsées (INTERPARTNER etc), utiliser ces données
        if parsed_data:
            objet = parsed_data.get("cause", subject)
            if not objet:
                objet = f"Intervention {parsed_data.get('numero_os', '')}"
            # Description = cause du mail
            description = parsed_data.get("cause", "")
            priorite = parsed_data.get("priorite", "NORMALE")
            numero_os = parsed_data.get("numero_os")
            contact_nom = parsed_data.get("contact_nom")
            contact_telephone = parsed_data.get("contact_telephone")
            adresse_intervention = parsed_data.get("adresse_intervention")
            code_postal = parsed_data.get("code_postal")
            ville = parsed_data.get("ville")
            date_demande = parsed_data.get("date_demande")  # Date/heure de l'ordre de mission
        else:
            # Mode classique
            objet = subject if extraction.get("objet_depuis_sujet", True) else "Demande par email"
            if donneur_info and donneur_info.get("donneur_ordre"):
                objet = objet.replace(donneur_info["donneur_ordre"], "").strip()
            for kw in self.config.get("mots_cles", []):
                objet = re.sub(rf"\b{kw}\b", "", objet, flags=re.IGNORECASE).strip()
            objet = re.sub(r"\s+", " ", objet).strip(" -:")
            if not objet:
                objet = f"Demande {keyword or 'email'}"

            description = body if extraction.get("description_depuis_corps", True) else None
            priorite = None
            numero_os = donneur_info.get("numero_os") if donneur_info else None
            contact_nom = None
            contact_telephone = None
            adresse_intervention = None
            code_postal = None
            ville = None
            date_demande = None  # Pas de date parsée, utilisera NOW()

        # Déterminer priorité et type
        if donneur_info:
            if not priorite:
                priorite = donneur_info.get("priorite", defauts.get("priorite", "NORMALE"))
            type_intervention = donneur_info.get("type_intervention", defauts.get("type_intervention", "DEPANNAGE"))
            if not numero_os:
                numero_os = donneur_info.get("numero_os")
            donneur_ordre_nom = donneur_info.get("donneur_ordre")
            donneur_ordre_id = self._find_donneur_ordre_id(donneur_ordre_nom, sender_email, subject) if donneur_ordre_nom else None
        else:
            if not priorite:
                priorite = self._get_priority_for_keyword(keyword) if keyword else defauts.get("priorite", "NORMALE")
            type_intervention = defauts.get("type_intervention", "DEPANNAGE")
            # Chercher donneur d'ordre par email/sujet même sans mot-clé donneur
            donneur_ordre_id = self._find_donneur_ordre_id("", sender_email, subject)

        with Database.get_session() as session:
            from sqlalchemy import text

            # Vérifier si une intervention existe déjà avec ce numero_os (anti-doublon)
            if numero_os:
                result = session.execute(
                    text("""
                        SELECT numero FROM azalplus.interventions
                        WHERE tenant_id = :tenant_id
                        AND numero_os = :numero_os
                        AND (archived IS NULL OR archived = false)
                        LIMIT 1
                    """),
                    {"tenant_id": str(self.tenant_id), "numero_os": numero_os}
                )
                existing = result.fetchone()
                if existing:
                    logger.info("intervention_already_exists", numero_os=numero_os, existing_numero=existing[0])
                    return None  # Ne pas créer de doublon

            # Générer le numéro interne
            result = session.execute(
                text("""
                    SELECT COUNT(*) + 1 FROM azalplus.interventions
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": str(self.tenant_id)}
            )
            count = result.scalar() or 1
            numero = f"INT-{datetime.now().strftime('%Y%m')}-{count:05d}"

            # Insérer l'intervention avec tous les champs
            intervention_id = session.execute(
                text("""
                    INSERT INTO azalplus.interventions (
                        id, tenant_id, numero, objet, description,
                        client_id, contact_email, contact_nom, contact_telephone,
                        adresse_intervention, code_postal, ville,
                        donneur_ordre_id, numero_os,
                        type_fiche, type_intervention, statut, priorite,
                        date_demande, notes,
                        created_at
                    ) VALUES (
                        uuid_generate_v4(), :tenant_id, :numero, :objet, :description,
                        :client_id, :contact_email, :contact_nom, :contact_telephone,
                        :adresse_intervention, :code_postal, :ville,
                        :donneur_ordre_id, :numero_os,
                        :type_fiche, :type_intervention, :statut, :priorite,
                        COALESCE(:date_demande, NOW()), :notes,
                        NOW()
                    )
                    RETURNING id
                """),
                {
                    "tenant_id": str(self.tenant_id),
                    "numero": numero,
                    "objet": objet[:200] if objet else "Demande par email",
                    "description": description[:250] if description else None,  # VARCHAR(255)
                    "client_id": str(client["id"]) if client else None,
                    "contact_email": sender_email,
                    "contact_nom": contact_nom[:100] if contact_nom else None,
                    "contact_telephone": contact_telephone[:20] if contact_telephone else None,
                    "adresse_intervention": adresse_intervention[:200] if adresse_intervention else None,
                    "code_postal": code_postal[:10] if code_postal else None,
                    "ville": ville[:100] if ville else None,
                    "donneur_ordre_id": donneur_ordre_id,
                    "numero_os": numero_os[:50] if numero_os else None,
                    "type_fiche": defauts.get("type_fiche", "INTERVENTION"),
                    "type_intervention": type_intervention,
                    "statut": defauts.get("statut", "DEMANDE"),
                    "priorite": priorite,
                    "date_demande": date_demande,
                    "notes": f"Créé automatiquement depuis email" + (f" - Réf: {numero_os}" if numero_os else "")
                }
            )
            session.commit()
            int_id = intervention_id.scalar()

            logger.info(
                "intervention_created_from_email",
                intervention_id=str(int_id),
                numero=numero,
                numero_os=numero_os,
                donneur_ordre=donneur_info.get("donneur_ordre") if donneur_info else None,
                contact_nom=contact_nom,
                ville=ville,
                sender=sender_email
            )

            return numero

    def _send_auto_reply(self, to_email: str, original_subject: str, numero: str):
        """Envoie une réponse automatique."""
        notif = self.config.get("notifications", {})
        if not notif.get("reponse_auto", False):
            return

        if not self.smtp_host:
            logger.warning("smtp_not_configured", message="Réponse auto désactivée")
            return

        try:
            subject = notif.get("reponse_sujet", "Re: {sujet_original}").format(
                sujet_original=original_subject,
                numero=numero
            )
            body = notif.get("reponse_corps", "Intervention {numero} créée.").format(
                numero=numero
            )

            msg = MIMEMultipart()
            msg["From"] = self.imap_user
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.imap_user, self.imap_password)
                server.send_message(msg)

            logger.info("auto_reply_sent", to=to_email, numero=numero)

        except Exception as e:
            logger.error("auto_reply_failed", to=to_email, error=str(e))

    def process_emails(self) -> List[str]:
        """
        Traite les emails et crée les interventions.
        Retourne la liste des numéros d'interventions créées.
        """
        if not self.is_configured():
            logger.debug("email_to_intervention_not_configured")
            return []

        created = []
        # Priorité: config DB > config YAML
        folder = self.db_config.get("imap_dossier") or self.config.get("imap", {}).get("dossier_source", "INBOX")

        try:
            imap = self._connect_imap()
            imap.select(folder)

            # Rechercher les emails non lus
            status, messages = imap.search(None, "UNSEEN")
            if status != "OK":
                return []

            email_ids = messages[0].split()
            logger.info("emails_found", count=len(email_ids), folder=folder, mots_cles=self.db_config.get("mots_cles"))

            for email_id in email_ids:
                try:
                    status, msg_data = imap.fetch(email_id, "(RFC822)")
                    if status != "OK":
                        continue

                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    # Décoder l'objet
                    subject = self._decode_header_value(msg.get("Subject", ""))
                    from_header = msg.get("From", "")
                    sender_email = self._extract_email_address(from_header)

                    # Extraire le corps
                    body = self._get_email_body(msg)

                    logger.info("processing_email", email_id=str(email_id), subject=subject[:80], sender=sender_email)

                    # Ignorer les réponses (Re:, RE:, Fwd:, TR:) pour éviter les doublons
                    subject_clean = subject.strip()
                    if re.match(r'^(Re|RE|Fwd|FWD|TR|Tr)\s*:', subject_clean):
                        logger.info("skipping_reply_email", subject=subject[:50])
                        # Marquer comme lu pour ne pas le retraiter
                        imap.store(email_id, "+FLAGS", "\\Seen")
                        continue

                    # 1) Vérifier d'abord si c'est un donneur d'ordre connu (INTERPARTNER etc)
                    donneur_info = self._matches_donneur_ordre(subject)
                    logger.info("donneur_ordre_check", donneur_info=donneur_info)
                    keyword = None
                    parsed_data = None

                    if donneur_info:
                        # Donneur d'ordre détecté - parser le corps du mail
                        logger.info(
                            "email_matches_donneur_ordre",
                            subject=subject[:50],
                            sender=sender_email,
                            donneur_ordre=donneur_info.get("donneur_ordre"),
                            numero_os=donneur_info.get("numero_os")
                        )

                        # Parser selon le type de donneur d'ordre
                        donneur_nom = donneur_info.get("donneur_ordre", "").upper()
                        if "INTERPARTNER" in donneur_nom:
                            parsed_data = self._parse_interpartner_email(body)
                            # Le numero_os peut venir du sujet ou du corps
                            if not parsed_data.get("numero_os") and donneur_info.get("numero_os"):
                                parsed_data["numero_os"] = donneur_info.get("numero_os")

                    else:
                        # 2) Fallback: vérifier les mots-clés
                        keyword = self._matches_keywords(subject)
                        if not keyword:
                            # Ni donneur d'ordre ni mot-clé - ignorer cet email
                            continue

                        logger.info(
                            "email_matches_keyword",
                            subject=subject[:50],
                            sender=sender_email,
                            keyword=keyword
                        )

                    # Trouver ou créer le client à partir des données parsées
                    client_id = None
                    try:
                        if parsed_data and parsed_data.get("contact_nom"):
                            # Utiliser les données du mail (INTERPARTNER, etc.)
                            client_id = self._find_or_create_client(
                                contact_nom=parsed_data.get("contact_nom"),
                                contact_telephone=parsed_data.get("contact_telephone"),
                                contact_email=sender_email,
                                adresse=parsed_data.get("adresse_intervention"),
                                code_postal=parsed_data.get("code_postal"),
                                ville=parsed_data.get("ville")
                            )
                        elif self.config.get("extraction", {}).get("client_par_email", True):
                            # Fallback: chercher par email expéditeur
                            client = self._find_client_by_email(sender_email)
                            client_id = str(client["id"]) if client else None
                    except Exception as e:
                        logger.debug("client_search_or_create_failed", error=str(e))

                    # Créer l'intervention
                    numero = self._create_intervention(
                        client={"id": client_id} if client_id else None,
                        subject=subject,
                        body=body,
                        sender_email=sender_email,
                        keyword=keyword,
                        donneur_info=donneur_info,
                        parsed_data=parsed_data
                    )

                    if numero:
                        created.append(numero)

                        # Marquer comme lu
                        imap.store(email_id, "+FLAGS", "\\Seen")

                        # Déplacer si configuré
                        dest_folder = self.db_config.get("imap_dossier_traite") or self.config.get("imap", {}).get("dossier_traite")
                        if dest_folder:
                            try:
                                imap.copy(email_id, dest_folder)
                                imap.store(email_id, "+FLAGS", "\\Deleted")
                            except Exception as e:
                                logger.warning("email_move_failed", error=str(e))

                        # Envoyer réponse auto
                        self._send_auto_reply(sender_email, subject, numero)

                except Exception as e:
                    logger.error("email_processing_error", email_id=email_id, error=str(e))
                    continue

            imap.expunge()
            imap.close()
            imap.logout()

        except Exception as e:
            logger.error("imap_connection_error", error=str(e))

        return created


# =============================================================================
# SCHEDULER
# =============================================================================
class EmailToInterventionScheduler:
    """Scheduler pour le polling périodique des emails."""

    _instance = None
    _task = None

    @classmethod
    async def start(cls, tenant_id: UUID):
        """Démarre le scheduler."""
        config = load_config()
        if not config.get("actif", False):
            logger.info("email_to_intervention_disabled")
            return

        interval = config.get("intervalle_polling", 300)
        cls._instance = cls(tenant_id, interval)
        cls._task = asyncio.create_task(cls._instance._run())
        logger.info("email_to_intervention_scheduler_started", interval=interval)

    @classmethod
    async def stop(cls):
        """Arrête le scheduler."""
        if cls._task:
            cls._task.cancel()
            try:
                await cls._task
            except asyncio.CancelledError:
                pass
            logger.info("email_to_intervention_scheduler_stopped")

    def __init__(self, tenant_id: UUID, interval: int):
        self.tenant_id = tenant_id
        self.interval = interval
        self.service = EmailToInterventionService(tenant_id)

    async def _run(self):
        """Boucle principale du scheduler."""
        while True:
            try:
                await asyncio.sleep(self.interval)

                if self.service.is_configured():
                    created = self.service.process_emails()
                    if created:
                        logger.info(
                            "interventions_created_from_emails",
                            count=len(created),
                            numeros=created
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("email_scheduler_error", error=str(e))
                await asyncio.sleep(60)  # Attendre avant de réessayer


# =============================================================================
# API ENDPOINTS
# =============================================================================
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from .tenant import get_current_tenant

router = APIRouter(prefix="/email-to-intervention", tags=["Email to Intervention"])


class EmailConfigResponse(BaseModel):
    actif: bool
    intervalle_polling: int
    mots_cles: List[str]
    imap_configured: bool


class ProcessResult(BaseModel):
    interventions_creees: List[str]
    count: int


@router.get("/config", response_model=EmailConfigResponse)
async def get_config():
    """Retourne la configuration du service."""
    config = load_config()
    imap_configured = bool(
        os.getenv("EMAIL_IMAP_HOST")
        and os.getenv("EMAIL_IMAP_USER")
        and os.getenv("EMAIL_IMAP_PASSWORD")
    )
    return EmailConfigResponse(
        actif=config.get("actif", False),
        intervalle_polling=config.get("intervalle_polling", 300),
        mots_cles=config.get("mots_cles", []),
        imap_configured=imap_configured
    )


@router.post("/process", response_model=ProcessResult)
async def process_emails_now(tenant_id: UUID = Depends(get_current_tenant)):
    """Traite immédiatement les emails (déclenchement manuel)."""

    service = EmailToInterventionService(tenant_id)
    if not service.is_configured():
        raise HTTPException(400, "Service non configuré (vérifier configuration mail)")

    created = service.process_emails()

    # Mettre à jour le statut en base
    _update_mail_status(tenant_id, f"OK - {len(created)} intervention(s) créée(s)")

    return ProcessResult(
        interventions_creees=created,
        count=len(created)
    )


class TestConnectionResult(BaseModel):
    imap_ok: bool
    imap_message: str
    smtp_ok: bool
    smtp_message: str
    emails_non_lus: int = 0


@router.post("/test-connexion", response_model=TestConnectionResult)
async def test_connexion(tenant_id: UUID = Depends(get_current_tenant)):
    """Teste la connexion IMAP et SMTP."""

    service = EmailToInterventionService(tenant_id)
    result = {
        "imap_ok": False,
        "imap_message": "Non configuré",
        "smtp_ok": False,
        "smtp_message": "Non configuré",
        "emails_non_lus": 0
    }

    # Test IMAP
    if service.imap_host and service.imap_user and service.imap_password:
        try:
            imap = service._connect_imap()
            imap.select("INBOX")
            status, messages = imap.search(None, "UNSEEN")
            if status == "OK":
                count = len(messages[0].split()) if messages[0] else 0
                result["imap_ok"] = True
                result["imap_message"] = f"Connecté - {count} email(s) non lu(s)"
                result["emails_non_lus"] = count
            imap.close()
            imap.logout()
        except Exception as e:
            result["imap_message"] = f"Erreur: {str(e)[:100]}"

    # Test SMTP
    if service.smtp_host:
        smtp_user = service.db_config.get("smtp_user") or service.imap_user
        smtp_pass = service.db_config.get("smtp_password") or service.imap_password
        if smtp_user and smtp_pass:
            try:
                with smtplib.SMTP(service.smtp_host, service.smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    result["smtp_ok"] = True
                    result["smtp_message"] = "Connecté"
            except Exception as e:
                result["smtp_message"] = f"Erreur: {str(e)[:100]}"

    # Mettre à jour le statut
    status_msg = f"IMAP: {'OK' if result['imap_ok'] else 'KO'}, SMTP: {'OK' if result['smtp_ok'] else 'KO'}"
    _update_mail_status(tenant_id, status_msg)

    return TestConnectionResult(**result)


def _update_mail_status(tenant_id: UUID, status: str):
    """Met à jour le statut de dernière vérification."""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text
            session.execute(
                text("""
                    UPDATE azalplus.administration_mail
                    SET derniere_verification = NOW(),
                        dernier_statut = :status,
                        updated_at = NOW()
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": str(tenant_id), "status": status[:200]}
            )
            session.commit()
    except Exception as e:
        logger.debug("update_mail_status_failed", error=str(e))
# Reload trigger Thu Mar 19 11:11:58 UTC 2026
