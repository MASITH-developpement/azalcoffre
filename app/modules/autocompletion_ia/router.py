# AZALPLUS - Router API Autocompletion IA
from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from .schemas import (
    CompletionRequest,
    CompletionResponse,
    ConfigResponse,
    ConfigUpdateRequest,
    FeedbackRequest,
    HealthResponse,
    StatsResponse,
    SuggestionRequest,
    SuggestionResponse,
)
from .service import AutocompletionIAService
from . import entreprise_lookup


# Schémas pour la recherche d'entreprise
class EntrepriseResponse(BaseModel):
    """Réponse avec les données de l'entreprise."""
    nom: str = ""
    raison_sociale: str = ""
    siret: str = ""
    siren: str = ""
    tva_intracommunautaire: str = ""
    code_naf: str = ""
    forme_juridique: str = ""
    adresse: str = ""
    complement_adresse: str = ""
    code_postal: str = ""
    ville: str = ""
    pays: str = "France"
    date_creation: str = ""
    effectif: str = ""
    categorie_entreprise: str = ""


class EntrepriseSearchResponse(BaseModel):
    """Réponse avec plusieurs entreprises."""
    resultats: list[EntrepriseResponse]
    total: int


class AutoFillRequest(BaseModel):
    """Requête pour auto-remplir des champs avec l'IA."""
    module: str
    champ_source: str
    valeur_source: str
    champs_cibles: list[str]
    contexte: Optional[dict] = None


class AutoFillResponse(BaseModel):
    """Réponse avec les valeurs suggérées pour chaque champ."""
    champs: dict[str, str]
    source: str  # "api_gouv", "ia", "mixte"
    confiance: float = 1.0

# Import des dépendances AZALPLUS
try:
    from moteur.auth import require_auth
    from moteur.tenant import get_current_tenant
    from moteur.db import Database
except ImportError:
    # Fallback si import échoue
    require_auth = None
    get_current_tenant = None
    Database = None

router = APIRouter(tags=["Autocompletion IA"])
# Router public pour les recherches d'entreprise (données publiques gov.fr)
public_router = APIRouter(tags=["Recherche Entreprise"])


# -----------------------------------------------------------------------------
# Dépendances
# -----------------------------------------------------------------------------
async def get_service(
    user: dict = Depends(require_auth) if require_auth else None,
    tenant_id: UUID = Depends(get_current_tenant) if get_current_tenant else None,
) -> AutocompletionIAService:
    """Créer le service d'autocomplétion."""
    # Utiliser un tenant_id par défaut si non disponible
    if tenant_id is None:
        from uuid import uuid4
        tenant_id = uuid4()
    return AutocompletionIAService(db=None, tenant_id=tenant_id, cache=None)


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@router.post(
    "/suggest",
    response_model=SuggestionResponse,
    summary="Obtenir des suggestions",
    description="Retourne des suggestions d'autocomplétion basées sur l'IA",
)
async def get_suggestions(
    request: SuggestionRequest,
    service: AutocompletionIAService = Depends(get_service),
) -> SuggestionResponse:
    """
    Obtenir des suggestions d'autocomplétion.

    - **module**: Nom du module (ex: Clients, Factures)
    - **champ**: Nom du champ (ex: nom, email)
    - **valeur**: Valeur actuelle saisie par l'utilisateur
    - **limite**: Nombre de suggestions souhaitées (1-10)
    """
    try:
        return await service.get_suggestions(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la génération des suggestions: {str(e)}",
        )


@router.post(
    "/complete",
    response_model=CompletionResponse,
    summary="Compléter un texte",
    description="Complète un texte long (textarea) avec l'IA",
)
async def complete_text(
    request: CompletionRequest,
    service: AutocompletionIAService = Depends(get_service),
) -> CompletionResponse:
    """
    Compléter un texte long.

    Utile pour les champs de type textarea comme les descriptions,
    les notes, les rapports d'intervention, etc.
    """
    try:
        return await service.complete_text(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la complétion: {str(e)}",
        )


@router.post(
    "/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Envoyer un feedback",
    description="Enregistre si une suggestion a été acceptée ou non",
)
async def send_feedback(
    request: FeedbackRequest,
    service: AutocompletionIAService = Depends(get_service),
) -> None:
    """
    Envoyer un feedback sur une suggestion.

    Permet d'améliorer les suggestions futures en apprenant
    des choix des utilisateurs.

    - **suggestion_id**: ID de la suggestion reçue
    - **accepted**: true si l'utilisateur a accepté la suggestion
    - **valeur_finale**: La valeur finalement saisie (optionnel)
    - **module**: Nom du module (optionnel mais recommandé)
    - **champ**: Nom du champ (optionnel mais recommandé)
    - **suggestion_texte**: Texte de la suggestion (optionnel mais recommandé)
    """
    await service.record_feedback(
        request=request,
        module=request.module,
        champ=request.champ,
        suggestion_texte=request.suggestion_texte,
    )


@router.get(
    "/config",
    response_model=ConfigResponse,
    summary="Obtenir la configuration",
    description="Retourne la configuration actuelle de l'autocomplétion IA",
)
async def get_config(
    service: AutocompletionIAService = Depends(get_service),
) -> ConfigResponse:
    """Obtenir la configuration actuelle."""
    return await service.get_config()


@router.put(
    "/config",
    response_model=ConfigResponse,
    summary="Mettre à jour la configuration",
    description="Met à jour la configuration de l'autocomplétion IA",
)
@router.patch(
    "/config",
    response_model=ConfigResponse,
    summary="Mettre à jour la configuration (partiel)",
    description="Met à jour partiellement la configuration",
)
async def update_config(
    request: ConfigUpdateRequest,
    service: AutocompletionIAService = Depends(get_service),
) -> ConfigResponse:
    """
    Mettre à jour la configuration.

    Seuls les champs fournis seront mis à jour.
    """
    return await service.update_config(request)


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Obtenir les statistiques",
    description="Retourne les statistiques d'utilisation",
)
async def get_stats(
    date_debut: date = Query(..., description="Date de début"),
    date_fin: date = Query(..., description="Date de fin"),
    service: AutocompletionIAService = Depends(get_service),
) -> StatsResponse:
    """
    Obtenir les statistiques d'utilisation.

    Inclut le nombre de requêtes, tokens utilisés, coût estimé,
    taux de cache, etc.
    """
    return await service.get_stats(date_debut, date_fin)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Vérifier l'état",
    description="Vérifie l'état des providers IA et du cache",
)
async def health_check(
    service: AutocompletionIAService = Depends(get_service),
) -> dict[str, Any]:
    """
    Vérifier l'état de santé des providers.

    Retourne le statut de connexion pour OpenAI, Anthropic,
    le provider local et le cache.
    """
    return await service.health_check()


@router.post(
    "/test",
    response_model=SuggestionResponse,
    summary="Tester l'autocomplétion",
    description="Endpoint de test pour vérifier la configuration",
)
async def test_autocompletion(
    provider: str = Query(default="anthropic", description="Provider à tester"),
    service: AutocompletionIAService = Depends(get_service),
) -> SuggestionResponse:
    """
    Tester l'autocomplétion avec un exemple simple.

    Utile pour vérifier que les clés API sont correctement configurées.
    """
    test_request = SuggestionRequest(
        module="Test",
        champ="nom",
        valeur="Dup",
        limite=3,
        provider=provider,
    )
    return await service.get_suggestions(test_request)


@router.get(
    "/learned",
    response_model=SuggestionResponse,
    summary="Suggestions apprises",
    description="Récupère les suggestions basées sur le feedback utilisateur",
)
async def get_learned_suggestions(
    module: str = Query(..., description="Nom du module (ex: Clients)"),
    champ: str = Query(..., description="Nom du champ (ex: nom)"),
    prefix: str = Query(default="", description="Préfixe pour filtrer"),
    limit: int = Query(default=5, ge=1, le=20, description="Nombre max de suggestions"),
    min_acceptance_rate: float = Query(default=0.5, ge=0, le=1, description="Taux d'acceptation minimum"),
    min_total_count: int = Query(default=2, ge=1, description="Nombre minimum d'utilisations"),
    service: AutocompletionIAService = Depends(get_service),
) -> SuggestionResponse:
    """
    Récupérer les suggestions apprises basées sur le feedback utilisateur.

    Ces suggestions sont celles qui ont été le plus souvent acceptées
    par les utilisateurs pour ce module/champ spécifique.
    """
    import time
    start_time = time.time()

    suggestions = await service.get_learned_suggestions(
        module=module,
        champ=champ,
        prefix=prefix,
        limit=limit,
        min_acceptance_rate=min_acceptance_rate,
        min_total_count=min_total_count,
    )

    latency_ms = int((time.time() - start_time) * 1000)

    from .schemas import SuggestionMeta
    return SuggestionResponse(
        suggestions=suggestions,
        meta=SuggestionMeta(
            cached=False,
            latency_ms=latency_ms,
        ),
    )


# -----------------------------------------------------------------------------
# Endpoints Recherche Entreprise (SIRET/SIREN) - PUBLICS
# -----------------------------------------------------------------------------
@public_router.get(
    "/entreprise/siret/{siret}",
    response_model=EntrepriseResponse,
    summary="Rechercher par SIRET",
    description="Recherche les informations d'une entreprise par son numéro SIRET",
)
async def lookup_entreprise_siret(siret: str) -> EntrepriseResponse:
    """
    Rechercher une entreprise par son SIRET (14 chiffres).

    Utilise l'API gouvernementale française pour récupérer:
    - Nom et raison sociale
    - Adresse complète
    - SIREN et numéro TVA intracommunautaire
    - Code NAF et forme juridique
    """
    result = await entreprise_lookup.lookup_by_siret(siret)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entreprise non trouvée pour le SIRET: {siret}",
        )
    return EntrepriseResponse(**result)


@public_router.get(
    "/entreprise/siren/{siren}",
    response_model=EntrepriseResponse,
    summary="Rechercher par SIREN",
    description="Recherche les informations d'une entreprise par son numéro SIREN",
)
async def lookup_entreprise_siren(siren: str) -> EntrepriseResponse:
    """
    Rechercher une entreprise par son SIREN (9 chiffres).
    """
    result = await entreprise_lookup.lookup_by_siren(siren)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entreprise non trouvée pour le SIREN: {siren}",
        )
    return EntrepriseResponse(**result)


@public_router.get(
    "/entreprise/search",
    response_model=EntrepriseSearchResponse,
    summary="Rechercher par nom",
    description="Recherche des entreprises par leur nom ou celui d'un particulier",
)
async def search_entreprise(
    q: str = Query(..., min_length=3, description="Nom de l'entreprise"),
    limit: int = Query(default=5, ge=1, le=20, description="Nombre de résultats"),
) -> EntrepriseSearchResponse:
    """
    Rechercher des entreprises par nom.

    Retourne une liste d'entreprises correspondantes.
    """
    results = await entreprise_lookup.search_by_name(q, limit)
    return EntrepriseSearchResponse(
        resultats=[EntrepriseResponse(**r) for r in results],
        total=len(results),
    )


# -----------------------------------------------------------------------------
# Endpoint Auto-remplissage IA
# -----------------------------------------------------------------------------
@router.post(
    "/autofill",
    response_model=AutoFillResponse,
    summary="Auto-remplir des champs",
    description="Utilise l'IA et/ou l'API gouvernementale pour suggérer des valeurs",
)
async def autofill_fields(
    request: AutoFillRequest,
    service: AutocompletionIAService = Depends(get_service),
) -> AutoFillResponse:
    """
    Auto-remplir des champs basé sur une valeur source.

    Exemple: À partir d'un SIRET, remplir automatiquement:
    - nom, raison_sociale, adresse, code_postal, ville, siren, tva_intracommunautaire

    Utilise l'API gouvernementale pour les données officielles,
    et l'IA (Claude/ChatGPT) pour enrichir si nécessaire.
    """
    champs_remplis = {}
    source = "ia"
    confiance = 0.8

    # Si le champ source est un SIRET ou SIREN, utiliser l'API gouvernementale
    champ_lower = request.champ_source.lower()
    valeur = request.valeur_source.replace(" ", "").replace(".", "")

    if "siret" in champ_lower and len(valeur) == 14:
        # Lookup par SIRET
        entreprise = await entreprise_lookup.lookup_by_siret(valeur)
        if entreprise:
            source = "api_gouv"
            confiance = 1.0
            # Mapper les champs demandés
            mapping = {
                "nom": entreprise.get("nom", ""),
                "raison_sociale": entreprise.get("raison_sociale", ""),
                "nom_entreprise": entreprise.get("nom", ""),
                "adresse": entreprise.get("adresse", ""),
                "adresse_ligne1": entreprise.get("adresse", ""),
                "complement_adresse": entreprise.get("complement_adresse", ""),
                "adresse_ligne2": entreprise.get("complement_adresse", ""),
                "code_postal": entreprise.get("code_postal", ""),
                "cp": entreprise.get("code_postal", ""),
                "ville": entreprise.get("ville", ""),
                "pays": entreprise.get("pays", "France"),
                "siren": entreprise.get("siren", ""),
                "tva_intracommunautaire": entreprise.get("tva_intracommunautaire", ""),
                "tva_intra": entreprise.get("tva_intracommunautaire", ""),
                "numero_tva": entreprise.get("tva_intracommunautaire", ""),
                "code_naf": entreprise.get("code_naf", ""),
                "naf": entreprise.get("code_naf", ""),
                "forme_juridique": entreprise.get("forme_juridique", ""),
                "date_creation": entreprise.get("date_creation", ""),
                "effectif": entreprise.get("effectif", ""),
            }
            for champ in request.champs_cibles:
                champ_norm = champ.lower().replace("-", "_")
                if champ_norm in mapping and mapping[champ_norm]:
                    champs_remplis[champ] = mapping[champ_norm]

    elif "siren" in champ_lower and len(valeur) == 9:
        # Lookup par SIREN
        entreprise = await entreprise_lookup.lookup_by_siren(valeur)
        if entreprise:
            source = "api_gouv"
            confiance = 1.0
            mapping = {
                "nom": entreprise.get("nom", ""),
                "raison_sociale": entreprise.get("raison_sociale", ""),
                "nom_entreprise": entreprise.get("nom", ""),
                "adresse": entreprise.get("adresse", ""),
                "siret": entreprise.get("siret", ""),
                "code_postal": entreprise.get("code_postal", ""),
                "ville": entreprise.get("ville", ""),
                "tva_intracommunautaire": entreprise.get("tva_intracommunautaire", ""),
                "code_naf": entreprise.get("code_naf", ""),
                "forme_juridique": entreprise.get("forme_juridique", ""),
            }
            for champ in request.champs_cibles:
                champ_norm = champ.lower().replace("-", "_")
                if champ_norm in mapping and mapping[champ_norm]:
                    champs_remplis[champ] = mapping[champ_norm]

    # Si on n'a pas trouvé via l'API ou si des champs manquent, utiliser l'IA
    champs_manquants = [c for c in request.champs_cibles if c not in champs_remplis]

    if champs_manquants and request.valeur_source:
        try:
            # Construire un prompt pour l'IA
            prompt = f"""Tu dois suggérer des valeurs pour des champs d'un formulaire.

Module: {request.module}
Champ source: {request.champ_source}
Valeur source: "{request.valeur_source}"

Champs à remplir: {', '.join(champs_manquants)}

{f"Contexte additionnel: {request.contexte}" if request.contexte else ""}

Réponds UNIQUEMENT en JSON avec le format:
{{"champ1": "valeur1", "champ2": "valeur2"}}

Ne suggère que les champs pour lesquels tu as une forte confiance."""

            # Appeler l'IA via le service
            import json
            suggestions = await service._get_provider().complete_text(
                prompt=prompt,
                system_prompt="Tu es un assistant qui aide à remplir des formulaires. Réponds uniquement en JSON valide.",
                temperature=0.3,
                max_tokens=500,
            )

            # Parser la réponse JSON
            try:
                # Nettoyer la réponse (enlever les blocs markdown si présents)
                clean_response = suggestions.strip()
                if clean_response.startswith("```"):
                    clean_response = clean_response.split("\n", 1)[1]
                    clean_response = clean_response.rsplit("```", 1)[0]

                ia_values = json.loads(clean_response)
                for champ, valeur in ia_values.items():
                    if champ in champs_manquants and valeur:
                        champs_remplis[champ] = str(valeur)

                if source == "api_gouv" and ia_values:
                    source = "mixte"
                elif ia_values:
                    source = "ia"
                    confiance = 0.7
            except json.JSONDecodeError:
                pass
        except Exception as e:
            # L'IA a échoué, on retourne ce qu'on a
            pass

    return AutoFillResponse(
        champs=champs_remplis,
        source=source,
        confiance=confiance,
    )


# -----------------------------------------------------------------------------
# Endpoints Lookup multi-sources (public)
# -----------------------------------------------------------------------------
from . import data_lookup


class AdresseResponse(BaseModel):
    """Réponse avec les données d'adresse."""
    adresse_complete: str = ""
    numero: str = ""
    rue: str = ""
    code_postal: str = ""
    ville: str = ""
    departement: str = ""
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    score: float = 0


class AdresseSearchResponse(BaseModel):
    """Réponse avec plusieurs adresses."""
    resultats: list[AdresseResponse]
    total: int


class ProduitResponse(BaseModel):
    """Réponse avec les données d'un produit."""
    code_barres: str = ""
    nom: str = ""
    marque: str = ""
    categorie: str = ""
    quantite: str = ""
    nutriscore: str = ""
    ecoscore: str = ""
    origine: str = ""
    image_url: str = ""
    ingredients: str = ""
    allergenes: str = ""
    labels: str = ""


class TVAValidationResponse(BaseModel):
    """Réponse de validation TVA."""
    valid: bool
    numero_tva: str = ""
    pays: str = ""
    nom: str = ""
    adresse: str = ""
    date_verification: str = ""
    error: Optional[str] = None


class IBANValidationResponse(BaseModel):
    """Réponse de validation IBAN."""
    valid: bool
    iban_formate: str = ""
    pays: str = ""
    code_banque: str = ""
    code_guichet: str = ""
    numero_compte: str = ""
    cle_rib: str = ""
    error: Optional[str] = None


class BICResponse(BaseModel):
    """Réponse avec les infos BIC."""
    valid: bool
    bic: str = ""
    code_banque: str = ""
    pays: str = ""
    localisation: str = ""
    branche: str = ""
    nom_banque: str = ""
    error: Optional[str] = None


class SmartLookupRequest(BaseModel):
    """Requête de lookup intelligent."""
    valeur: str
    type_champ: Optional[str] = None


class SmartLookupResponse(BaseModel):
    """Réponse du lookup intelligent."""
    type: str = ""
    source: str = ""
    data: dict = {}
    found: bool = False


@public_router.get(
    "/adresse/search",
    response_model=AdresseSearchResponse,
    summary="Rechercher une adresse",
    description="Recherche d'adresses via l'API Adresse du gouvernement",
)
async def search_address(
    q: str = Query(..., min_length=3, description="Adresse à rechercher"),
    limit: int = Query(default=5, ge=1, le=20, description="Nombre de résultats"),
) -> AdresseSearchResponse:
    """Rechercher des adresses par texte."""
    results = await data_lookup.search_address(q, limit)
    return AdresseSearchResponse(
        resultats=[AdresseResponse(**r) for r in results],
        total=len(results),
    )


@public_router.get(
    "/adresse/cp/{code_postal}",
    response_model=AdresseResponse,
    summary="Ville par code postal",
    description="Récupère la ville à partir d'un code postal",
)
async def get_city_by_postal_code(code_postal: str) -> AdresseResponse:
    """Récupérer la ville depuis un code postal."""
    result = await data_lookup.get_city_from_postal_code(code_postal)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucune ville trouvée pour le code postal: {code_postal}",
        )
    return AdresseResponse(**result)


@public_router.get(
    "/produit/barcode/{barcode}",
    response_model=ProduitResponse,
    summary="Produit par code-barres",
    description="Recherche un produit par son code-barres (EAN/UPC)",
)
async def lookup_product_by_barcode(barcode: str) -> ProduitResponse:
    """Rechercher un produit par code-barres."""
    result = await data_lookup.lookup_product_barcode(barcode)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Produit non trouvé pour le code-barres: {barcode}",
        )
    return ProduitResponse(**result)


@public_router.get(
    "/produit/search",
    summary="Rechercher des produits",
    description="Recherche des produits par nom",
)
async def search_products(
    q: str = Query(..., min_length=2, description="Nom du produit"),
    limit: int = Query(default=10, ge=1, le=50, description="Nombre de résultats"),
) -> list[ProduitResponse]:
    """Rechercher des produits par nom."""
    results = await data_lookup.search_products(q, limit)
    return [ProduitResponse(**r) for r in results]


@public_router.get(
    "/tva/validate/{vat_number}",
    response_model=TVAValidationResponse,
    summary="Valider TVA européenne",
    description="Valide un numéro de TVA intracommunautaire via VIES",
)
async def validate_vat(vat_number: str) -> TVAValidationResponse:
    """Valider un numéro de TVA européen."""
    result = await data_lookup.validate_vat_number(vat_number)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Numéro de TVA invalide",
        )
    return TVAValidationResponse(**result)


@public_router.get(
    "/iban/validate/{iban}",
    response_model=IBANValidationResponse,
    summary="Valider IBAN",
    description="Valide un numéro IBAN et extrait les informations",
)
async def validate_iban(iban: str) -> IBANValidationResponse:
    """Valider un IBAN."""
    result = data_lookup.validate_iban(iban)
    return IBANValidationResponse(**result)


@public_router.get(
    "/bic/{bic}",
    response_model=BICResponse,
    summary="Infos BIC/SWIFT",
    description="Extrait les informations d'un code BIC/SWIFT",
)
async def get_bic_info(bic: str) -> BICResponse:
    """Obtenir les infos d'un code BIC."""
    result = data_lookup.get_bank_from_bic(bic)
    return BICResponse(**result)


@public_router.post(
    "/smart-lookup",
    response_model=SmartLookupResponse,
    summary="Lookup intelligent",
    description="Détecte automatiquement le type de données et recherche dans les APIs appropriées",
)
async def smart_lookup(request: SmartLookupRequest) -> SmartLookupResponse:
    """
    Lookup intelligent multi-sources.

    Détecte automatiquement le type de données (SIRET, SIREN, IBAN, code-barres, etc.)
    et recherche dans l'API appropriée.
    """
    result = await data_lookup.smart_lookup(request.valeur, request.type_champ)
    if result:
        return SmartLookupResponse(
            type=result["type"],
            source=result["source"],
            data=result["data"],
            found=True,
        )
    return SmartLookupResponse(found=False)


# -----------------------------------------------------------------------------
# Endpoint Recherche Générique de Relations (pour TOUS les modules)
# -----------------------------------------------------------------------------
class RelationSearchResult(BaseModel):
    """Un résultat de recherche de relation."""
    id: str
    display: str
    module: str
    extra: Optional[dict] = None


class RelationSearchResponse(BaseModel):
    """Réponse de recherche de relations."""
    resultats: list[RelationSearchResult]
    total: int
    module: str
    champs_recherches: list[str]


# Configuration par défaut des champs de recherche par module
# Cette config peut être surchargée par config/autocompletion.yml
DEFAULT_RELATION_SEARCH_FIELDS = {
    "clients": ["nom", "email", "telephone", "siret", "code"],
    "fournisseurs": ["nom", "raison_sociale", "email", "siret", "code"],
    "produits": ["nom", "reference", "code_barres", "code", "designation"],
    "employes": ["nom", "prenom", "email", "matricule"],
    "contacts": ["nom", "prenom", "email", "telephone"],
    "projets": ["nom", "code", "reference", "titre"],
    "interventions": ["reference", "objet", "numero"],
    "factures": ["numero", "reference"],
    "devis": ["numero", "reference"],
    "commandes": ["numero", "reference"],
    "bons_commande": ["numero", "reference"],
    "bons_livraison": ["numero", "reference"],
    "utilisateurs": ["nom", "prenom", "email", "login"],
    "donneur_ordre": ["nom", "raison_sociale", "email", "siret"],
    "articles": ["nom", "reference", "code", "designation"],
    "prestations": ["nom", "code", "reference"],
    "equipements": ["nom", "code", "numero_serie"],
    "vehicules": ["immatriculation", "marque", "modele"],
    "locaux": ["nom", "adresse", "reference"],
    "immeubles": ["nom", "adresse", "reference"],
    "lots": ["numero", "reference", "designation"],
    "contrats": ["numero", "reference", "objet"],
    "affaires": ["nom", "code", "reference"],
}

# Champs d'affichage par défaut
DEFAULT_DISPLAY_FIELDS = {
    "clients": ["nom", "email"],
    "fournisseurs": ["nom", "email"],
    "produits": ["nom", "reference"],
    "employes": ["prenom", "nom"],
    "contacts": ["prenom", "nom", "email"],
    "utilisateurs": ["prenom", "nom"],
    "factures": ["numero", "client_nom"],
    "devis": ["numero", "client_nom"],
}


def _get_display_value(record: dict, module_name: str) -> str:
    """Génère la valeur d'affichage pour un enregistrement."""
    module_lower = module_name.lower()
    display_fields = DEFAULT_DISPLAY_FIELDS.get(module_lower, ["nom", "name", "reference", "code", "titre"])

    parts = []
    for field in display_fields:
        if field in record and record[field]:
            parts.append(str(record[field]))

    if parts:
        return " - ".join(parts)

    # Fallback: premier champ non-système non-vide
    for key, value in record.items():
        if key not in ["id", "tenant_id", "created_at", "updated_at", "deleted_at", "archived"] and value:
            return str(value)

    return str(record.get("id", ""))[:8]


@router.get(
    "/relation-search",
    response_model=RelationSearchResponse,
    summary="Recherche générique dans les relations",
    description="Recherche dans n'importe quel module pour les champs de type relation",
)
async def search_relation(
    module: str = Query(..., description="Nom du module (ex: Clients, Produits, Fournisseurs)"),
    q: str = Query(..., min_length=2, description="Terme de recherche"),
    limit: int = Query(default=10, ge=1, le=50, description="Nombre de résultats"),
    fields: Optional[str] = Query(default=None, description="Champs à rechercher (séparés par des virgules)"),
    user: dict = Depends(require_auth) if require_auth else None,
    tenant_id: UUID = Depends(get_current_tenant) if get_current_tenant else None,
) -> RelationSearchResponse:
    """
    Recherche générique dans n'importe quel module.

    Permet de faire de l'autocomplétion sur les champs de type relation
    sans avoir besoin d'un endpoint dédié par module.

    Exemples:
    - /relation-search?module=Clients&q=dupont
    - /relation-search?module=Produits&q=vis&fields=nom,reference
    - /relation-search?module=Employes&q=jean&limit=5
    """
    if not Database:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de données non disponible",
        )

    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
        )

    # Normaliser le nom du module
    module_lower = module.lower().replace("-", "_")

    # Tenter de trouver la définition du module via ModuleParser
    try:
        from moteur.parser import ModuleParser
        module_def = ModuleParser.get(module)
        if module_def:
            table_name = module_def.table_name or module_lower
        else:
            table_name = module_lower
    except ImportError:
        table_name = module_lower

    # Déterminer les champs de recherche
    if fields:
        search_fields = [f.strip() for f in fields.split(",")]
    else:
        search_fields = DEFAULT_RELATION_SEARCH_FIELDS.get(
            module_lower,
            ["nom", "name", "code", "reference", "email", "titre"]
        )

    # Exécuter la recherche
    try:
        results = Database.search(
            table_name=table_name,
            tenant_id=tenant_id,
            query=q,
            fields=search_fields,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur de recherche: {str(e)}",
        )

    # Formater les résultats
    formatted_results = []
    for record in results:
        # Extraire les champs utiles pour extra
        extra = {}
        for key in ["email", "telephone", "siret", "code", "reference", "adresse", "ville"]:
            if key in record and record[key]:
                extra[key] = record[key]

        formatted_results.append(RelationSearchResult(
            id=str(record.get("id", "")),
            display=_get_display_value(record, module),
            module=module,
            extra=extra if extra else None,
        ))

    return RelationSearchResponse(
        resultats=formatted_results,
        total=len(formatted_results),
        module=module,
        champs_recherches=search_fields,
    )


@router.get(
    "/relation-modules",
    summary="Liste des modules disponibles pour la recherche",
    description="Retourne la liste des modules avec leurs champs de recherche configurés",
)
async def list_relation_modules() -> dict:
    """
    Liste les modules disponibles pour la recherche de relations.

    Utile pour savoir quels modules peuvent être recherchés et
    quels champs sont utilisés par défaut.
    """
    try:
        from moteur.parser import ModuleParser
        available_modules = ModuleParser.all()
    except ImportError:
        available_modules = list(DEFAULT_RELATION_SEARCH_FIELDS.keys())

    modules_info = {}
    for module_name in available_modules:
        module_lower = module_name.lower()
        modules_info[module_name] = {
            "search_fields": DEFAULT_RELATION_SEARCH_FIELDS.get(
                module_lower,
                ["nom", "name", "code", "reference"]
            ),
            "display_fields": DEFAULT_DISPLAY_FIELDS.get(module_lower, ["nom"]),
        }

    return {
        "modules": modules_info,
        "total": len(modules_info),
    }
