# Règles des Modules YAML - AZALPLUS

> **Document de référence pour la création et modification des modules YAML**
> Ces règles sont NON NÉGOCIABLES.
>
> **PHILOSOPHIE NO-CODE :**
> - Variables plutôt que valeurs en dur
> - Requêtes SQL dynamiques pour les calculs
> - Configuration centralisée dans config/constants.yml

---

## 1. Principes Fondamentaux

### 1.1 ZÉRO valeur en dur

```yaml
# ❌ INTERDIT - valeurs hardcodées
options: [PROSPECT, ACTIF, INACTIF]
defaut: PROSPECT
taux_tva: 20

# ✅ CORRECT - références aux constantes
options: $statuts.clients.valeurs
defaut: $statuts.clients.defaut
taux_tva: $tva.france.normal
```

### 1.2 ZÉRO calcul stocké

Les statistiques et agrégations ne sont **JAMAIS** stockées.
Elles sont calculées dynamiquement via des requêtes SQL.

```yaml
# ❌ INTERDIT - valeur stockée
- nom: ca_cumule
  type: money
  defaut: 0

# ✅ CORRECT - calcul dynamique SQL
- nom: ca_cumule
  type: money
  libelle: "CA cumulé total"
  calcule: true
  sql: |
    SELECT COALESCE(SUM(CAST(total AS NUMERIC)), 0)
    FROM azalplus.factures
    WHERE customer_id = {id}
    AND tenant_id = {tenant_id}
    AND status = 'PAID'
    AND deleted_at IS NULL
```

---

## 2. Syntaxe des Références

### 2.1 Format

Les références aux constantes utilisent le préfixe `$` suivi du chemin:

```
$chemin.vers.valeur
```

**IMPORTANT : SANS accolades** - la syntaxe `{$VARIABLE}` est INCORRECTE.

### 2.2 Références disponibles (config/constants.yml)

| Chemin | Description | Exemple |
|--------|-------------|---------|
| `$statuts.{module}.valeurs` | Liste des statuts d'un module | `$statuts.factures.valeurs` |
| `$statuts.{module}.defaut` | Statut par défaut | `$statuts.clients.defaut` |
| `$tva.france.normal` | Taux TVA normal France | `20.0` |
| `$tva.france.reduit` | Taux TVA réduit France | `5.5` |
| `$devises.EUR` | Configuration devise EUR | `{code, symbole, ...}` |
| `$devises.defaut` | Devise par défaut | `EUR` |
| `$conditions_paiement.valeurs` | Conditions de paiement | Liste objets |
| `$conditions_paiement.defaut` | Condition par défaut | `NET_30` |
| `$modes_paiement.valeurs` | Modes de paiement | Liste objets |
| `$modes_paiement.defaut` | Mode par défaut | `VIREMENT` |
| `$civilites` | Liste des civilités | `[{code, nom, abrev}]` |
| `$formes_juridiques` | Formes juridiques | Liste objets |
| `$clients.types.valeurs` | Types de clients | `[PROFESSIONNEL, PARTICULIER, ...]` |
| `$clients.segments.valeurs` | Segments clients | `[TPE, PME, ETI, ...]` |
| `$clients.origines.valeurs` | Origines clients | `[PROSPECTION, ...]` |
| `$clients.priorites.valeurs` | Priorités | `[BASSE, NORMALE, HAUTE, CRITIQUE]` |
| `$clients.satisfactions.valeurs` | Niveaux satisfaction | `[TRES_INSATISFAIT, ...]` |
| `$seuils.encours_alerte` | Seuil encours (0.9 = 90%) | `0.9` |
| `$seuils.inactivite_jours` | Jours avant client inactif | `180` |
| `$alertes.*` | Messages d'alerte | `$alertes.depassement_encours` |
| `$defauts.pays` | Pays par défaut | `FR` |
| `$defauts.devise` | Devise par défaut | `EUR` |
| `$comptabilite.compte_client_defaut` | Compte comptable client | `411000` |
| `$validations.types.siret` | Pattern validation SIRET | regex |
| `$validations.regles.pourcentage` | Règle 0-100 | règle |
| `$workflows.client` | Workflow clients | définition |

### 2.3 Variables dynamiques dans les requêtes SQL

| Variable | Description |
|----------|-------------|
| `{id}` | ID de l'enregistrement courant |
| `{tenant_id}` | ID du tenant (OBLIGATOIRE - isolation multi-tenant) |

---

## 3. Champs Calculés

### 3.1 Structure

```yaml
- nom: nom_du_champ
  type: money|number|date
  libelle: "Libellé affiché"
  calcule: true
  sql: |
    SELECT ...
    FROM azalplus.table
    WHERE foreign_key = {id}
    AND tenant_id = {tenant_id}
    AND deleted_at IS NULL
```

### 3.2 Règles SQL OBLIGATOIRES

1. **Toujours** filtrer par `tenant_id = {tenant_id}` (isolation multi-tenant)
2. **Toujours** exclure les soft-deleted : `AND deleted_at IS NULL`
3. Utiliser `COALESCE` pour éviter les NULL : `COALESCE(SUM(...), 0)`
4. Caster explicitement les types : `CAST(total AS NUMERIC)`

### 3.3 Exemples

```yaml
# CA cumulé
- nom: ca_cumule
  type: money
  libelle: "CA cumulé total"
  calcule: true
  sql: |
    SELECT COALESCE(SUM(CAST(total AS NUMERIC)), 0)
    FROM azalplus.factures
    WHERE customer_id = {id}
    AND tenant_id = {tenant_id}
    AND status = 'PAID'
    AND deleted_at IS NULL

# Nombre de factures
- nom: nombre_factures
  type: number
  libelle: "Nb factures"
  calcule: true
  sql: |
    SELECT COUNT(*)
    FROM azalplus.factures
    WHERE customer_id = {id}
    AND tenant_id = {tenant_id}
    AND status != 'CANCELLED'
    AND deleted_at IS NULL

# Délai de paiement moyen
- nom: delai_paiement_moyen
  type: number
  libelle: "Délai paiement moyen (j)"
  calcule: true
  sql: |
    SELECT COALESCE(AVG(EXTRACT(DAY FROM (paid_at - date))), 0)::INTEGER
    FROM azalplus.factures
    WHERE customer_id = {id}
    AND tenant_id = {tenant_id}
    AND status = 'PAID'
    AND paid_at IS NOT NULL
    AND deleted_at IS NULL
```

---

## 4. Validations

### 4.1 Référence aux patterns existants

```yaml
- nom: tax_id
  type: text
  libelle: "SIRET"
  validation: $validations.types.siret

- nom: credit_limit
  type: money
  validation: $validations.regles.montant_positif
```

### 4.2 Patterns disponibles (config/validations.yml)

| Chemin | Valide |
|--------|--------|
| `$validations.types.email` | Format email |
| `$validations.types.telephone` | Téléphone international |
| `$validations.types.telephone_fr` | Téléphone français |
| `$validations.types.code_postal_fr` | 5 chiffres |
| `$validations.types.siret` | 14 chiffres |
| `$validations.types.siren` | 9 chiffres |
| `$validations.types.tva_intra` | Format TVA UE |
| `$validations.types.iban` | Format IBAN |
| `$validations.types.bic` | Format BIC/SWIFT |
| `$validations.types.url` | Format URL |
| `$validations.types.code_naf` | Code APE/NAF |
| `$validations.regles.montant_positif` | >= 0 |
| `$validations.regles.pourcentage` | 0-100 |

---

## 5. Options Select

### 5.1 ❌ INTERDIT : Options en dur

```yaml
# ❌ INTERDIT
- nom: statut
  type: select
  options:
    - PROSPECT
    - ACTIF
    - INACTIF
```

### 5.2 ✅ OBLIGATOIRE : Références aux constantes

```yaml
# ✅ CORRECT
- nom: statut
  type: select
  options: $statuts.clients.valeurs
  defaut: $statuts.clients.defaut

- nom: type
  type: select
  options: $clients.types.valeurs
  defaut: $clients.types.defaut

- nom: payment_terms
  type: select
  options: $conditions_paiement.valeurs
  defaut: $conditions_paiement.defaut
```

---

## 6. Workflows

### 6.1 Référence externe (recommandé)

```yaml
# Référence au workflow défini dans config/workflows.yml
workflow: $workflows.client
```

### 6.2 Définition inline (si nécessaire)

Les workflows sont définis dans `config/workflows.yml`.
Ne pas définir de workflows directement dans les modules YAML.

---

## 7. Actions

### 7.1 Structure

```yaml
actions:
  - nom: identifiant_action
    libelle: "Texte du bouton"
    icone: lucide-icon-name
    statut_requis: STATUT           # Optionnel
    confirmation: true              # Demande confirmation
    ouvre: module_cible             # Optionnel - ouvre un autre module
    prefill:                        # Optionnel - pré-remplit
      champ: "{valeur}"
    export: pdf|csv                 # Optionnel - type export
    template: nom_template          # Optionnel - template PDF
```

### 7.2 Exemples

```yaml
actions:
  - nom: creer_devis
    libelle: "Créer un devis"
    icone: file-text
    ouvre: devis
    prefill:
      customer_id: "{id}"

  - nom: exporter_fiche
    libelle: "Exporter PDF"
    icone: download
    export: pdf
    template: fiche_client

  - nom: bloquer
    libelle: "Bloquer"
    icone: ban
    confirmation: true
```

---

## 8. Alertes IA (Marceau)

### 8.1 Structure

```yaml
marceau:
  alertes:
    - condition: expression_sql
      condition_sup: condition_additionnelle    # Optionnel
      message: $alertes.message_reference
      severite: info|warning|error
```

### 8.2 Exemple

```yaml
marceau:
  alertes:
    - condition: encours_actuel > credit_limit * $seuils.encours_alerte
      condition_sup: credit_limit > 0
      message: $alertes.depassement_encours
      severite: warning

    - condition: impaye_total > 0 AND statut = 'ACTIF'
      message: $alertes.client_impayes
      severite: warning

    - condition: date_derniere_commande < NOW() - INTERVAL '$seuils.inactivite_jours days'
      message: $alertes.client_inactif
      severite: info
```

---

## 9. Numérotation Automatique

### 9.1 Référence aux séquences

```yaml
- nom: numero
  type: text
  libelle: "Code client"
  unique: true
  auto_genere: true
  sequence: client    # Référence config/numerotation.yml > sequences.client
```

Les formats sont définis dans `config/numerotation.yml`.

---

## 10. Multi-Tenant Obligatoire

Le champ `tenant_id` est ajouté **automatiquement** par le moteur.
**NE PAS** le déclarer dans le YAML.

Toutes les requêtes SQL des champs calculés **DOIVENT** filtrer par `tenant_id`.

---

## 11. Checklist Validation

Avant de commiter un module YAML :

- [ ] Aucune valeur hardcodée (utiliser `$chemin.valeur`)
- [ ] Aucune statistique stockée (utiliser `calcule: true` + `sql:`)
- [ ] Toutes les requêtes SQL filtrent par `tenant_id = {tenant_id}`
- [ ] Toutes les requêtes SQL excluent `deleted_at IS NULL`
- [ ] Options select référencent `$...`
- [ ] Validations référencent `$validations.types.*` ou `$validations.regles.*`
- [ ] Exécuter `python -m moteur.validate_yaml` sans erreur

---

## 12. Fichiers de Configuration

| Fichier | Contenu |
|---------|---------|
| `config/constants.yml` | Constantes centralisées (statuts, TVA, devises, clients, etc.) |
| `config/validations.yml` | Patterns de validation |
| `config/workflows.yml` | Définitions des workflows |
| `config/numerotation.yml` | Formats de numérotation |
| `config/permissions.yml` | Rôles et permissions |
| `config/rapports.yml` | Définitions de rapports |

---

## 13. Nomenclature

### Noms de champs

| Convention | Exemple |
|------------|---------|
| snake_case | `date_creation`, `montant_ht` |
| Suffixe `_id` pour relations | `client_id`, `commercial_id` |
| Suffixe `_at` pour datetime | `created_at`, `validated_at` |
| Préfixe `is_` pour booléens | `is_active`, `is_paid` |
| Préfixe `nb_` ou `nombre_` pour compteurs | `nb_factures`, `nombre_lignes` |

---

**Dernière mise à jour** : 2026-03-16
**Version** : 3.0
**Règles applicables à tous les modules YAML AZALPLUS**
