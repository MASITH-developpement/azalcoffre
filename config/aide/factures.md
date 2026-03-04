# Gestion des Factures

## Presentation

Le module Factures vous permet de gerer l'ensemble de votre cycle de facturation : emission, suivi des paiements, relances et rapprochement.

## Creer une facture

### Depuis un devis
1. Ouvrez un devis au statut **ACCEPTE**
2. Cliquez sur **Convertir en facture**
3. Verifiez les informations reportees
4. Validez la facture

### Creation directe
1. Accedez au module **Factures**
2. Cliquez sur **+ Nouveau**
3. Remplissez les informations client et lignes
4. Enregistrez en brouillon ou validez directement

## Statuts des factures

| Statut | Description |
|--------|-------------|
| DRAFT | Brouillon, non envoyee |
| PENDING | En attente de validation |
| VALIDATED | Validee, prete a envoyer |
| SENT | Envoyee au client |
| PARTIALLY_PAID | Partiellement payee |
| PAID | Entierement payee |
| OVERDUE | En retard de paiement |
| CANCELLED | Annulee |

## Gestion des paiements

### Enregistrer un paiement
1. Ouvrez la facture concernee
2. Cliquez sur **Enregistrer paiement**
3. Saisissez :
   - Montant recu
   - Date de reception
   - Mode de paiement (virement, cheque, CB, etc.)
   - Reference du paiement
4. Validez le paiement

### Paiement partiel
- Saisissez le montant recu (inferieur au total)
- La facture passe en statut **PARTIALLY_PAID**
- Le reste a payer est mis a jour automatiquement

### Paiement multi-devises
1. Selectionnez la devise du paiement
2. Saisissez le montant dans cette devise
3. Le taux de change est applique automatiquement
4. Le montant en devise de base est calcule

## Relances

### Relance manuelle
1. Ouvrez une facture en retard
2. Cliquez sur **Relancer**
3. Personnalisez le message de relance
4. Envoyez par email

### Relances automatiques
Les relances peuvent etre configurees dans **Parametres > Notifications** :
- 1ere relance : 7 jours apres echeance
- 2eme relance : 15 jours apres echeance
- 3eme relance : 30 jours apres echeance

## Balance agee

Visualisez vos creances par anciennete :
1. Accedez a la fiche client
2. Cliquez sur **Balance agee**
3. Consultez la repartition :
   - Non echu
   - 0-30 jours
   - 31-60 jours
   - 61-90 jours
   - > 90 jours

## Releve de compte

Generez un releve pour vos clients :
1. Ouvrez la fiche client
2. Cliquez sur **Releve de compte**
3. Selectionnez la periode
4. Telechargez ou envoyez le PDF

## Avoirs

### Creer un avoir
1. Ouvrez la facture concernee
2. Cliquez sur **Generer avoir**
3. Selectionnez les lignes a crediter
4. Validez l'avoir

### Types d'avoirs
- **Avoir total** : Annule entierement la facture
- **Avoir partiel** : Remboursement partiel
- **Avoir commercial** : Geste commercial

## Export comptable

### Format d'export
- FEC (Fichier des Ecritures Comptables)
- CSV standard
- Format specifique (Sage, Cegid, etc.)

### Procedure
1. Accedez a **Comptabilite > Export**
2. Selectionnez la periode
3. Choisissez le format
4. Telechargez le fichier

## Mentions legales

Les mentions obligatoires sont automatiquement ajoutees :
- Numero de facture
- Date d'emission
- Informations vendeur (SIRET, TVA, etc.)
- Informations client
- Detail des produits/services
- Conditions de paiement
- Penalites de retard

## Conseils

- Validez rapidement vos factures pour respecter les delais legaux
- Utilisez les rappels automatiques pour reduire les impayes
- Consultez regulierement la balance agee
- Archivez vos factures pour une duree legale de 10 ans
