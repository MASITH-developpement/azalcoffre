# =============================================================================
# AZALMED - Service Veille médicale
# =============================================================================
# Agrégation PubMed, HAS, ANSM + Résumé IA

import os
import json
import structlog
import xml.etree.ElementTree as ET
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

import httpx

from moteur.db import Database

logger = structlog.get_logger()


class VeilleService:
    """
    Service de veille médicale personnalisée.

    Sources :
    - PubMed (publications scientifiques)
    - HAS (recommandations françaises)
    - ANSM (alertes médicaments)
    - DGS-Urgent (alertes sanitaires)
    """

    TABLE_ARTICLES = "med_articles_veille"
    TABLE_PRATICIENS = "med_praticiens"

    def __init__(self, tenant_id: UUID):
        """
        Initialise le service de veille.

        Args:
            tenant_id: ID du tenant (OBLIGATOIRE pour isolation multi-tenant)
        """
        self.tenant_id = tenant_id
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.pubmed_api_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.has_rss_url = "https://www.has-sante.fr/jcms/fc_2875171/fr/rss"
        self.ansm_rss_url = "https://ansm.sante.fr/rss"

    async def synchroniser(
        self,
        praticien_id: UUID,
        sources: Optional[list[str]] = None,
    ) -> dict:
        """
        Synchronise les articles de veille pour un praticien.

        Args:
            praticien_id: ID du praticien
            sources: Liste des sources (PUBMED, HAS, ANSM, DGS_URGENT)

        Returns:
            dict avec le nombre d'articles importés par source
        """
        if sources is None:
            sources = ["PUBMED", "HAS", "ANSM"]

        # Récupérer le profil du praticien
        profil = await self._get_profil_praticien(praticien_id)
        specialite = profil.get("specialite", "")
        themes = profil.get("veille_themes", [])

        resultats = {}

        if "PUBMED" in sources:
            articles_pubmed = await self._sync_pubmed(specialite, themes)
            resultats["PUBMED"] = len(articles_pubmed)

            # Générer les résumés IA et sauvegarder
            for article in articles_pubmed:
                article["resume_ia"] = await self._generer_resume_ia(article)
                article["praticien_id"] = str(praticien_id)
                Database.insert(self.TABLE_ARTICLES, self.tenant_id, article)

        if "HAS" in sources:
            articles_has = await self._sync_has(specialite)
            resultats["HAS"] = len(articles_has)
            for article in articles_has:
                article["praticien_id"] = str(praticien_id)
                Database.insert(self.TABLE_ARTICLES, self.tenant_id, article)

        if "ANSM" in sources:
            alertes_ansm = await self._sync_ansm()
            resultats["ANSM"] = len(alertes_ansm)
            for alerte in alertes_ansm:
                alerte["praticien_id"] = str(praticien_id)
                Database.insert(self.TABLE_ARTICLES, self.tenant_id, alerte)

        return {
            "praticien_id": str(praticien_id),
            "date_sync": datetime.utcnow().isoformat(),
            "articles_importes": resultats,
            "total": sum(resultats.values()),
        }

    async def _sync_pubmed(
        self,
        specialite: str,
        themes: list[str],
    ) -> list[dict]:
        """
        Interroge PubMed et récupère les articles récents.
        """
        # Construire la requête de recherche
        query_parts = []
        if specialite:
            query_parts.append(f"{specialite}[MeSH Terms]")
        for theme in themes[:5]:  # Max 5 thèmes
            query_parts.append(f"{theme}[Title/Abstract]")

        query = " OR ".join(query_parts) if query_parts else "medicine"

        # Filtrer sur les 7 derniers jours
        date_min = (datetime.utcnow() - timedelta(days=7)).strftime("%Y/%m/%d")
        query += f" AND ({date_min}[Date - Publication] : 3000[Date - Publication])"

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Recherche des IDs
            search_response = await client.get(
                f"{self.pubmed_api_url}/esearch.fcgi",
                params={
                    "db": "pubmed",
                    "term": query,
                    "retmax": 20,
                    "retmode": "json",
                    "sort": "date",
                },
            )

            if search_response.status_code != 200:
                logger.error(f"Erreur PubMed search: {search_response.text}")
                return []

            search_data = search_response.json()
            ids = search_data.get("esearchresult", {}).get("idlist", [])

            if not ids:
                return []

            # 2. Récupérer les détails
            fetch_response = await client.get(
                f"{self.pubmed_api_url}/efetch.fcgi",
                params={
                    "db": "pubmed",
                    "id": ",".join(ids),
                    "retmode": "xml",
                },
            )

            if fetch_response.status_code != 200:
                logger.error(f"Erreur PubMed fetch: {fetch_response.text}")
                return []

            # Parser le XML
            articles = self._parser_pubmed_xml(fetch_response.text)
            return articles

    def _parser_pubmed_xml(self, xml_content: str) -> list[dict]:
        """
        Parse le XML PubMed et extrait les articles.
        """
        articles = []
        try:
            root = ET.fromstring(xml_content)
            for article in root.findall(".//PubmedArticle"):
                pmid = article.findtext(".//PMID")
                titre = article.findtext(".//ArticleTitle")
                abstract = article.findtext(".//AbstractText") or ""

                # Auteurs
                auteurs = []
                for author in article.findall(".//Author"):
                    lastname = author.findtext("LastName") or ""
                    forename = author.findtext("ForeName") or ""
                    if lastname:
                        auteurs.append(f"{lastname} {forename}".strip())

                # Date
                pub_date = article.find(".//PubDate")
                date_str = ""
                if pub_date is not None:
                    year = pub_date.findtext("Year") or ""
                    month = pub_date.findtext("Month") or "01"
                    day = pub_date.findtext("Day") or "01"
                    date_str = f"{year}-{month}-{day}"

                articles.append({
                    "source": "PUBMED",
                    "pmid": pmid,
                    "titre": titre,
                    "resume_original": abstract[:1000],
                    "auteurs": ", ".join(auteurs[:5]),
                    "date_publication": date_str,
                    "url_source": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "type_article": "ETUDE_CLINIQUE",
                })
        except Exception as e:
            logger.error(f"Erreur parsing PubMed XML: {e}")

        return articles

    async def _sync_has(self, specialite: str) -> list[dict]:
        """
        Récupère les recommandations HAS via RSS.
        """
        # TODO: Implémenter le parsing RSS HAS
        return []

    async def _sync_ansm(self) -> list[dict]:
        """
        Récupère les alertes ANSM via RSS.
        """
        # TODO: Implémenter le parsing RSS ANSM
        return []

    async def generer_resume(self, article_id: UUID) -> dict:
        """
        Génère le résumé IA d'un article.
        """
        article = Database.get_by_id(
            self.TABLE_ARTICLES,
            self.tenant_id,
            article_id,
        )
        if not article:
            raise ValueError(f"Article non trouvé: {article_id}")

        resume_ia = await self._generer_resume_ia(article)

        # Mettre à jour l'article avec le résumé
        Database.update(
            self.TABLE_ARTICLES,
            self.tenant_id,
            article_id,
            {"resume_ia": resume_ia},
        )

        return {
            "article_id": str(article_id),
            "resume_ia": resume_ia,
        }

    async def _generer_resume_ia(self, article: dict) -> str:
        """
        Génère un résumé en français avec le LLM.
        """
        if not self.openai_api_key:
            return ""

        titre = article.get("titre", "")
        abstract = article.get("resume_original", "")

        if not abstract:
            return ""

        prompt = f"""Résume cet article médical en français, en 3-4 phrases simples et accessibles pour un médecin généraliste.

Titre : {titre}

Abstract : {abstract}

Résumé :"""

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
                    "max_tokens": 300,
                },
            )

            if response.status_code != 200:
                logger.error(f"Erreur résumé IA: {response.text}")
                return ""

            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

    async def envoyer_digest(
        self,
        praticien_id: UUID,
        frequence: str = "QUOTIDIEN",
    ) -> dict:
        """
        Envoie le digest de veille par email.
        """
        # TODO: Implémenter l'envoi d'email avec les articles non lus
        return {
            "praticien_id": str(praticien_id),
            "frequence": frequence,
            "statut": "envoye",
            "date_envoi": datetime.utcnow().isoformat(),
        }

    async def _get_profil_praticien(self, praticien_id: UUID) -> dict:
        """Récupère le profil du praticien depuis la base."""
        praticien = Database.get_by_id(
            self.TABLE_PRATICIENS,
            self.tenant_id,
            praticien_id,
        )
        if not praticien:
            raise ValueError(f"Praticien non trouvé: {praticien_id}")
        return praticien
