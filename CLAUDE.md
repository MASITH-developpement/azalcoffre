# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Projet

**AZALPLUS** — Moteur No-Code ERP multi-tenant (Python 3.11 / FastAPI / PostgreSQL 16 / Redis)

- **Version** : 1.0.0
- **Architecture** : Générateur ERP depuis fichiers YAML
- **Modules YAML** : 67 définitions métier
- **Moteur** : 52 composants Python (~37K lignes)

---

## Commandes de développement

```bash
# Démarrer le serveur (depuis /home/ubuntu/azalplus)
python -m uvicorn moteur.core:app --reload --host 0.0.0.0 --port 8000

# Valider les modules YAML
python -m moteur.validate_yaml

# Docker (environnement complet)
cd /home/ubuntu/azalplus/infra
docker-compose up --build              # Tous les services
docker-compose up postgres redis       # DB + Cache seuls

# Health check
curl http://localhost:8000/health
```

---

## Architecture

### Principe No-Code

**1 fichier YAML = 1 module ERP complet généré automatiquement :**
- Table PostgreSQL (schéma `azalplus`)
- API REST CRUD (`/api/{module}/*` et `/api/v1/{module}/*`)
- Interface HTML (`/ui/{module}/*`)
- Validations Pydantic
- Workflows métier
- Permissions RBAC
- Audit trail

### Structure projet

```
/home/ubuntu/azalplus/
├── moteur/                    # Cœur du générateur (52 modules)
│   ├── core.py                # FastAPI app + lifespan
│   ├── parser.py              # YAML → ModuleDefinition
│   ├── db.py                  # PostgreSQL + génération tables
│   ├── api.py                 # Génération routes CRUD (legacy)
│   ├── api_v1.py              # API v1 versionnée
│   ├── ui.py                  # Génération HTML (145KB)
│   ├── auth.py                # JWT + 2FA + Argon2
│   ├── tenant.py              # Isolation multi-tenant
│   ├── guardian.py            # WAF silencieux (SQL injection, XSS)
│   ├── workflows.py           # Moteur workflows
│   ├── rgpd.py                # Conformité RGPD
│   └── ...                    # 40+ autres composants
│
├── modules/                   # 67 définitions YAML
│   ├── clients.yml            # CRM
│   ├── factures.yml           # Facturation
│   ├── produits.yml           # Catalogue
│   ├── interventions.yml      # SAV
│   └── ...
│
├── config/                    # Configuration YAML
│   ├── theme.yml              # CSS/Design
│   ├── permissions.yml        # RBAC
│   ├── workflows.yml          # Transitions d'état
│   └── validations.yml        # Règles validation
│
├── app/modules/               # Modules Python custom
│   └── autocompletion_ia/     # IA multi-provider (OpenAI, Claude)
│
└── infra/                     # Docker + Nginx
    └── docker-compose.yml
```

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

---

## Règles absolues

```
┌─────────────────────────────────────────────────────────────────┐
│  1. MULTI-TENANT NON NÉGOCIABLE                                 │
│     - tenant_id sur CHAQUE entité                               │
│     - Filtre tenant sur CHAQUE requête                          │
│     - TenantContext.get_tenant_id() obligatoire                 │
│                                                                 │
│  2. YAML VALIDE                                                 │
│     - Valeurs avec ":" doivent être entre guillemets            │
│     - YAMLValidator.validate_file() avant chargement            │
│                                                                 │
│  3. GUARDIAN INVISIBLE                                          │
│     - Ne jamais exposer l'existence de Guardian                 │
│     - Messages d'erreur neutres uniquement                      │
│     - Seul CREATEUR_EMAIL voit le dashboard                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Format module YAML

```yaml
# modules/exemple.yml
nom: Exemple
icone: file
menu: Général
description: Description du module

champs:
  - nom: code
    type: text
    obligatoire: true
    autocompletion: true

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
  - envoyer_email
```

### Types de champs supportés

| Type | Alias | PostgreSQL |
|------|-------|------------|
| `text` | texte, string | VARCHAR(255) |
| `number` | nombre, entier | NUMERIC(15,2) |
| `date` | datetime | DATE/TIMESTAMP |
| `boolean` | booleen, oui/non | BOOLEAN |
| `select` | enum | VARCHAR |
| `relation` | lien | UUID (FK) |
| `textarea` | texte long | TEXT |
| `email` | - | VARCHAR(255) |
| `tel` | telephone | VARCHAR(20) |
| `json` | - | JSONB |
| `tags` | - | JSONB |
| `money` | montant | NUMERIC(15,2) |

---

## Isolation multi-tenant (4 couches)

1. **Middleware** (`tenant.py`) : Extrait tenant du JWT ou header `X-Tenant-ID`
2. **Contexte** (`TenantContext`) : Stockage thread-local du tenant_id
3. **Service** : `Database.query(module, tenant_id, ...)`
4. **Base** : Schéma PostgreSQL `azalplus` avec colonne `tenant_id`

```python
# Toute requête DOIT filtrer par tenant
def get_items(tenant_id: UUID):
    return Database.query("module", tenant_id, filters={...})
```

---

## API

### Endpoints générés automatiquement

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/v1/{module}` | Liste paginée |
| GET | `/api/v1/{module}/{id}` | Détail |
| POST | `/api/v1/{module}` | Création |
| PUT | `/api/v1/{module}/{id}` | Mise à jour |
| DELETE | `/api/v1/{module}/{id}` | Suppression |
| POST | `/api/v1/{module}/bulk` | Opérations en masse |
| GET | `/api/v1/{module}/export` | Export CSV/JSON |

### Routes publiques (sans auth)

- `/health` - Health check
- `/api/docs` - Swagger UI
- `/api/auth/login` - Authentification
- `/api/autocompletion-ia/entreprise` - Lookup SIRET (API gouv.fr)
- `/api/autocompletion-ia/adresse` - Autocomplétion adresse

---

## Sécurité

### Guardian (WAF invisible)

- Détection SQL injection, XSS
- Rate limiting (500 req/min auth, 100 req/min public)
- Blocage IP après 10 tentatives
- Dashboard : `/guardian/dashboard` (créateur uniquement)

### Authentification

- JWT (24h) + Refresh token (7j)
- Argon2 pour hachage mots de passe
- 2FA TOTP optionnel
- Sessions Redis

---

## Stack technique

| Couche | Technologies |
|--------|-------------|
| Framework | FastAPI, Pydantic 2.x |
| Database | PostgreSQL 16, SQLAlchemy 2.0 |
| Cache | Redis 7 |
| Auth | python-jose, argon2-cffi, pyotp |
| PDF | WeasyPrint, Jinja2 |
| IA | OpenAI, Anthropic Claude |
| Monitoring | structlog, prometheus-client |

---

## Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `DATABASE_URL` | PostgreSQL connection string | - |
| `REDIS_URL` | Redis connection string | redis://localhost:6379/0 |
| `SECRET_KEY` | JWT signing key (min 32 chars) | - |
| `ANTHROPIC_API_KEY` | Clé API Claude | - |
| `OPENAI_API_KEY` | Clé API OpenAI | - |
| `RATE_LIMIT_AUTHENTICATED` | Limite req/min (auth) | 500 |

---

## Composants moteur clés

| Fichier | Responsabilité |
|---------|----------------|
| `parser.py` | Parse YAML, valide, génère ModuleDefinition |
| `db.py` | Connexion PostgreSQL, génération tables dynamiques |
| `api.py` / `api_v1.py` | Génération routes CRUD |
| `ui.py` | Génération interface HTML |
| `tenant.py` | Middleware + contexte multi-tenant |
| `guardian.py` | Sécurité silencieuse (WAF) |
| `auth.py` | JWT, 2FA, gestion sessions |
| `workflows.py` | Moteur de workflows (transitions d'état) |
| `validation.py` | Validation avancée (SIRET, IBAN, TVA...) |
| `rgpd.py` | Conformité RGPD (export, suppression données) |

---

## Normes AZALPLUS (AZAP-*)

**Référence complète :** `memoire.md`

### Normes clés

| Norme | Règle |
|-------|-------|
| AZAP-NF-001 | Unicité du moteur — jamais dupliqué |
| AZAP-NF-002 | Modules YAML subordonnés au moteur |
| AZAP-TENANT-001 | Isolation tenant obligatoire sur toute requête |
| AZAP-SEC-001 | Guardian invisible — messages neutres uniquement |
| AZAP-NC-001 | Génération automatique tables PostgreSQL |
| AZAP-YAML-001 | Validation YAML stricte avant chargement |

### Interdictions absolues

| Code | Interdiction |
|------|--------------|
| I-01 | ❌ Code sans `tenant_id` |
| I-02 | ❌ Requête sans filtre tenant |
| I-03 | ❌ Secrets en dur |
| I-05 | ❌ Exposer l'existence de Guardian |
| I-06 | ❌ Modifier CREATEUR_EMAIL |
| I-23 | ❌ Mentir sur un résultat |

### Processus IA obligatoire

```
ANALYSIS → PLAN → EXECUTION → VERIFICATION
```

---

## Fichiers de référence

| Fichier | Quand le lire |
|---------|---------------|
| `memoire.md` | Normes AZAP-* complètes, interdictions, processus |
| `CLAUDE.md` | Commandes, architecture, quick start |
| `config/theme.yml` | Personnalisation CSS/UI |
| `config/permissions.yml` | Définition rôles RBAC |
