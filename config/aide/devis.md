# Gestion des Devis

## Presentation

Le module Devis vous permet de creer, gerer et suivre vos propositions commerciales.

## Creer un devis

### Etape 1 : Informations generales
1. Cliquez sur **+ Ajouter** dans la barre d'outils
2. Selectionnez un client existant ou creez-en un nouveau
3. Definissez la date de validite du devis
4. Ajoutez une reference ou objet

### Etape 2 : Lignes de devis
1. Cliquez sur **+ Ajouter un produit**
2. Selectionnez un produit du catalogue ou saisissez une description libre
3. Indiquez la quantite et le prix unitaire
4. La TVA est calculee automatiquement selon le produit

### Etape 3 : Options
- **Remise globale** : Appliquez une remise sur le total
- **Code promo** : Saisissez un code promotionnel si applicable
- **Conditions** : Ajoutez vos conditions de vente
- **Notes** : Notes visibles par le client

## Statuts des devis

| Statut | Description |
|--------|-------------|
| BROUILLON | Devis en cours de redaction |
| ENVOYE | Devis envoye au client |
| ACCEPTE | Devis accepte par le client |
| REFUSE | Devis refuse par le client |
| EXPIRE | Devis dont la date de validite est depassee |

## Workflow

```
BROUILLON → ENVOYE → ACCEPTE → Convertir en facture
                  → REFUSE
                  → EXPIRE (automatique)
```

## Actions disponibles

### Envoyer par email
1. Ouvrez le devis
2. Cliquez sur **Envoyer par email**
3. Verifiez le destinataire et personnalisez le message
4. Cliquez sur **Envoyer**

### Generer un PDF
1. Ouvrez le devis
2. Cliquez sur **Generer PDF**
3. Le PDF s'ouvre dans un nouvel onglet

### Convertir en facture
1. Ouvrez un devis **ACCEPTE**
2. Cliquez sur **Convertir en facture**
3. Verifiez les informations
4. Validez la creation de la facture

### Dupliquer
1. Ouvrez un devis existant
2. Cliquez sur **Dupliquer**
3. Un nouveau devis est cree avec les memes informations

## Signature electronique

Les devis peuvent etre signes electroniquement par vos clients :
1. Envoyez le devis via le portail client
2. Le client accede au devis avec un lien securise
3. Il peut signer directement depuis son navigateur
4. La signature est enregistree avec l'adresse IP et l'horodatage

## Calculs automatiques

- **Total HT** = Somme des lignes HT - Remises
- **TVA** = Calculee par taux (ventilation automatique)
- **Total TTC** = Total HT + TVA

## Multi-devises

1. Selectionnez la devise du devis
2. Le taux de change est applique automatiquement
3. Les montants en devise de base (EUR) sont conserves pour la comptabilite

## Conseils

- Verifiez toujours la date de validite avant envoi
- Utilisez des modeles pour gagner du temps
- Ajoutez des notes pour clarifier les conditions
- Suivez vos devis dans le tableau de bord
