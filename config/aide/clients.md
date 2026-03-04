# Gestion des Clients

## Presentation

Le module Clients centralise toutes les informations sur vos clients et prospects. Il permet de suivre l'historique des interactions, les documents commerciaux et les statistiques.

## Creer un client

### Informations de base
1. Accedez au module **Clients**
2. Cliquez sur **+ Nouveau**
3. Remplissez les champs obligatoires :
   - Code client (auto-genere si vide)
   - Nom / Raison sociale
   - Type (Prospect, Client, VIP, etc.)

### Coordonnees
- Email principal
- Telephone fixe et mobile
- Site web
- Adresse complete

### Informations legales
- Numero TVA intracommunautaire
- SIRET / SIREN
- Forme juridique

## Types de clients

| Type | Description |
|------|-------------|
| PROSPECT | Contact initial, pas encore client |
| LEAD | Prospect qualifie |
| CUSTOMER | Client actif |
| VIP | Client premium |
| PARTNER | Partenaire commercial |
| CHURNED | Ancien client |
| SUPPLIER | Fournisseur (double role) |

## Contacts multiples

Chaque client peut avoir plusieurs contacts :
1. Ouvrez la fiche client
2. Section **Contacts**
3. Cliquez sur **+ Ajouter contact**
4. Renseignez les informations :
   - Nom et prenom
   - Fonction
   - Email et telephone
   - Role (principal, facturation, livraison, decideur)

## Conditions commerciales

### Conditions de paiement
- Comptant
- 30 jours net
- 45 jours fin de mois
- Conditions personnalisees

### Limite de credit
1. Definissez une limite de credit
2. Activez **Bloquer si depassement**
3. Les nouvelles factures seront bloquees si la limite est atteinte

### Remise client
- Remise globale en pourcentage
- Appliquee automatiquement sur les devis et factures

## Gestion du credit client

### Solde credit
Le solde credit represente :
- **Positif** : Le client a un avoir
- **Negatif** : Le client doit de l'argent

### Mouvements de credit
Consultez l'historique des mouvements :
1. Ouvrez la fiche client
2. Section **Credit**
3. Visualisez les ajouts/retraits

### Utilisation du credit
Lors de la creation d'une facture :
1. Le credit disponible est affiche
2. Cochez **Utiliser le credit**
3. Le montant est deduit automatiquement

## Statistiques client

### Indicateurs automatiques
- **CA total** : Chiffre d'affaires cumule
- **Nombre de commandes** : Total des factures
- **Derniere commande** : Date de la derniere facture
- **Premiere commande** : Date client depuis

### Score de sante
- Score de 0 a 100
- Calcule selon l'activite et les paiements
- Alerte si score < 50

### Score prospect
- Score de 0 a 100
- Indique la probabilite de conversion
- Base sur les interactions

## Actions rapides

### Creer un document
- **Creer devis** : Nouveau devis pre-rempli
- **Creer facture** : Nouvelle facture directe

### Voir l'historique
- Documents emis (devis, factures)
- Paiements recus
- Interventions realisees
- Notes et activites

### Rapports financiers
- **Releve de compte** : Historique des transactions
- **Balance agee** : Creances par anciennete

## Tags et segmentation

### Tags
Ajoutez des tags libres pour classifier :
- Secteur d'activite
- Source d'acquisition
- Statut specifique

### Segments
Creez des segments marketing :
- Par taille d'entreprise
- Par zone geographique
- Par comportement d'achat

## Import / Export

### Import clients
1. Accedez a **Parametres > Import**
2. Selectionnez le fichier CSV
3. Mappez les colonnes
4. Validez l'import

### Export clients
1. Accedez a la liste clients
2. Appliquez vos filtres
3. Cliquez sur **Exporter**
4. Choisissez le format (CSV, Excel)

## Conseils

- Maintenez les informations a jour
- Utilisez les tags pour segmenter votre base
- Suivez les scores de sante regulierement
- Definissez des limites de credit adaptees
- Documentez les interactions importantes
