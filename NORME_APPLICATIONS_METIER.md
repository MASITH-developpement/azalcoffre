# NORME APPLICATIONS METIER AZALPLUS

## AZA-APP — Norme pour AZALBTP, AZALIMMO, AZALMED

**Version** : 1.0
**Date** : 2026-03-19
**Statut** : OBLIGATOIRE

---

## Principe Fondamental

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│   AZALPLUS = MOTEUR (gratuit, jamais dupliqué)                                  │
│                                                                                  │
│   AZALBTP, AZALIMMO, AZALMED = APPLICATIONS METIER (payantes)                   │
│                                                                                  │
│   → Chaque application IMPORTE le moteur AZALPLUS                               │
│   → Chaque application définit ses MODULES YAML spécifiques                     │
│   → Chaque application peut ajouter des SERVICES métier                         │
│   → JAMAIS de duplication du moteur                                             │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## AZA-APP-001 : Structure de répertoires obligatoire

Chaque application métier DOIT avoir cette structure exacte :

```
azal{app}/
│
├── modules/                    # OBLIGATOIRE — Modules YAML métier
│   └── *.yml
│
├── config/                     # OBLIGATOIRE — Configuration YAML
│   ├── app.yml                 # Configuration application
│   ├── theme.yml               # Thème (couleurs, logo)
│   ├── permissions.yml         # Rôles RBAC
│   ├── workflows.yml           # Workflows métier
│   └── *.yml                   # Autres configs spécifiques
│
├── templates/                  # OBLIGATOIRE — Templates Jinja2
│   ├── pdf/                    # Templates PDF
│   ├── emails/                 # Templates emails
│   └── ui/                     # Extensions UI (optionnel)
│
├── moteur/                     # OPTIONNEL — Code métier spécifique
│   ├── __init__.py             # Imports depuis AZALPLUS
│   ├── config.py               # Settings spécifiques (ports, chemins)
│   ├── services/               # Services métier
│   ├── integrations/           # APIs externes
│   └── tasks/                  # Tâches cron
│
├── assets/                     # OBLIGATOIRE — Fichiers statiques
│   ├── favicon.svg
│   ├── logo-azal{app}.svg
│   └── images/
│
├── tests/                      # OBLIGATOIRE — Tests
│   ├── __init__.py
│   ├── conftest.py
│   └── test_*.py
│
├── infra/                      # OPTIONNEL — Déploiement
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── nginx.conf
│
├── docs/                       # OPTIONNEL — Documentation
│
├── main.py                     # OBLIGATOIRE — Point d'entrée
├── requirements.txt            # OBLIGATOIRE — Dépendances
├── pyproject.toml              # OBLIGATOIRE — Configuration projet
├── CLAUDE.md                   # OBLIGATOIRE — Instructions Claude
├── NORMES.md                   # OBLIGATOIRE — Normes spécifiques
└── MODELE_ECONOMIQUE.md        # OBLIGATOIRE — Modèle économique
```

---

## AZA-APP-002 : Import obligatoire du moteur AZALPLUS

### Fichiers INTERDITS dans moteur/

| Fichier | Raison | Action |
|---------|--------|--------|
| `main.py` | Duplique le core | SUPPRIMER |
| `ui.py` | Duplique l'UI | SUPPRIMER |
| `auth.py` | Duplique l'auth | SUPPRIMER |
| `database.py` | Duplique la DB | SUPPRIMER |
| `models.py` | Duplique les modèles | SUPPRIMER ou ETENDRE |
| `schemas.py` | Duplique les schémas | SUPPRIMER ou ETENDRE |
| `parser.py` | Duplique le parser | SUPPRIMER |
| `tenant.py` | Duplique le tenant | SUPPRIMER |
| `guardian.py` | Duplique le WAF | SUPPRIMER |
| `api_v1.py` | Duplique l'API | SUPPRIMER |
| `workflows.py` | Duplique les workflows | SUPPRIMER |

### Fichiers AUTORISES dans moteur/

| Fichier | Raison |
|---------|--------|
| `__init__.py` | Imports depuis AZALPLUS |
| `config.py` | Settings spécifiques (port, chemins) |
| `services/*.py` | Logique métier spécifique |
| `integrations/*.py` | APIs externes spécifiques |
| `tasks/*.py` | Tâches cron spécifiques |

### Structure correcte moteur/__init__.py

```python
"""
AZAL{APP} — Import du moteur AZALPLUS
"""

import sys
sys.path.insert(0, "/home/ubuntu/azalplus")

# ═══════════════════════════════════════════════════════════════════════════════
# IMPORT MOTEUR AZALPLUS (JAMAIS DUPLIQUE)
# ═══════════════════════════════════════════════════════════════════════════════

# Core
from azalplus.moteur.core import app as azalplus_app
from azalplus.moteur.core import create_app

# Database
from azalplus.moteur.db import Database, get_session, Base

# Auth
from azalplus.moteur.auth import (
    get_current_user,
    create_access_token,
    verify_password,
    hash_password,
)

# Tenant
from azalplus.moteur.tenant import TenantContext, TenantMiddleware

# Parser
from azalplus.moteur.parser import ModuleParser, ModuleDefinition

# UI
from azalplus.moteur.ui import render_page, render_form, render_table

# API
from azalplus.moteur.api_v1 import create_crud_routes

# Workflows
from azalplus.moteur.workflows import WorkflowEngine

# ═══════════════════════════════════════════════════════════════════════════════
# SERVICES METIER SPECIFIQUES
# ═══════════════════════════════════════════════════════════════════════════════

from .services import *  # Services métier de l'application

# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Core AZALPLUS
    "create_app",
    "Database",
    "get_session",
    "get_current_user",
    "TenantContext",
    # Services métier
    # ... services spécifiques
]
```

---

## AZA-APP-003 : Point d'entrée main.py

Le fichier `main.py` DOIT être à la racine (pas dans moteur/) et DOIT utiliser le moteur AZALPLUS :

```python
#!/usr/bin/env python3
"""
AZAL{APP} — Point d'entrée
Charge le moteur AZALPLUS avec les modules {APP}
"""

import sys
import os

# Chemin vers AZALPLUS
AZALPLUS_PATH = os.getenv("AZALPLUS_PATH", "/home/ubuntu/azalplus")
sys.path.insert(0, AZALPLUS_PATH)

# Import du moteur AZALPLUS
from azalplus.moteur.core import create_app

# Configuration de l'application
APP_NAME = "azal{app}"
APP_PORT = {PORT}
MODULES_PATH = os.path.dirname(os.path.abspath(__file__)) + "/modules"
CONFIG_PATH = os.path.dirname(os.path.abspath(__file__)) + "/config"
TEMPLATES_PATH = os.path.dirname(os.path.abspath(__file__)) + "/templates"

# Création de l'application
app = create_app(
    app_name=APP_NAME,
    modules_path=MODULES_PATH,
    config_path=CONFIG_PATH,
    templates_path=TEMPLATES_PATH,
)

# Import des services métier spécifiques (après création app)
from moteur.services import register_routes
register_routes(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=APP_PORT,
        reload=True,
    )
```

---

## AZA-APP-004 : Ports assignés

| Application | Port | Variable |
|-------------|------|----------|
| AZALPLUS | 8000 | `AZALPLUS_PORT` |
| AZALCOFFRE | 8001 | `AZALCOFFRE_PORT` |
| AZALIMMO | 8002 | `AZALIMMO_PORT` |
| AZALBTP | 8003 | `AZALBTP_PORT` |
| AZALMED | 8004 | `AZALMED_PORT` |

---

## AZA-APP-005 : Configuration app.yml

Chaque application DOIT avoir un `config/app.yml` avec cette structure :

```yaml
# ═══════════════════════════════════════════════════════════════════════════════
# AZAL{APP} — Configuration
# ═══════════════════════════════════════════════════════════════════════════════

nom: AZAL{APP}
version: "1.0.0"
description: "Description de l'application"
port: {PORT}

# Chemin vers AZALPLUS (moteur)
azalplus_path: "/home/ubuntu/azalplus"

# Base de données (même PostgreSQL qu'AZALPLUS, schéma différent)
database:
  schema: "azal{app}"

# Redis (même instance qu'AZALPLUS, DB différente)
redis:
  db: {REDIS_DB}

# Modules AZALPLUS utilisés via relations
modules_azalplus:
  - clients
  - employes
  - factures
  # ... autres modules AZALPLUS utilisés

# Menu de l'application
menu:
  nom: AZAL{APP}
  icone: {ICONE}
  items:
    - nom: Dashboard
      icone: chart-line
      route: /dashboard
    # ... autres items
```

---

## AZA-APP-006 : Modules YAML — Extension AZALPLUS

Les modules peuvent étendre des modules AZALPLUS existants :

```yaml
# modules/chantiers.yml (AZALBTP)

module:
  name: chantiers
  extends: azalplus.projets          # ← EXTENSION
  label: "Chantiers BTP"
  description: "Gestion des chantiers"

# Champs HERITES de projets.yml (automatique)
# + Champs AJOUTES spécifiques BTP

additional_fields:
  - name: numero_marche
    type: string
    label: "Numéro de marché"

  - name: type_marche
    type: select
    options: [PUBLIC, PRIVE]

  - name: retenue_garantie_pct
    type: number
    default: 5

# Relations vers modules AZALPLUS
relations:
  - field: client_id
    target: azalplus.clients         # ← Module AZALPLUS
    required: true

  - field: chef_chantier_id
    target: azalplus.employes        # ← Module AZALPLUS
```

---

## AZA-APP-007 : Services métier

Les services métier DOIVENT :

1. Être dans `moteur/services/`
2. Avoir `tenant_id` dans le constructeur
3. Utiliser `TenantContext` pour les requêtes

```python
# moteur/services/situations.py

from uuid import UUID
from azalplus.moteur.db import Database
from azalplus.moteur.tenant import TenantContext


class SituationsService:
    """Service de gestion des situations de travaux."""

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id  # OBLIGATOIRE

    def _base_query(self):
        """Requête de base filtrée par tenant."""
        return Database.query(
            "situations_travaux",
            tenant_id=self.tenant_id,  # OBLIGATOIRE
        )

    async def calculer_cumul(self, chantier_id: UUID) -> dict:
        """Calcule le cumul des situations d'un chantier."""
        situations = self._base_query().filter(
            chantier_id=chantier_id
        ).all()
        # ... logique métier
```

---

## AZA-APP-008 : Intégrations externes

Les intégrations vers APIs externes DOIVENT :

1. Être dans `moteur/integrations/`
2. Ne pas dupliquer les intégrations AZALPLUS existantes
3. Gérer les erreurs proprement

```python
# moteur/integrations/boamp.py

import httpx
from typing import Optional


class BOAMPClient:
    """Client API BOAMP (marchés publics)."""

    BASE_URL = "https://boamp.fr/api/v1"

    async def search_marches(
        self,
        departements: list[str],
        mots_cles: list[str],
        date_min: Optional[str] = None,
    ) -> list[dict]:
        """Recherche des marchés publics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/marches",
                params={
                    "departements": ",".join(departements),
                    "q": " ".join(mots_cles),
                    "date_min": date_min,
                },
            )
            response.raise_for_status()
            return response.json()["results"]
```

---

## AZA-APP-009 : Tests obligatoires

Chaque application DOIT avoir :

1. `tests/conftest.py` avec fixtures tenant
2. Tests d'isolation tenant
3. Tests des services métier

```python
# tests/conftest.py

import pytest
from uuid import uuid4

@pytest.fixture
def tenant_id():
    """Fixture tenant pour les tests."""
    return uuid4()

@pytest.fixture
def other_tenant_id():
    """Autre tenant pour tests d'isolation."""
    return uuid4()
```

```python
# tests/test_tenant_isolation.py

import pytest

class TestTenantIsolation:
    """Tests d'isolation multi-tenant."""

    def test_cannot_access_other_tenant_data(
        self,
        tenant_id,
        other_tenant_id,
    ):
        """Un tenant ne peut pas voir les données d'un autre."""
        # Créer donnée tenant A
        # Essayer de lire depuis tenant B
        # Vérifier que c'est vide
        pass
```

---

## AZA-APP-010 : Variables d'environnement

Chaque application DOIT supporter ces variables :

| Variable | Description | Obligatoire |
|----------|-------------|-------------|
| `DATABASE_URL` | PostgreSQL | Oui |
| `REDIS_URL` | Redis | Oui |
| `SECRET_KEY` | JWT (min 32 chars) | Oui |
| `AZALPLUS_PATH` | Chemin moteur | Oui |
| `AZALCOFFRE_URL` | API AZALCOFFRE | Non |
| `{APP}_PORT` | Port application | Non (défaut config) |

---

## Résumé des normes

| Norme | Description |
|-------|-------------|
| AZA-APP-001 | Structure de répertoires obligatoire |
| AZA-APP-002 | Import obligatoire du moteur AZALPLUS |
| AZA-APP-003 | Point d'entrée main.py standardisé |
| AZA-APP-004 | Ports assignés par application |
| AZA-APP-005 | Configuration app.yml obligatoire |
| AZA-APP-006 | Extension modules AZALPLUS |
| AZA-APP-007 | Services métier avec tenant_id |
| AZA-APP-008 | Intégrations externes |
| AZA-APP-009 | Tests obligatoires |
| AZA-APP-010 | Variables d'environnement |

---

## Sanctions

Toute violation de ces normes entraîne :

1. **Rejet du code** lors de la review
2. **Refactoring obligatoire** avant merge
3. **Documentation de la violation** dans le rapport

---

## Historique

| Version | Date | Modification |
|---------|------|--------------|
| 1.0 | 2026-03-19 | Création initiale |
