# AZALPLUS - Documentation de Référence

## Variables d'Environnement (.env)

| Variable | Description | Défaut |
|----------|-------------|--------|
| `AZALPLUS_ENV` | Environnement (development/production) | development |
| `DATABASE_URL` | URL de connexion PostgreSQL | postgresql://azalplus:azalplus@localhost:5432/azalplus |
| `REDIS_URL` | URL de connexion Redis | redis://localhost:6379/0 |
| `SECRET_KEY` | Clé secrète JWT (min 32 caractères) | - |
| `RATE_LIMIT_AUTHENTICATED` | Requêtes/min pour utilisateurs authentifiés | 100 |
| `RATE_LIMIT_UNAUTHENTICATED` | Requêtes/min pour non authentifiés | 20 |
| `RATE_LIMIT_PER_MINUTE` | Limite globale par minute | 60 |
| `SMTP_HOST` | Serveur SMTP | - |
| `SMTP_PORT` | Port SMTP | 587 |
| `SMTP_USER` | Utilisateur SMTP | - |
| `SMTP_PASSWORD` | Mot de passe SMTP | - |
| `OPENAI_API_KEY` | Clé API OpenAI | - |
| `ANTHROPIC_API_KEY` | Clé API Anthropic | - |
| `UPLOAD_DIR` | Répertoire d'upload | /app/data/uploads |
| `MAX_UPLOAD_SIZE_MB` | Taille max upload (Mo) | 50 |

---

## Pages Web (Routes UI)

### Pages Principales

| URL | Description |
|-----|-------------|
| `/login` | Page de connexion |
| `/ui/` | Dashboard principal |
| `/ui/calendrier` | Calendrier des interventions |
| `/ui/favoris` | Liste des favoris |

### Pages Modules (dynamiques)

| URL Pattern | Description |
|-------------|-------------|
| `/ui/{module}` | Liste des enregistrements |
| `/ui/{module}/nouveau` | Formulaire de création |
| `/ui/{module}/{id}` | Détail d'un enregistrement |
| `/ui/{module}/{id}/edit` | Formulaire de modification |

### Modules Disponibles

| Module | Menu | Description |
|--------|------|-------------|
| `clients` | Commercial | Gestion des clients |
| `fournisseurs` | Achats | Gestion des fournisseurs |
| `produits` | Inventaire | Catalogue produits |
| `devis` | Commercial | Devis clients |
| `factures` | Commercial | Factures clients |
| `avoirs` | Commercial | Avoirs/remboursements |
| `interventions` | Interventions | Planification interventions |
| `projets` | Projets | Gestion de projets |
| `taches` | Projets | Tâches de projet |
| `contrats` | Commercial | Contrats clients |
| `commandes_achat` | Achats | Commandes fournisseurs |
| `stock` | Inventaire | Niveaux de stock |
| `mouvements_stock` | Inventaire | Mouvements de stock |
| `employes` | RH | Gestion des employés |
| `conges` | RH | Demandes de congés |
| `temps` | RH | Suivi du temps |
| `notes_frais` | Comptabilité | Notes de frais |
| `comptabilite` | Comptabilité | Écritures comptables |
| `paiements` | Comptabilité | Suivi des paiements |
| `taxes` | Paramètres | Configuration TVA |
| `devises` | Paramètres | Devises et taux |
| `comptesbancaires` | Comptabilité | Comptes bancaires |
| `workflows` | Système | Automatisations |
| `modeles_email` | Paramètres | Templates d'emails |
| `sequences` | Système | Numérotation |
| `webhooks` | Système | Webhooks |

---

## API Endpoints

### Authentification

| Méthode | URL | Description |
|---------|-----|-------------|
| POST | `/api/auth/login` | Connexion |
| POST | `/api/auth/logout` | Déconnexion |
| POST | `/api/auth/refresh` | Rafraîchir token |
| GET | `/api/auth/me` | Utilisateur courant |

### CRUD Générique (par module)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/{module}` | Liste (avec pagination) |
| GET | `/api/{module}/{id}` | Détail |
| POST | `/api/{module}` | Créer |
| PUT | `/api/{module}/{id}` | Modifier |
| DELETE | `/api/{module}/{id}` | Supprimer |
| PATCH | `/api/{module}/bulk` | Modification en masse |
| DELETE | `/api/{module}/bulk` | Suppression en masse |

### API v1 (documentée)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/` | Info API |
| GET | `/api/v1/modules` | Liste des modules |
| GET | `/api/v1/{module}` | Liste paginée |
| GET | `/api/v1/{module}/{id}` | Détail |
| POST | `/api/v1/{module}` | Créer |
| PUT | `/api/v1/{module}/{id}` | Modifier |
| DELETE | `/api/v1/{module}/{id}` | Supprimer |

### Endpoints Spéciaux

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/health` | Health check |
| GET | `/api/docs` | Swagger UI |
| GET | `/api/redoc` | ReDoc |
| GET | `/api/documentation` | Documentation API |
| GET | `/static/style.css` | CSS généré depuis theme.yml |
| POST | `/api/storage/upload` | Upload fichier |
| GET | `/api/storage/{id}` | Télécharger fichier |

---

## Structure des Fichiers YAML (Modules)

```yaml
# modules/{nom_module}.yml
nom: NomDuModule
icone: icon-name
menu: NomDuMenu
description: Description du module

champs:
  - nom: nom_du_champ
    type: text|number|date|datetime|boolean|select|relation|textarea|email
    obligatoire: true|false
    defaut: valeur_par_defaut
    description: Description du champ
    relation: NomModuleLie  # Pour type: relation
    options: [OPT1, OPT2]   # Pour type: select

actions:
  - action1
  - action2

workflow:
  "ETAT1 -> ETAT2": "action demarrer"
```

---

## Types de Champs Supportés

| Type | Description | HTML généré |
|------|-------------|-------------|
| `text` | Texte court | `<input type="text">` |
| `textarea` | Texte long | `<textarea>` |
| `number` | Nombre | `<input type="number">` |
| `date` | Date | `<input type="date">` |
| `datetime` | Date et heure | `<input type="datetime-local">` |
| `boolean` | Oui/Non | `<input type="checkbox">` |
| `select` | Liste déroulante | `<select>` |
| `relation` | Lien vers autre module | `<select>` + bouton "+" |
| `email` | Email | `<input type="email">` |
| `json` | Données JSON | `<textarea>` |

---

## Commandes Utiles

```bash
# Démarrer le serveur
python3 -m uvicorn moteur.core:app --host 0.0.0.0 --port 8000

# Valider les fichiers YAML
python3 -m moteur.validate_yaml

# Voir les logs
tail -f /tmp/server.log
```

---

## Fichiers de Configuration

| Fichier | Description |
|---------|-------------|
| `.env` | Variables d'environnement |
| `config/theme.yml` | Thème CSS (couleurs, fonts) |
| `config/i18n/*.yml` | Traductions |
| `modules/*.yml` | Définitions des modules |

---

*Généré automatiquement - AZALPLUS v1.0.0*
