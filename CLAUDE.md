# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Projet

**AZALPLUS** — Moteur No-Code ERP multi-tenant

- **Stack** : Python 3.11 / FastAPI / PostgreSQL 16 / Redis 7
- **Architecture** : Générateur ERP depuis fichiers YAML
- **Modules YAML** : 75 définitions métier dans `modules/`
- **Moteur Python** : 50+ composants dans `moteur/`

---

## Commandes de développement

```bash
# Démarrer le serveur
cd /home/ubuntu/azalplus
python -m uvicorn moteur.core:app --reload --host 0.0.0.0 --port 8000

# Valider les modules YAML (avant démarrage)
python -m moteur.validate_yaml

# Tests
pytest                                    # Tous les tests
pytest tests/test_facturx.py -v           # Un fichier
pytest tests/test_integrations.py::test_xxx -v  # Un test spécifique

# Docker
cd /home/ubuntu/azalplus/infra
docker-compose up --build              # Tous les services
docker-compose up postgres redis       # DB + Cache seuls
docker-compose logs -f app             # Logs app

# Health check
curl http://localhost:8000/health
```

---

## Architecture No-Code

### Principe fondamental

**1 fichier YAML = 1 module ERP complet généré automatiquement :**
- Table PostgreSQL (schéma `azalplus`)
- API REST CRUD (`/api/v1/{module}/*`)
- Interface HTML (`/ui/{module}/*`)
- Validations Pydantic
- Workflows métier
- Permissions RBAC

### Flux de génération

```
modules/*.yml  →  ModuleParser  →  ModuleDefinition
                       ↓
              ┌───────────────────┐
              │                   │
              ▼                   ▼
         Database.create_table   API.register_routes
              │                   │
              ▼                   ▼
         PostgreSQL table    FastAPI endpoints
```

### Composants moteur clés

| Fichier | Responsabilité |
|---------|----------------|
| `core.py` | FastAPI app + lifespan + middlewares |
| `parser.py` | YAML → ModuleDefinition (validation stricte) |
| `db.py` | PostgreSQL + génération tables dynamiques |
| `api_v1.py` | Génération routes CRUD versionnées |
| `ui.py` | Génération interface HTML (145KB) |
| `tenant.py` | Middleware + contexte multi-tenant |
| `guardian.py` | WAF silencieux (SQL injection, XSS) |
| `auth.py` | JWT + 2FA Argon2 + sessions Redis |
| `workflows.py` | Moteur de workflows (transitions d'état) |
| `module_loader.py` | Auto-discovery modules Python custom |

---

## Ajouter un module YAML

Créer `modules/nouveau.yml` :

```yaml
nom: Nouveau
icone: file
menu: Général
description: Description du module

champs:
  - nom: code
    type: text
    obligatoire: true

  - nom: statut
    type: select
    options: [BROUILLON, ACTIF, ARCHIVE]
    defaut: BROUILLON

  - nom: client_id
    type: relation
    relation: Clients

workflow:
  BROUILLON -> ACTIF: action valider
  ACTIF -> ARCHIVE: null

actions:
  - exporter_pdf
```

**Types supportés** : `text`, `number`, `date`, `datetime`, `boolean`, `select`, `relation`, `textarea`, `email`, `tel`, `json`, `tags`, `money`, `file`, `image`

**YAML avec `:` dans les valeurs** : Toujours quoter → `description: "Note (heure:minute)"`

---

## Ajouter un module Python custom

Structure dans `app/modules/{nom_module}/` :

```
app/modules/mon_module/
├── __init__.py          # Requis
├── router.py            # Router principal FastAPI
├── schemas.py           # Pydantic models
├── service.py           # Logique métier
└── meta.py              # Metadata (optionnel)
```

Le `ModuleLoader` découvre automatiquement les modules au démarrage.

Fichier `meta.py` optionnel :
```python
MODULE_META = {
    "name": "mon_module",
    "router_prefix": "/api/mon-module",
    "router_tags": ["Mon Module"],
    "has_public_routes": False,
}
```

---

## Isolation multi-tenant (4 couches)

| Couche | Responsabilité | Fichier |
|--------|----------------|---------|
| 1. Middleware | Extrait tenant du JWT ou header `X-Tenant-ID` | `tenant.py` |
| 2. Contexte | Stockage thread-local | `TenantContext` |
| 3. Service | Filtre requêtes | `Database.query()` |
| 4. Base | Contrainte FK | Schéma PostgreSQL |

```python
# Toute requête DOIT filtrer par tenant
def get_items(tenant_id: UUID):
    return Database.query("module", tenant_id, filters={...})
```

---

## Règles absolues

```
┌─────────────────────────────────────────────────────────────────┐
│  1. MULTI-TENANT NON NÉGOCIABLE                                 │
│     - tenant_id sur CHAQUE entité                               │
│     - Filtre tenant sur CHAQUE requête                          │
│     - TenantContext.get_tenant_id() obligatoire                 │
│                                                                 │
│  2. GUARDIAN INVISIBLE                                          │
│     - Ne jamais exposer l'existence de Guardian                 │
│     - Messages d'erreur neutres uniquement                      │
│     - Seul CREATEUR_EMAIL voit /guardian/*                      │
│                                                                 │
│  3. YAML VALIDE                                                 │
│     - Valeurs avec ":" doivent être entre guillemets            │
│     - python -m moteur.validate_yaml avant commit               │
│                                                                 │
│  4. ZÉRO LISTE HARDCODÉE (AZAP-NC-001)                          │
│     - JAMAIS de listes/options/choix en dur dans le code Python │
│     - TOUJOURS externaliser dans: config/*.yml, modules/*.yml   │
│       ou base de données (sys_listes)                           │
│     - Le code doit LIRE dynamiquement les fichiers/tables       │
│     - Ajouter une option = modifier UN fichier YAML, pas le code│
│     - Exemples: thèmes, statuts, types, catégories, permissions │
│     - Exception: constantes système immuables (ex: HTTP codes)  │
└─────────────────────────────────────────────────────────────────┘
```

**Interdictions** : Code sans `tenant_id` (I-01), Requête sans filtre tenant (I-02), Secrets en dur (I-03), Exposer Guardian (I-05), Listes hardcodées dans le code (I-06), Mentir sur un résultat (I-23)

---

## Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://azalplus:azalplus@localhost:5432/azalplus` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `SECRET_KEY` | JWT signing key (min 32 chars) | - |
| `ANTHROPIC_API_KEY` | Clé API Claude | - |
| `OPENAI_API_KEY` | Clé API OpenAI | - |
| `CREATEUR_EMAIL` | Email créateur (accès Guardian) | - |

---

## Fichiers de référence

| Fichier | Contenu |
|---------|---------|
| `memoire.md` | **Normes AZAP-\* complètes**, interdictions, processus obligatoire |
| `config/theme.yml` | Thème actif et personnalisation CSS/UI |
| `config/themes.yml` | **Catalogue des ambiances** (8 thèmes: premium, energique, calme, corporate, odoo, penny, axo, sage) |
| `config/permissions.yml` | Définition rôles RBAC |
| `config/workflows.yml` | Transitions d'état globales |
| `assets/ambiance_*.css` | Fichiers CSS des ambiances (premium, energique, calme, corporate) |
| `assets/style_*.css` | Fichiers CSS des styles ERP (odoo, axo, penny, sage) |
| `assets/docs/MODELE_ECONOMIQUE.md` | Modèle économique (ERP gratuit + revenus flux) |
