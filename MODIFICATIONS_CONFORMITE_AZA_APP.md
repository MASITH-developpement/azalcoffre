# MODIFICATIONS CONFORMITE AZA-APP

## Plan de mise en conformité AZALBTP, AZALIMMO, AZALMED

**Date** : 2026-03-19
**Référence** : NORME_APPLICATIONS_METIER.md

---

## Audit actuel

### AZALBTP (Port 8003)

| Élément | État actuel | Conforme | Action |
|---------|-------------|----------|--------|
| `modules/*.yml` | 8 fichiers | ✅ | Garder |
| `config/*.yml` | 3 fichiers | ✅ | Garder |
| `templates/` | Structure OK | ✅ | Garder |
| `moteur/main.py` | 29 KB dupliqué | ❌ | SUPPRIMER |
| `moteur/ui.py` | 72 KB dupliqué | ❌ | SUPPRIMER |
| `moteur/models.py` | 20 KB dupliqué | ❌ | SUPPRIMER |
| `moteur/schemas.py` | 12 KB dupliqué | ❌ | SUPPRIMER |
| `moteur/auth.py` | 7 KB dupliqué | ❌ | SUPPRIMER |
| `moteur/database.py` | 3 KB dupliqué | ❌ | SUPPRIMER |
| `moteur/services/` | 2 fichiers | ✅ | Garder |
| `main.py` racine | Absent | ❌ | CREER |
| `moteur/__init__.py` | Imports incorrects | ❌ | REFAIRE |

### AZALIMMO (Port 8002)

| Élément | État actuel | Conforme | Action |
|---------|-------------|----------|--------|
| `modules/*.yml` | 20 fichiers | ✅ | Garder |
| `config/*.yml` | 8 fichiers | ✅ | Garder |
| `templates/` | emails + pdf | ✅ | Garder |
| `moteur/main.py` | 45 KB dupliqué | ❌ | SUPPRIMER |
| `moteur/database.py` | 10 KB dupliqué | ❌ | SUPPRIMER |
| `moteur/config.py` | 7 KB | ⚠️ | SIMPLIFIER |
| `moteur/services/` | Absent | ❌ | CREER |
| `main.py` racine | Absent | ❌ | CREER |
| `moteur/__init__.py` | Imports incorrects | ❌ | REFAIRE |

### AZALMED (Port 8004)

| Élément | État actuel | Conforme | Action |
|---------|-------------|----------|--------|
| `modules/*.yml` | 0 fichiers (vide) | ❌ | CREER |
| `config/*.yml` | 0 fichiers (vide) | ❌ | CREER |
| `templates/` | Vide | ❌ | CREER |
| `moteur/` | Vide | ⚠️ | CREER structure |
| `main.py` racine | Absent | ❌ | CREER |
| `tests/` | Vide | ❌ | CREER |

---

## AZALBTP — Modifications détaillées

### 1. Fichiers à SUPPRIMER

```bash
# Fichiers dupliqués du moteur AZALPLUS
rm /home/ubuntu/azalbtp/moteur/main.py          # 29 KB
rm /home/ubuntu/azalbtp/moteur/ui.py            # 72 KB
rm /home/ubuntu/azalbtp/moteur/models.py        # 20 KB
rm /home/ubuntu/azalbtp/moteur/schemas.py       # 12 KB
rm /home/ubuntu/azalbtp/moteur/auth.py          # 7 KB
rm /home/ubuntu/azalbtp/moteur/database.py      # 3 KB
rm -rf /home/ubuntu/azalbtp/moteur/__pycache__
rm -rf /home/ubuntu/azalbtp/moteur/api/         # Si dupliqué
```

### 2. Fichiers à CREER

#### `/home/ubuntu/azalbtp/main.py` (racine)

```python
#!/usr/bin/env python3
"""
AZALBTP — Point d'entrée
ERP BTP utilisant le moteur AZALPLUS
"""

import sys
import os

# Chemin vers AZALPLUS
AZALPLUS_PATH = os.getenv("AZALPLUS_PATH", "/home/ubuntu/azalplus")
sys.path.insert(0, AZALPLUS_PATH)

# Import du moteur AZALPLUS
from azalplus.moteur.core import create_app

# Configuration
APP_NAME = "azalbtp"
APP_PORT = int(os.getenv("AZALBTP_PORT", "8003"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Création de l'application
app = create_app(
    app_name=APP_NAME,
    modules_path=f"{BASE_DIR}/modules",
    config_path=f"{BASE_DIR}/config",
    templates_path=f"{BASE_DIR}/templates",
)

# Enregistrement des routes métier spécifiques
from moteur.services import register_btp_routes
register_btp_routes(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=APP_PORT, reload=True)
```

#### `/home/ubuntu/azalbtp/moteur/__init__.py`

```python
"""
AZALBTP — Moteur BTP
Import du moteur AZALPLUS + services BTP spécifiques
"""

import sys
sys.path.insert(0, "/home/ubuntu/azalplus")

# ═══════════════════════════════════════════════════════════════════════════════
# IMPORT MOTEUR AZALPLUS
# ═══════════════════════════════════════════════════════════════════════════════

from azalplus.moteur.core import create_app
from azalplus.moteur.db import Database, get_session
from azalplus.moteur.auth import get_current_user, create_access_token
from azalplus.moteur.tenant import TenantContext
from azalplus.moteur.parser import ModuleParser
from azalplus.moteur.ui import render_page

# ═══════════════════════════════════════════════════════════════════════════════
# SERVICES BTP SPECIFIQUES
# ═══════════════════════════════════════════════════════════════════════════════

from .services.appels_offres import AppelsOffresService
from .services.veille_marches import VeilleService

__all__ = [
    # AZALPLUS
    "create_app",
    "Database",
    "get_session",
    "get_current_user",
    "TenantContext",
    # BTP
    "AppelsOffresService",
    "VeilleService",
]
```

#### `/home/ubuntu/azalbtp/moteur/config.py` (simplifié)

```python
"""
AZALBTP — Configuration spécifique BTP
"""

import os
from pydantic_settings import BaseSettings


class AZALBTPSettings(BaseSettings):
    """Settings spécifiques AZALBTP."""

    # Chemins
    AZALPLUS_PATH: str = "/home/ubuntu/azalplus"
    AZALCOFFRE_URL: str = "http://localhost:8001"

    # Port
    AZALBTP_PORT: int = 8003

    # APIs externes BTP
    BOAMP_API_URL: str = "https://boamp.fr/api/v1"
    INSEE_API_URL: str = "https://api.insee.fr"
    METEO_API_URL: str = "https://api.open-meteo.com/v1"

    class Config:
        env_file = ".env"


settings = AZALBTPSettings()
```

#### `/home/ubuntu/azalbtp/moteur/services/__init__.py`

```python
"""
AZALBTP — Services métier BTP
"""

from fastapi import FastAPI

from .appels_offres import AppelsOffresService
from .veille_marches import VeilleService


def register_btp_routes(app: FastAPI):
    """Enregistre les routes spécifiques BTP."""
    from .routes import router as btp_router
    app.include_router(btp_router, prefix="/api/btp", tags=["BTP"])


__all__ = [
    "AppelsOffresService",
    "VeilleService",
    "register_btp_routes",
]
```

### 3. Fichiers à GARDER

```
modules/                    # 8 fichiers YAML ✅
├── appels_offres_btp.yml
├── chantiers.yml
├── devis_btp.yml
├── documents_btp.yml
├── materiel_btp.yml
├── pointages_chantier.yml
├── situations_travaux.yml
└── sous_traitants.yml

config/                     # 3 fichiers YAML ✅
├── app.yml
├── permissions.yml
└── theme.yml

templates/                  # Structure ✅
├── pdf/
└── emails/

moteur/services/            # Services métier ✅
├── appels_offres.py
└── veille_marches.py

tests/                      # Tests ✅
├── conftest.py
├── test_health.py
└── test_tenant_isolation.py
```

### 4. Structure finale AZALBTP

```
azalbtp/
├── main.py                          # NOUVEAU — Point d'entrée
├── CLAUDE.md                        ✅
├── NORMES.md                        ✅
├── MODELE_ECONOMIQUE.md             ✅
├── requirements.txt                 ✅
├── pyproject.toml                   ✅
│
├── modules/                         ✅ (8 fichiers)
├── config/                          ✅ (3 fichiers)
├── templates/                       ✅
├── assets/                          ✅
├── tests/                           ✅
├── infra/                           ✅
│
└── moteur/
    ├── __init__.py                  # REFAIT — Import AZALPLUS
    ├── config.py                    # SIMPLIFIE — Settings BTP
    │
    ├── services/                    ✅
    │   ├── __init__.py              # NOUVEAU
    │   ├── appels_offres.py         ✅
    │   ├── veille_marches.py        ✅
    │   ├── dc_generator.py          # A CREER
    │   ├── memoire_generator.py     # A CREER
    │   └── situations.py            # A CREER
    │
    ├── integrations/                # A CREER
    │   ├── boamp.py
    │   ├── joue.py
    │   └── azalcoffre.py
    │
    └── tasks/                       # A CREER
        └── veille_cron.py
```

---

## AZALIMMO — Modifications détaillées

### 1. Fichiers à SUPPRIMER

```bash
# Fichiers dupliqués du moteur AZALPLUS
rm /home/ubuntu/azalimmo/moteur/main.py         # 45 KB
rm /home/ubuntu/azalimmo/moteur/database.py     # 10 KB
rm -rf /home/ubuntu/azalimmo/moteur/__pycache__
```

### 2. Fichiers à CREER

#### `/home/ubuntu/azalimmo/main.py` (racine)

```python
#!/usr/bin/env python3
"""
AZALIMMO — Point d'entrée
ERP Immobilier utilisant le moteur AZALPLUS
"""

import sys
import os

# Chemin vers AZALPLUS
AZALPLUS_PATH = os.getenv("AZALPLUS_PATH", "/home/ubuntu/azalplus")
sys.path.insert(0, AZALPLUS_PATH)

# Import du moteur AZALPLUS
from azalplus.moteur.core import create_app

# Configuration
APP_NAME = "azalimmo"
APP_PORT = int(os.getenv("AZALIMMO_PORT", "8002"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Création de l'application
app = create_app(
    app_name=APP_NAME,
    modules_path=f"{BASE_DIR}/modules",
    config_path=f"{BASE_DIR}/config",
    templates_path=f"{BASE_DIR}/templates",
)

# Enregistrement des routes métier spécifiques
from moteur.services import register_immo_routes
register_immo_routes(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=APP_PORT, reload=True)
```

#### `/home/ubuntu/azalimmo/moteur/__init__.py`

```python
"""
AZALIMMO — Moteur Immobilier
Import du moteur AZALPLUS + services Immo spécifiques
"""

import sys
sys.path.insert(0, "/home/ubuntu/azalplus")

# ═══════════════════════════════════════════════════════════════════════════════
# IMPORT MOTEUR AZALPLUS
# ═══════════════════════════════════════════════════════════════════════════════

from azalplus.moteur.core import create_app
from azalplus.moteur.db import Database, get_session
from azalplus.moteur.auth import get_current_user, create_access_token
from azalplus.moteur.tenant import TenantContext
from azalplus.moteur.parser import ModuleParser
from azalplus.moteur.ui import render_page

# ═══════════════════════════════════════════════════════════════════════════════
# SERVICES IMMO SPECIFIQUES
# ═══════════════════════════════════════════════════════════════════════════════

from .services.quittances import QuittancesService
from .services.baux import BauxService
from .services.alertes import AlertesService

__all__ = [
    # AZALPLUS
    "create_app",
    "Database",
    "get_session",
    "get_current_user",
    "TenantContext",
    # IMMO
    "QuittancesService",
    "BauxService",
    "AlertesService",
]
```

#### `/home/ubuntu/azalimmo/moteur/config.py` (simplifié)

```python
"""
AZALIMMO — Configuration spécifique Immobilier
"""

import os
from pydantic_settings import BaseSettings


class AZALIMMOSettings(BaseSettings):
    """Settings spécifiques AZALIMMO."""

    # Chemins
    AZALPLUS_PATH: str = "/home/ubuntu/azalplus"
    AZALCOFFRE_URL: str = "http://localhost:8001"

    # Port
    AZALIMMO_PORT: int = 8002

    # APIs externes Immo
    DVFPLUS_API_URL: str = "https://api.dvfplus.fr"  # Données foncières
    BAN_API_URL: str = "https://api-adresse.data.gouv.fr"

    class Config:
        env_file = ".env"


settings = AZALIMMOSettings()
```

#### `/home/ubuntu/azalimmo/moteur/services/__init__.py`

```python
"""
AZALIMMO — Services métier Immobilier
"""

from fastapi import FastAPI


def register_immo_routes(app: FastAPI):
    """Enregistre les routes spécifiques Immo."""
    from .routes import router as immo_router
    app.include_router(immo_router, prefix="/api/immo", tags=["Immo"])


__all__ = [
    "register_immo_routes",
]
```

#### `/home/ubuntu/azalimmo/moteur/services/quittances.py`

```python
"""
Service de génération des quittances de loyer.
"""

from uuid import UUID
from datetime import date

import sys
sys.path.insert(0, "/home/ubuntu/azalplus")
from azalplus.moteur.db import Database
from azalplus.moteur.tenant import TenantContext


class QuittancesService:
    """Génération et gestion des quittances."""

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id

    def _base_query(self, module: str):
        return Database.query(module, tenant_id=self.tenant_id)

    async def generer_quittances_mensuelles(self, mois: date) -> list[dict]:
        """Génère les quittances pour tous les baux actifs."""
        baux_actifs = self._base_query("baux").filter(
            statut="ACTIF"
        ).all()

        quittances = []
        for bail in baux_actifs:
            quittance = await self._creer_quittance(bail, mois)
            quittances.append(quittance)

        return quittances

    async def _creer_quittance(self, bail: dict, mois: date) -> dict:
        """Crée une quittance pour un bail."""
        # Logique métier...
        pass
```

#### `/home/ubuntu/azalimmo/moteur/services/baux.py`

```python
"""
Service de gestion des baux.
"""

from uuid import UUID
from datetime import date, timedelta

import sys
sys.path.insert(0, "/home/ubuntu/azalplus")
from azalplus.moteur.db import Database


class BauxService:
    """Gestion des baux et renouvellements."""

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id

    def _base_query(self):
        return Database.query("baux", tenant_id=self.tenant_id)

    async def detecter_fins_bail(self, jours_avant: int = 90) -> list[dict]:
        """Détecte les baux arrivant à échéance."""
        date_limite = date.today() + timedelta(days=jours_avant)

        return self._base_query().filter(
            date_fin__lte=date_limite,
            statut="ACTIF",
        ).all()

    async def renouveler_bail(self, bail_id: UUID, duree_mois: int = 12) -> dict:
        """Renouvelle un bail."""
        # Logique métier...
        pass
```

#### `/home/ubuntu/azalimmo/moteur/services/alertes.py`

```python
"""
Service d'alertes immobilières.
"""

from uuid import UUID
from datetime import date, timedelta

import sys
sys.path.insert(0, "/home/ubuntu/azalplus")
from azalplus.moteur.db import Database


class AlertesService:
    """Gestion des alertes (loyers, DPE, assurances, etc.)."""

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id

    async def generer_alertes_quotidiennes(self) -> list[dict]:
        """Génère toutes les alertes du jour."""
        alertes = []

        # Loyers impayés
        alertes.extend(await self._alertes_loyers_impayes())

        # DPE expirés
        alertes.extend(await self._alertes_dpe())

        # Fins de bail
        alertes.extend(await self._alertes_fins_bail())

        # Assurances
        alertes.extend(await self._alertes_assurances())

        return alertes

    async def _alertes_loyers_impayes(self) -> list[dict]:
        """Loyers non payés à J+15."""
        # Logique métier...
        return []

    async def _alertes_dpe(self) -> list[dict]:
        """DPE expirant dans 90 jours."""
        # Logique métier...
        return []

    async def _alertes_fins_bail(self) -> list[dict]:
        """Baux finissant dans 90 jours."""
        # Logique métier...
        return []

    async def _alertes_assurances(self) -> list[dict]:
        """Assurances expirant dans 30 jours."""
        # Logique métier...
        return []
```

### 3. Structure finale AZALIMMO

```
azalimmo/
├── main.py                          # NOUVEAU — Point d'entrée
├── CLAUDE.md                        ✅
├── MODELE_ECONOMIQUE.md             ✅
├── requirements.txt                 ✅
├── pyproject.toml                   ✅
│
├── modules/                         ✅ (20 fichiers)
│   ├── biens.yml
│   ├── baux.yml
│   ├── locataires.yml
│   ├── proprietaires.yml
│   ├── quittances.yml
│   ├── mandats.yml
│   ├── diagnostics.yml
│   ├── etats_lieux.yml
│   ├── travaux.yml
│   ├── charges.yml
│   ├── assurances.yml
│   ├── sci.yml
│   ├── associes.yml
│   ├── assemblees.yml
│   ├── compteurs.yml
│   ├── contrats_entretien.yml
│   ├── estimations.yml
│   ├── transactions.yml
│   ├── visites.yml
│   └── groupes_immobiliers.yml
│
├── config/                          ✅ (8 fichiers)
│   ├── app.yml
│   ├── theme.yml
│   ├── permissions.yml
│   ├── workflows.yml
│   ├── alertes.yml
│   ├── types_biens.yml
│   ├── motifs_fin_bail.yml
│   └── subscriptions.yml
│
├── templates/                       ✅
│   ├── emails/
│   │   ├── base.html
│   │   ├── bienvenue.html
│   │   ├── quittance.html
│   │   ├── relance_loyer.html
│   │   ├── fin_bail.html
│   │   └── alerte_dpe.html
│   └── pdf/
│       ├── base.html
│       ├── quittance.html
│       ├── bail.html
│       ├── etat_lieux.html
│       └── avis_echeance.html
│
├── assets/                          ✅
├── tests/                           ✅
├── docs/                            ✅
├── infra/                           (vide)
│
└── moteur/
    ├── __init__.py                  # REFAIT — Import AZALPLUS
    ├── config.py                    # SIMPLIFIE — Settings Immo
    │
    ├── services/                    # NOUVEAU
    │   ├── __init__.py
    │   ├── quittances.py
    │   ├── baux.py
    │   ├── alertes.py
    │   ├── etats_lieux.py           # A CREER
    │   └── revision_loyers.py       # A CREER
    │
    ├── integrations/                # A CREER
    │   ├── dvfplus.py               # Données foncières
    │   ├── ban.py                   # Adresses
    │   └── azalcoffre.py            # Signatures
    │
    └── tasks/                       # A CREER
        ├── quittances_cron.py       # Génération mensuelle
        └── alertes_cron.py          # Alertes quotidiennes
```

---

## AZALMED — Initialisation complète

AZALMED est vide, il faut tout créer :

### 1. Fichiers à CREER

#### `/home/ubuntu/azalmed/main.py`

```python
#!/usr/bin/env python3
"""
AZALMED — Point d'entrée
Plateforme médicale utilisant le moteur AZALPLUS
"""

import sys
import os

# Chemin vers AZALPLUS
AZALPLUS_PATH = os.getenv("AZALPLUS_PATH", "/home/ubuntu/azalplus")
sys.path.insert(0, AZALPLUS_PATH)

# Import du moteur AZALPLUS
from azalplus.moteur.core import create_app

# Configuration
APP_NAME = "azalmed"
APP_PORT = int(os.getenv("AZALMED_PORT", "8004"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Création de l'application
app = create_app(
    app_name=APP_NAME,
    modules_path=f"{BASE_DIR}/modules",
    config_path=f"{BASE_DIR}/config",
    templates_path=f"{BASE_DIR}/templates",
)

# Enregistrement des routes métier spécifiques
from moteur.services import register_med_routes
register_med_routes(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=APP_PORT, reload=True)
```

#### `/home/ubuntu/azalmed/moteur/__init__.py`

```python
"""
AZALMED — Moteur Médical
Import du moteur AZALPLUS + services Médicaux spécifiques
"""

import sys
sys.path.insert(0, "/home/ubuntu/azalplus")

# ═══════════════════════════════════════════════════════════════════════════════
# IMPORT MOTEUR AZALPLUS
# ═══════════════════════════════════════════════════════════════════════════════

from azalplus.moteur.core import create_app
from azalplus.moteur.db import Database, get_session
from azalplus.moteur.auth import get_current_user, create_access_token
from azalplus.moteur.tenant import TenantContext
from azalplus.moteur.parser import ModuleParser
from azalplus.moteur.ui import render_page

# ═══════════════════════════════════════════════════════════════════════════════
# SERVICES MEDICAUX SPECIFIQUES
# ═══════════════════════════════════════════════════════════════════════════════

from .services.consultations import ConsultationsService
from .services.consentements import ConsentementsService
from .services.transcription import TranscriptionService

__all__ = [
    # AZALPLUS
    "create_app",
    "Database",
    "get_session",
    "get_current_user",
    "TenantContext",
    # MED
    "ConsultationsService",
    "ConsentementsService",
    "TranscriptionService",
]
```

#### `/home/ubuntu/azalmed/moteur/config.py`

```python
"""
AZALMED — Configuration spécifique Médical
"""

import os
from pydantic_settings import BaseSettings


class AZALMEDSettings(BaseSettings):
    """Settings spécifiques AZALMED."""

    # Chemins
    AZALPLUS_PATH: str = "/home/ubuntu/azalplus"
    AZALCOFFRE_URL: str = "http://localhost:8001"

    # Port
    AZALMED_PORT: int = 8004

    # APIs IA
    WHISPER_API_URL: str = ""  # Transcription
    ANTHROPIC_API_KEY: str = ""

    # HDS (Hébergeur Données Santé)
    HDS_ENABLED: bool = True

    class Config:
        env_file = ".env"


settings = AZALMEDSettings()
```

#### `/home/ubuntu/azalmed/moteur/services/__init__.py`

```python
"""
AZALMED — Services métier Médicaux
"""

from fastapi import FastAPI


def register_med_routes(app: FastAPI):
    """Enregistre les routes spécifiques Médicales."""
    from .routes import router as med_router
    app.include_router(med_router, prefix="/api/med", tags=["Medical"])


__all__ = [
    "register_med_routes",
]
```

#### `/home/ubuntu/azalmed/config/app.yml`

```yaml
# ═══════════════════════════════════════════════════════════════════════════════
# AZALMED — Configuration
# ═══════════════════════════════════════════════════════════════════════════════

nom: AZALMED
version: "1.0.0"
description: "Plateforme digitale pour professionnels de santé"
port: 8004

azalplus_path: "/home/ubuntu/azalplus"

database:
  schema: "azalmed"

redis:
  db: 4

# Modules AZALPLUS utilisés
modules_azalplus:
  - clients      # → Patients
  - employes     # → Praticiens
  - documents

# Conformité santé
compliance:
  hds: true                    # Hébergeur Données Santé
  rgpd: true
  retention_annees: 20         # Dossier médical

menu:
  nom: AZALMED
  icone: heartbeat
  items:
    - nom: Dashboard
      icone: chart-line
      route: /dashboard
    - nom: Patients
      icone: user-injured
      route: /patients
    - nom: Consultations
      icone: stethoscope
      route: /consultations
    - nom: Consentements
      icone: file-signature
      route: /consentements
    - nom: Documents
      icone: archive
      route: /documents
    - nom: Veille médicale
      icone: newspaper
      route: /veille
```

#### `/home/ubuntu/azalmed/config/theme.yml`

```yaml
# ═══════════════════════════════════════════════════════════════════════════════
# AZALMED — Thème
# ═══════════════════════════════════════════════════════════════════════════════

nom: azalmed
base: calme

couleurs:
  primaire: "#2E7D32"         # Vert médical
  secondaire: "#81C784"
  accent: "#4CAF50"

logo: /assets/logo-azalmed.svg
favicon: /assets/favicon.svg
```

#### `/home/ubuntu/azalmed/config/permissions.yml`

```yaml
# ═══════════════════════════════════════════════════════════════════════════════
# AZALMED — Permissions RBAC
# ═══════════════════════════════════════════════════════════════════════════════

roles:
  - nom: admin
    label: "Administrateur"
    permissions: ["*"]

  - nom: medecin
    label: "Médecin"
    permissions:
      - patients:*
      - consultations:*
      - consentements:*
      - documents:read
      - documents:create

  - nom: secretaire
    label: "Secrétaire médicale"
    permissions:
      - patients:read
      - patients:create
      - patients:update
      - consultations:read
      - consultations:create
      - documents:read
```

### 2. Modules YAML à créer

#### `/home/ubuntu/azalmed/modules/patients.yml`

```yaml
# ═══════════════════════════════════════════════════════════════════════════════
# AZALMED — Patients
# ═══════════════════════════════════════════════════════════════════════════════

module:
  name: patients
  extends: azalplus.clients
  label: "Patients"
  description: "Gestion des patients"
  icone: user-injured

additional_fields:
  - name: numero_secu
    type: string
    label: "N° Sécurité Sociale"
    pattern: "^[12][0-9]{14}$"

  - name: date_naissance
    type: date
    label: "Date de naissance"
    required: true

  - name: medecin_traitant
    type: string
    label: "Médecin traitant"

  - name: allergies
    type: tags
    label: "Allergies connues"

  - name: antecedents
    type: textarea
    label: "Antécédents médicaux"

  - name: groupe_sanguin
    type: select
    options: ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "Inconnu"]
```

#### `/home/ubuntu/azalmed/modules/consultations.yml`

```yaml
# ═══════════════════════════════════════════════════════════════════════════════
# AZALMED — Consultations
# ═══════════════════════════════════════════════════════════════════════════════

module:
  name: consultations
  label: "Consultations"
  description: "Gestion des consultations médicales"
  icone: stethoscope

champs:
  - name: patient_id
    type: relation
    relation: patients
    required: true

  - name: praticien_id
    type: relation
    relation: azalplus.employes
    required: true

  - name: date_heure
    type: datetime
    required: true

  - name: motif
    type: string
    label: "Motif de consultation"

  - name: observations
    type: textarea
    label: "Observations"

  - name: diagnostic
    type: textarea
    label: "Diagnostic"

  - name: prescription
    type: textarea
    label: "Prescription"

  - name: audio_transcription
    type: file
    label: "Enregistrement audio"

  - name: transcription_ia
    type: textarea
    label: "Transcription IA"
    readonly: true

  - name: statut
    type: select
    options: [PLANIFIEE, EN_COURS, TERMINEE, ANNULEE]
    default: PLANIFIEE

workflow:
  PLANIFIEE -> EN_COURS: action demarrer
  EN_COURS -> TERMINEE: action terminer
  PLANIFIEE -> ANNULEE: action annuler
```

#### `/home/ubuntu/azalmed/modules/consentements.yml`

```yaml
# ═══════════════════════════════════════════════════════════════════════════════
# AZALMED — Consentements
# ═══════════════════════════════════════════════════════════════════════════════

module:
  name: consentements
  label: "Consentements"
  description: "Consentements éclairés avec signature eIDAS"
  icone: file-signature

champs:
  - name: patient_id
    type: relation
    relation: patients
    required: true

  - name: type_consentement
    type: select
    options:
      - SOINS_GENERAUX
      - INTERVENTION_CHIRURGICALE
      - ANESTHESIE
      - TRAITEMENT_DONNEES
      - TELESANTE
      - RECHERCHE_CLINIQUE
    required: true

  - name: formulaire_id
    type: relation
    relation: formulaires_consent

  - name: date_signature
    type: datetime

  - name: signature_eidas
    type: json
    label: "Données signature AZALCOFFRE"

  - name: document_signe
    type: file
    label: "Document signé (PDF)"

  - name: statut
    type: select
    options: [BROUILLON, ENVOYE, SIGNE, REFUSE, EXPIRE]
    default: BROUILLON

  - name: validite_jours
    type: number
    default: 365
    label: "Validité (jours)"

workflow:
  BROUILLON -> ENVOYE: action envoyer
  ENVOYE -> SIGNE: action signer
  ENVOYE -> REFUSE: action refuser
  SIGNE -> EXPIRE: auto after validite_jours
```

### 3. Structure finale AZALMED

```
azalmed/
├── main.py                          # Point d'entrée
├── CLAUDE.md                        ✅
├── MODELE_ECONOMIQUE.md             ✅
├── requirements.txt                 # A CREER
├── pyproject.toml                   # A CREER
│
├── modules/
│   ├── patients.yml                 # extends azalplus.clients
│   ├── consultations.yml
│   ├── consentements.yml
│   ├── formulaires_consent.yml      # A CREER
│   ├── ordonnances.yml              # A CREER
│   ├── documents_medicaux.yml       # A CREER
│   └── veille_medicale.yml          # A CREER
│
├── config/
│   ├── app.yml
│   ├── theme.yml
│   ├── permissions.yml
│   └── workflows.yml                # A CREER
│
├── templates/
│   ├── emails/
│   │   ├── rappel_rdv.html          # A CREER
│   │   ├── consentement.html        # A CREER
│   │   └── ordonnance.html          # A CREER
│   └── pdf/
│       ├── ordonnance.html          # A CREER
│       ├── consentement.html        # A CREER
│       └── compte_rendu.html        # A CREER
│
├── assets/
│   ├── favicon.svg                  # A CREER
│   └── logo-azalmed.svg             # A CREER
│
├── tests/
│   ├── __init__.py                  # A CREER
│   ├── conftest.py                  # A CREER
│   └── test_health.py               # A CREER
│
├── infra/                           # A CREER
│
└── moteur/
    ├── __init__.py
    ├── config.py
    │
    ├── services/
    │   ├── __init__.py
    │   ├── consultations.py         # Gestion consultations
    │   ├── consentements.py         # Signature eIDAS
    │   └── transcription.py         # Whisper IA
    │
    ├── integrations/
    │   ├── whisper.py               # Transcription audio
    │   ├── claude.py                # Extraction structurée
    │   └── azalcoffre.py            # Signatures, archivage
    │
    └── tasks/
        ├── rappels_rdv.py           # Rappels automatiques
        └── veille_medicale.py       # Veille publications
```

---

## Résumé des actions

| Application | Fichiers à supprimer | Fichiers à créer | Effort |
|-------------|---------------------|------------------|--------|
| **AZALBTP** | 6 fichiers (143 KB) | 5 fichiers | Moyen |
| **AZALIMMO** | 2 fichiers (55 KB) | 8 fichiers | Moyen |
| **AZALMED** | 0 (vide) | 20+ fichiers | Important |

---

## Ordre d'exécution recommandé

1. **Phase 1** : AZALBTP (le plus avancé, sert de modèle)
2. **Phase 2** : AZALIMMO (20 modules YAML existants)
3. **Phase 3** : AZALMED (à initialiser complètement)

---

## Validation

Après chaque mise en conformité, vérifier :

```bash
# 1. Aucun fichier dupliqué
ls -la azal{app}/moteur/*.py  # Ne doit avoir que __init__.py et config.py

# 2. Import AZALPLUS fonctionne
cd azal{app} && python -c "from moteur import create_app; print('OK')"

# 3. Application démarre
python main.py  # Doit démarrer sans erreur

# 4. Tests passent
pytest tests/
```
