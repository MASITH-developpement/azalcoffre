# AZALPLUS - TODOLIST FONCTIONNALITES

**Version:** 1.1.0
**Date:** 2026-03-12
**Statut:** Identification des besoins (pas encore de programmation)

---

## Contexte produit

**AZALPLUS** = ERP SaaS **100% gratuit** pour les **TPE françaises** (4,2 millions d'entreprises)

### Cibles prioritaires
| Segment | Exemples | Potentiel |
|---------|----------|-----------|
| Artisans | Plombiers, électriciens, maçons | ★★★★★ |
| Commerces | Boutiques, restauration | ★★★★☆ |
| Services | Consultants, coachs, formateurs | ★★★★☆ |
| Créateurs | Auto-entrepreneurs, nouvelles entreprises | ★★★☆☆ |

### Modèle économique (revenus)
1. **Open Banking** — Commission 0.3-0.5% sur paiements via "Payer maintenant"
2. **Données anonymisées** — Études sectorielles B2B (banques, assureurs)
3. **Compte bancaire intégré** — Option 9-12€/mois (via Swan/Treezor)

### Objectifs
- Année 1 : 500 TPE actives
- Année 3 : 5 000 TPE actives
- Année 5 : 15 000 TPE actives

---

## Légende

| Icône | Signification |
|-------|---------------|
| ⬜ | À faire |
| 🔲 | Priorité haute (critique pour le business) |
| 💡 | Idée / Nice to have |
| 🔗 | Dépendance autre module |
| 💰 | Génère du revenu |

---

# 💰 MONÉTISATION (Priorité absolue)

Ces fonctionnalités génèrent les revenus d'AZALPLUS. Sans elles, pas de business.

## Paiement Open Banking (`paiements_openbanking.yml`) ⚠️ MODULE À CRÉER

### Partenaire : Fintecture (ou Bridge, Powens)

Commission : 0.99% (Fintecture) + 0.30% (AZALPLUS) = **1.29% total**

### Fonctionnalités à implémenter

#### Bouton "Payer maintenant" sur factures
- 🔲💰 Lien de paiement unique par facture
- 🔲💰 Bouton dans l'email de facture
- 🔲💰 Bouton sur le PDF de facture (QR code)
- 🔲💰 Page de paiement hébergée (AZALPLUS ou Fintecture)
- 🔲💰 Redirection vers banque du client (Open Banking)
- 🔲💰 Pré-remplissage des informations (montant, référence, IBAN)

#### Workflow paiement
```
Client reçoit facture email
        ↓
Clique "Payer maintenant"
        ↓
Choisit sa banque (liste 99% banques FR)
        ↓
Authentification bancaire (app mobile ou web)
        ↓
Confirme le virement pré-rempli
        ↓
Virement instantané (SEPA Instant) ou J+1
        ↓
Notification TPE "Facture payée"
        ↓
Rapprochement automatique dans AZALPLUS
```

#### Intégration Fintecture
- 🔲💰 API Connect (initiation paiement)
- 🔲💰 Webhooks (notification paiement reçu)
- 🔲💰 Gestion des statuts (pending, completed, failed)
- 🔲💰 Réconciliation automatique facture ↔ paiement
- ⬜ Dashboard paiements pour la TPE
- ⬜ Historique des paiements
- ⬜ Relance automatique si non payé

#### Avantages à communiquer au client final
- Moins cher que CB (1.29% vs 1.5-2.9%)
- Instantané (vs 2-7 jours)
- Pas de chargeback (virement irrévocable)
- Sécurisé (authentification bancaire)

---

## Compte bancaire intégré (`compte_bancaire.yml`) ⚠️ MODULE À CRÉER

### Partenaire : Swan (BaaS)

**Optionnel** — 20-30% des TPE activeront cette option

### Fonctionnalités à implémenter

#### Ouverture de compte
- 🔲💰 Parcours KYC intégré (vérification identité)
- 🔲💰 Création IBAN français
- 🔲💰 Activation carte bancaire virtuelle/physique
- ⬜ Multi-comptes (si besoin)

#### Fonctionnalités bancaires
- 🔲💰 Solde temps réel dans dashboard ERP
- 🔲💰 Historique des transactions
- 🔲💰 Virements SEPA sortants
- 🔲💰 Prélèvements SEPA
- ⬜ Catégorisation automatique
- ⬜ Export relevés PDF/CSV

#### Tap to Pay (encaissement carte)
- 🔲💰 Encaissement CB sur smartphone (NFC)
- 🔲💰 Terminal virtuel (saisie manuelle)
- ⬜ Lien de paiement CB (pour ventes à distance)

#### Carte bancaire
- ⬜ Carte physique avec plafonds configurables
- ⬜ Carte virtuelle pour achats en ligne
- ⬜ Blocage/déblocage instantané
- ⬜ Notifications temps réel

#### Intégration ERP
- 🔲💰 Rapprochement automatique (factures ↔ encaissements)
- ⬜ Prévision de trésorerie
- ⬜ Alertes solde bas

#### Tarification
| Élément | Prix |
|---------|------|
| Abonnement | 9-12€/mois |
| Carte physique | Incluse |
| Virements SEPA | Illimités |
| Tap to Pay | 1.2-1.5% |

---

## Données anonymisées (`donnees_agregees.yml`) ⚠️ MODULE À CRÉER

### Activation : à partir de 5 000 TPE

### Fonctionnalités à implémenter

#### Collecte des données (automatique)
- ⬜ CA moyen par secteur
- ⬜ Délais de paiement moyens
- ⬜ Saisonnalité par activité
- ⬜ Taux de transformation devis/facture
- ⬜ Panier moyen par secteur

#### Anonymisation (RGPD)
- 🔲 Agrégation minimum 10-20 TPE par groupe
- 🔲 Impossible de remonter à une TPE individuelle
- 🔲 Audit juridique RGPD

#### Produits data B2B
- 💡 Études sectorielles (5-15K€)
- 💡 Baromètres mensuels (2-5K€/mois)
- 💡 API temps réel (20-50K€/an)

---

## Factoring / Prêt (futur)

### Partenaire : Defacto (ou autre)

### Fonctionnalités futures
- 💡 Avance sur factures (factoring) depuis l'ERP
- 💡 Demande de prêt court terme en 2 clics
- 💡 Données pré-remplies depuis l'ERP
- 💡 Commission apporteur d'affaires

---

# COMMERCIAL

## Clients (`clients.yml`)

### Fonctionnalités existantes
- CRUD basique, workflow PROSPECT → CLIENT → ARCHIVÉ

### À implémenter

#### Gestion de base
- ⬜ Import CSV/Excel clients en masse
- ⬜ Export CSV/Excel avec filtres
- ⬜ Fusion de doublons (merge clients)
- ⬜ Détection automatique doublons (SIRET, email, téléphone)
- ⬜ Géocodage automatique des adresses (lat/lng)
- ⬜ Validation SIRET via API INSEE
- ⬜ Validation TVA intracommunautaire (VIES)

#### Multi-contacts
- ⬜ Contacts multiples par client (décideur, comptable, technique)
- ⬜ Rôles des contacts (principal, facturation, livraison)
- ⬜ Historique des changements de contacts

#### Segmentation
- ⬜ Scoring client automatique (CA, ancienneté, paiements)
- ⬜ Catégorisation automatique (PME, ETI, GE)
- ⬜ Tags personnalisés avec couleurs
- ⬜ Segments dynamiques (règles auto)

#### Financier
- ⬜ Encours autorisé par client
- ⬜ Alerte dépassement encours
- ⬜ Conditions de paiement personnalisées
- ⬜ Remises par défaut (%)
- ⬜ Historique des paiements
- ⬜ Score de solvabilité (intégration Creditsafe/Ellisphere)

#### Communication
- ⬜ Envoi email depuis fiche client
- ⬜ Envoi SMS depuis fiche client
- ⬜ Historique des communications (emails, appels, SMS)
- ⬜ Modèles d'emails personnalisés par client
- ⬜ Préférences de contact (email/tel/courrier)

#### Portail client
- 💡 Accès client à ses factures/devis
- 💡 Suivi des interventions en temps réel
- 💡 Demande de devis en ligne
- 💡 Signature électronique des devis

#### Analytics
- ⬜ Dashboard client (CA, évolution, top produits)
- ⬜ Graphique évolution CA par client
- ⬜ Comparaison N vs N-1
- ⬜ Prédiction churn (ML)

---

## Devis (`devis.yml`)

### Fonctionnalités existantes
- CRUD, workflow BROUILLON → ENVOYÉ → ACCEPTÉ → FACTURÉ

### À implémenter

#### Création
- ⬜ Création depuis opportunité (pré-remplissage)
- ⬜ Création depuis intervention (pré-remplissage)
- ⬜ Duplication de devis existant
- ⬜ Modèles de devis (templates)
- ⬜ Variantes de devis (options A/B/C)
- ⬜ Devis multi-devises

#### Lignes de devis
- ⬜ Recherche produits avec autocomplétion
- ⬜ Ajout produit par scan code-barres
- ⬜ Calcul automatique remises (ligne/global)
- ⬜ Gestion des lots/packs
- ⬜ Lignes de commentaire/section
- ⬜ Réorganisation drag & drop des lignes
- ⬜ Sous-totaux par section

#### Calculs
- ⬜ Multi-TVA par ligne
- ⬜ Éco-participation (DEEE)
- ⬜ Frais de port calculés
- ⬜ Remise conditionnelle (si montant > X)
- ⬜ Arrondi configurable

#### Envoi
- ⬜ Génération PDF personnalisé
- ⬜ Envoi par email avec tracking ouverture
- ⬜ Lien de signature en ligne
- ⬜ Relance automatique si pas de réponse
- ⬜ Notification acceptation/refus

#### Conversion
- 🔲 Transformation devis → commande (un clic)
- ⬜ Transformation partielle (sélection lignes)
- ⬜ Acompte depuis devis accepté

#### Suivi
- ⬜ Historique des versions
- ⬜ Comparaison entre versions
- ⬜ Raison du refus (sélection)
- ⬜ Statistiques taux de conversion

#### Documents
- ⬜ Pièces jointes (plans, photos)
- ⬜ Conditions générales attachées
- ⬜ Annexes techniques

---

## Commandes clients (`commandes.yml`) ⚠️ MODULE À CRÉER

### Flux commercial
```
Devis (accepté) → Commande → Bon de livraison → Facture
```

### À implémenter

#### Création
- 🔲 Création depuis devis accepté (reprise des lignes)
- ⬜ Création manuelle (vente directe sans devis)
- ⬜ Commande multi-devis (regroupement)
- ⬜ Numérotation automatique (CMD-2024-00001)

#### Informations commande
- ⬜ Référence client (n° commande client)
- ⬜ Date de commande
- ⬜ Date de livraison souhaitée
- ⬜ Adresse de livraison (différente facturation)
- ⬜ Contact livraison
- ⬜ Instructions de livraison
- ⬜ Conditions de paiement

#### Lignes de commande
- ⬜ Produits avec quantités
- ⬜ Prix unitaire (repris du devis ou catalogue)
- ⬜ Remises par ligne
- ⬜ TVA par ligne
- ⬜ Délai par ligne (si différent)
- ⬜ Statut par ligne (à livrer, partiellement livré, livré)

#### Workflow
```
BROUILLON → CONFIRMEE → EN_PREPARATION → EXPEDIEE → LIVREE → FACTUREE
                     → ANNULEE (avec motif)
```
- ⬜ Confirmation commande (envoi email client)
- ⬜ Accusé de réception PDF
- ⬜ Suivi préparation
- ⬜ Annulation avec motif

#### Stock
- 🔗 Réservation stock à confirmation
- 🔗 Vérification disponibilité temps réel
- ⬜ Alerte si stock insuffisant
- ⬜ Commande en attente de stock

#### Livraison
- 🔲 Génération bon de livraison (BL)
- ⬜ Livraison partielle
- ⬜ Livraison multiple (plusieurs BL)
- ⬜ Colisage
- ⬜ Transporteur et n° de suivi
- ⬜ Notification client expédition

#### Facturation
- 🔲 Transformation commande → facture
- ⬜ Facturation partielle (lignes livrées)
- ⬜ Facturation groupée (plusieurs commandes)
- ⬜ Acompte à la commande
- ⬜ Solde à la livraison

#### Suivi
- ⬜ Historique des modifications
- ⬜ Backlog commandes en cours
- ⬜ CA commandé vs livré vs facturé
- ⬜ Délai moyen de traitement

#### Documents
- ⬜ Confirmation de commande PDF
- ⬜ Pièces jointes
- ⬜ Bon de préparation interne

---

## Bons de livraison (`bons_livraison.yml`)

> **Note** : Ce module gère le **document** BL. Pour la logistique (transporteurs, étiquettes, tracking), voir `expéditions.yml`.

### Fonctionnalités existantes
- CRUD basique

### À implémenter

#### Création
- 🔲 Génération depuis commande
- ⬜ BL partiel (sélection lignes/quantités)
- ⬜ BL de retour (marchandise refusée)
- ⬜ Numérotation automatique (BL-2024-00001)

#### Informations
- ⬜ Référence commande liée
- ⬜ Date de livraison
- ⬜ Adresse de livraison
- ⬜ Contact destinataire

#### Lignes
- ⬜ Produits livrés avec quantités
- ⬜ N° de lot / série (traçabilité)
- ⬜ Emplacement de prélèvement

#### Workflow
```
BROUILLON → PREPARE → EXPEDIE → LIVRE → SIGNE
```
- ⬜ Validation préparation
- ⬜ Preuve de livraison (signature, photo)
- ⬜ Notification client

#### Stock
- 🔗 Déstockage automatique à validation
- ⬜ Annulation = restockage

#### Document
- ⬜ Bon de livraison PDF

#### Logistique
- 🔗 Transporteur, étiquettes, tracking → voir module `expeditions.yml`

---

## Factures (`factures.yml`)

### Fonctionnalités existantes
- CRUD complet, multi-TVA, workflow 6 états, Factur-X

### À implémenter

#### Création
- 🔲 Création depuis commande livrée
- 🔲 Création depuis bon de livraison
- ⬜ Facturation récurrente (abonnements)
- ⬜ Facturation groupée (plusieurs commandes → 1 facture)
- ⬜ Facture proforma
- ⬜ Facture d'acompte
- ⬜ Facture de solde
- ⬜ Facture d'avoir partiel

#### Conformité
- 🔲 Export Factur-X (PDF/A-3)
- 🔲 Export Chorus Pro (XML UBL)
- 🔲 Export FEC (Fichier des Écritures Comptables)
- ⬜ Numérotation séquentielle garantie
- ⬜ Archivage légal 10 ans
- ⬜ Signature électronique RGS

#### Paiements
- ⬜ Enregistrement paiement partiel
- ⬜ Paiement multi-modes (CB + chèque)
- ⬜ Rapprochement automatique virements
- ⬜ Intégration paiement en ligne (Stripe, GoCardless)
- ⬜ Prélèvement SEPA automatique
- ⬜ QR code paiement sur PDF

#### Relances
- 🔲 Relances automatiques (J+7, J+15, J+30)
- ⬜ Modèles de relance personnalisés
- ⬜ Escalade (email → courrier → mise en demeure)
- ⬜ Calcul pénalités de retard
- ⬜ Indemnité forfaitaire 40€

#### Reporting
- ⬜ Tableau de bord facturation
- ⬜ CA par période/client/produit
- ⬜ DSO (délai moyen de paiement)
- ⬜ Aging balance (balance âgée)
- ⬜ Prévision de trésorerie

#### Intégrations
- 🔗 Écriture comptable automatique
- 🔗 Mise à jour stock automatique
- ⬜ Export vers logiciel comptable (Sage, Cegid, QuickBooks)
- ⬜ Webhook sur changement de statut

---

## Avoirs (`avoirs.yml`)

### À implémenter
- ⬜ Création depuis facture (sélection lignes)
- ⬜ Avoir total (annulation facture)
- ⬜ Avoir partiel (remise commerciale)
- ⬜ Remboursement ou note de crédit
- ⬜ Imputation sur prochaine facture
- ⬜ Suivi utilisation du crédit
- ⬜ Export Factur-X avoir
- ⬜ Écriture comptable automatique

---

## Abonnements (`abonnements.yml`)

### À implémenter
- ⬜ Périodicité configurable (mensuel, trimestriel, annuel)
- ⬜ Date de début/fin
- ⬜ Renouvellement automatique
- ⬜ Alerte avant échéance
- ⬜ Génération facture automatique
- ⬜ Révision tarifaire annuelle
- ⬜ Gestion des suspensions
- ⬜ Résiliation avec préavis
- ⬜ Prorata temporis
- ⬜ Multi-lignes (bundle)
- 💡 Portail client pour gérer son abonnement

---

## Opportunités / Pipeline commercial (`opportunites.yml`)

### Fonctionnalités existantes
- Pipeline CRM 5 étapes, probabilité, montant estimé

### À implémenter

#### Pipeline
- ⬜ Pipeline personnalisable (étapes custom)
- ⬜ Vue Kanban drag & drop
- ⬜ Durée moyenne par étape
- ⬜ Probabilité auto par étape
- ⬜ Conversion rate par étape
- ⬜ Alertes inactivité

#### Gestion des deals
- ⬜ Fiche opportunité enrichie
- ⬜ Contacts associés
- ⬜ Produits/services concernés
- ⬜ Concurrents identifiés
- ⬜ Forces/faiblesses
- ⬜ Prochaines actions

#### Qualification
- ⬜ Score BANT automatique
- ⬜ Qualification MEDDIC
- ⬜ Questions de qualification configurables
- ⬜ Motifs de perte (analyse)

#### Automatisations
- ⬜ Relances automatiques
- ⬜ Séquences d'emails par étape
- ⬜ Scoring dynamique
- ⬜ Attribution automatique

#### Forecasting
- ⬜ Prévision CA pondéré
- ⬜ Objectifs par commercial
- ⬜ Comparaison réalisé vs objectif
- ⬜ Pipeline coverage ratio
- ⬜ Velocity (temps moyen pour closer)
- ⬜ Win rate par source/commercial

#### Reporting
- ⬜ Dashboard pipeline
- ⬜ Analyse sources
- ⬜ Performance commerciaux
- ⬜ Raisons de perte

#### Actions
- ⬜ Création devis depuis opportunité
- ⬜ Planification RDV
- ⬜ Historique des actions
- ⬜ Rappels automatiques
- 🔗 Liaison avec leads

---

## Leads (`leads.yml`)

### Fonctionnalités existantes
- Scoring, BANT, source UTM, statuts

### À implémenter

#### Capture
- ⬜ Formulaire web intégrable
- ⬜ Import depuis fichier
- ⬜ Intégration LinkedIn Sales Navigator
- ⬜ Capture depuis email
- ⬜ API de création lead

#### Qualification
- ⬜ Scoring automatique (comportement)
- ⬜ Enrichissement données (Clearbit, Hunter)
- ⬜ Détection entreprise depuis email
- ⬜ Attribution automatique (round-robin, géo, secteur)

#### Nurturing
- ⬜ Séquences d'emails automatiques
- ⬜ Triggers comportementaux
- ⬜ Score d'engagement
- ⬜ Relances programmées

#### Conversion
- 🔲 Conversion lead → client + opportunité
- ⬜ Historique conservé après conversion
- ⬜ Analyse taux de conversion par source

---

## Contrats (`contrats.yml`)

### À implémenter
- ⬜ Types de contrats (maintenance, location, prestation)
- ⬜ Durée et reconduction
- ⬜ Clauses configurables
- ⬜ Signatures électroniques (DocuSign, Yousign)
- ⬜ Alertes échéances
- ⬜ Révision tarifaire
- ⬜ Génération factures périodiques
- ⬜ Historique avenants
- ⬜ Résiliation avec motif
- ⬜ Documents attachés

---

## Campagnes marketing (`campagnes.yml`)

> **Note** : Module unifié pour toutes les campagnes (email, SMS, courrier, téléphone)

### À implémenter

#### Canaux
- ⬜ Email
- ⬜ SMS
- ⬜ Courrier postal
- ⬜ Téléphone

#### Création email
- ⬜ Éditeur email drag & drop
- ⬜ Templates prédéfinis
- ⬜ Blocs réutilisables
- ⬜ Personnalisation (merge tags)
- ⬜ Preview multi-devices
- ⬜ Test anti-spam

#### Segmentation
- ⬜ Ciblage par segment
- ⬜ Listes de contacts
- ⬜ Segments dynamiques (règles)
- ⬜ Import contacts
- ⬜ Exclusion automatique désabonnés
- ⬜ Suppression bounces

#### Envoi
- ⬜ Envoi immédiat
- ⬜ Planification envoi
- ⬜ Envoi par lots (throttling)
- ⬜ A/B testing (sujet, contenu)
- ⬜ Optimisation heure d'envoi

#### Tracking
- ⬜ Taux d'ouverture
- ⬜ Taux de clic
- ⬜ Carte de clics (heatmap)
- ⬜ Désabonnements
- ⬜ Bounces (hard/soft)
- ⬜ Plaintes spam
- ⬜ Analyse ROI

#### Automatisation
- ⬜ Séquences automatiques (drip)
- ⬜ Triggers (inscription, achat, abandon)
- ⬜ Conditions et branchements
- ⬜ Délais entre emails
- ⬜ Goals et conversions
- ⬜ Landing pages

#### Conformité
- ⬜ Lien désabonnement obligatoire
- ⬜ Gestion consentements RGPD
- ⬜ Double opt-in
- ⬜ Mentions légales

#### Providers
- ⬜ Mailjet / Sendinblue (Brevo)
- ⬜ SendGrid / Amazon SES
- ⬜ Twilio (SMS)

---

# ACHATS

## Fournisseurs (`fournisseurs.yml`)

### À implémenter
- ⬜ Import CSV fournisseurs
- ⬜ Validation SIRET/TVA
- ⬜ Contacts multiples
- ⬜ Conditions d'achat par défaut
- ⬜ Délais de livraison moyens
- ⬜ Évaluation fournisseur (qualité, délais)
- ⬜ Historique des achats
- ⬜ Comparaison prix fournisseurs
- ⬜ Certifications et documents
- ⬜ Scoring fournisseur

---

## Commandes d'achat (`commandes_achat.yml`)

### À implémenter
- ⬜ Création depuis stock min atteint
- ⬜ Demande de prix (RFQ)
- ⬜ Comparaison devis fournisseurs
- ⬜ Validation multi-niveaux
- ⬜ Envoi commande par email
- ⬜ Suivi statut livraison
- ⬜ Réception partielle
- ⬜ Gestion des litiges
- ⬜ Facture fournisseur liée
- ⬜ Écart prix commande/facture
- 🔗 Mise à jour stock à réception

---

## Réceptions (`receptions.yml`)

### À implémenter
- ⬜ Réception par scan code-barres
- ⬜ Contrôle quantités
- ⬜ Contrôle qualité
- ⬜ Photos des colis
- ⬜ Gestion des anomalies
- ⬜ Retour fournisseur
- ⬜ Mise à jour stock automatique
- ⬜ Bon de réception PDF
- ⬜ Traçabilité lot/série

---

# INVENTAIRE / STOCK

## Produits (`produits.yml`)

### Fonctionnalités existantes
- CRUD complet, variantes, multi-TVA

### À implémenter

#### Catalogue
- ⬜ Import CSV/Excel produits
- ⬜ Catégories hiérarchiques (arbre)
- ⬜ Marques
- ⬜ Photos multiples avec zoom
- ⬜ Documents techniques (PDF)
- ⬜ Vidéos produit

#### Codification
- ⬜ Génération EAN13 automatique
- ⬜ Code interne auto-incrémenté
- ⬜ QR code produit
- ⬜ Codes fournisseurs multiples

#### Prix
- ⬜ Prix d'achat par fournisseur
- ⬜ Tarifs par quantité (dégressif)
- ⬜ Tarifs par client/segment
- ⬜ Prix promotionnel avec période
- ⬜ Historique des prix

#### Variantes
- ⬜ Attributs personnalisés (taille, couleur, matière)
- ⬜ Matrice de variantes auto-générée
- ⬜ Prix différent par variante
- ⬜ Stock par variante

#### Stock
- 🔗 Stock temps réel par emplacement
- ⬜ Stock min/max avec alertes
- ⬜ Stock de sécurité
- ⬜ Prévision de rupture

#### E-commerce
- 💡 Sync WooCommerce/Shopify/PrestaShop
- 💡 Publication marketplace (Amazon, Cdiscount)

---

## Stock (`stock.yml`)

### À implémenter
- ⬜ Multi-entrepôts
- ⬜ Multi-emplacements (allée, rayon, niveau)
- ⬜ Stock par lot/numéro de série
- ⬜ FIFO/LIFO/FEFO
- ⬜ Inventaire tournant
- ⬜ Inventaire complet avec écarts
- ⬜ Valorisation stock (CUMP, FIFO)
- ⬜ Alertes stock min
- ⬜ Réapprovisionnement automatique
- ⬜ Transfert inter-entrepôts
- ⬜ Réservation stock (devis/commandes)

---

## Mouvements de stock (`mouvements_stock.yml`)

### À implémenter
- ⬜ Types : entrée, sortie, ajustement, transfert, inventaire
- ⬜ Motifs configurables
- ⬜ Lien avec documents (facture, intervention, réception)
- ⬜ Traçabilité complète
- ⬜ Validation mouvements
- ⬜ Annulation mouvement
- ⬜ Export historique
- ⬜ Coût du mouvement

---

## Variantes produit (`variantes_produit.yml`)

### À implémenter
- ⬜ Création automatique depuis matrice
- ⬜ SKU par variante
- ⬜ Prix spécifique
- ⬜ Stock spécifique
- ⬜ Photos par variante
- ⬜ Activation/désactivation variante

---

# COMPTABILITÉ / FINANCE

## Comptabilité (`comptabilite.yml`)

### À implémenter
- ⬜ Plan comptable français (PCG)
- ⬜ Création comptes
- ⬜ Écritures manuelles
- ⬜ Écritures automatiques (factures, paiements)
- ⬜ Lettrage automatique
- 🔗 Rapprochement bancaire → voir module dédié `rapprochement_bancaire.yml`
- ⬜ Grand livre
- ⬜ Balance générale
- ⬜ Journaux (achats, ventes, banque, OD)
- ⬜ Clôture mensuelle/annuelle
- ⬜ Export FEC
- ⬜ Déclaration TVA (CA3)
- 💡 Liasse fiscale

---

## Comptes bancaires (`comptes_bancaires.yml`)

### À implémenter
- ⬜ Multi-comptes
- ⬜ Solde temps réel
- ⬜ Import relevés OFX/QIF/CSV
- 🔲 Intégration Open Banking (Powens, Bridge, Fintecture)
- ⬜ Catégorisation automatique
- 🔗 Rapprochement bancaire → voir module dédié `rapprochement_bancaire.yml`
- ⬜ Prévision de trésorerie
- ⬜ Alertes solde bas
- ⬜ Virements SEPA
- ⬜ Historique des soldes

---

## Mouvements bancaires (`mouvements_bancaires.yml`)

### Fonctionnalités existantes
- Import, catégorisation, suggestions IA, workflow

### À implémenter
- 🔗 Rapprochement → voir module dédié `rapprochement_bancaire.yml`
- ⬜ Règles de catégorisation personnalisées
- ⬜ Apprentissage des catégorisations (ML)
- ⬜ Split d'un mouvement
- ⬜ Réconciliation multi-factures
- ⬜ Exclusion mouvements internes
- ⬜ Export rapproché pour comptable

---

## Paiements (`paiements.yml`)

### À implémenter
- ⬜ Modes : virement, chèque, CB, espèces, prélèvement
- ⬜ Paiement partiel
- ⬜ Paiement groupé (plusieurs factures)
- ⬜ Remise de chèques
- ⬜ Bordereau de remise
- ⬜ Suivi encaissements
- ⬜ Rapprochement avec banque
- ⬜ Reçu de paiement PDF
- ⬜ Historique par client

---

## Immobilisations (`immobilisations.yml`)

### Fonctionnalités existantes
- CRUD, types PCG, amortissement

### À implémenter
- ⬜ Calcul amortissement linéaire/dégressif
- ⬜ Tableau d'amortissement
- ⬜ Écritures comptables automatiques
- ⬜ Cession d'immobilisation
- ⬜ Plus/moins-value
- ⬜ Mise au rebut
- ⬜ Réévaluation
- ⬜ Inventaire physique
- ⬜ QR code sur actifs
- ⬜ Photos et documents

---

## Notes de frais (`notes_frais.yml`)

### Fonctionnalités existantes
- CRUD, workflow approbation, catégories

### À implémenter
- ⬜ OCR tickets de caisse
- ⬜ Photo justificatif obligatoire
- ⬜ Barème kilométrique automatique
- ⬜ Géolocalisation trajets
- ⬜ Plafonds par catégorie
- ⬜ Validation hiérarchique
- ⬜ Virement remboursement
- ⬜ Carte affaires virtuelle
- ⬜ Intégration carte bancaire (Spendesk, Qonto)
- ⬜ Export comptable

---

## Taxes (`taxes.yml`)

### Fonctionnalités existantes
- 9 taux français, codes EN16931

### À implémenter
- ⬜ Taxes personnalisées
- ⬜ Éco-taxes (DEEE, emballages)
- ⬜ Taxes par pays (international)
- ⬜ TVA sur marge
- ⬜ Autoliquidation BTP
- ⬜ Calcul automatique selon client/produit

---

# RESSOURCES HUMAINES

## Employés (`employes.yml`)

### Fonctionnalités existantes
- CRUD complet, contrats, statuts

### À implémenter

#### Gestion administrative
- ⬜ Dossier RH complet
- ⬜ Documents (contrat, diplômes, pièce identité)
- ⬜ Alertes échéances (fin CDD, période essai, visite médicale)
- ⬜ Historique des postes
- ⬜ Organigramme

#### Paie
- 💡 Éléments variables de paie
- 💡 Export vers logiciel paie
- 💡 Bulletins de paie (intégration)

#### Compétences
- ⬜ Matrice de compétences
- ⬜ Formations suivies
- ⬜ Certifications
- ⬜ Habilitations avec dates validité
- ⬜ Entretiens annuels

#### Planification
- 🔗 Planning des équipes
- ⬜ Disponibilités
- ⬜ Affectation aux projets/chantiers
- 🔗 Calcul charge vs capacité

---

## Congés (`conges.yml`)

### Fonctionnalités existantes
- Types congés, workflow approbation

### À implémenter
- ⬜ Solde de congés temps réel
- ⬜ Calcul automatique acquisition
- ⬜ Report N-1
- ⬜ Calendrier équipe
- ⬜ Détection conflits (absences simultanées)
- ⬜ Workflow validation manager
- ⬜ Notification équipe
- ⬜ Export planning absences
- ⬜ Intégration calendrier (Google, Outlook)
- ⬜ Récupération RTT

---

## Temps (`temps.yml`)

### Fonctionnalités existantes
- Saisie temps, timer, workflow, facturable

### À implémenter
- ⬜ Timer start/stop
- ⬜ Saisie hebdomadaire (timesheet)
- ⬜ Affectation projet/tâche/client
- ⬜ Taux horaire par projet
- ⬜ Heures sup automatiques
- ⬜ Validation manager
- ⬜ Facturation automatique
- ⬜ Rapport heures par projet/client
- ⬜ Comparaison estimé vs réel
- ⬜ Intégration calendrier
- 🔗 Lien avec interventions

---

# PROJETS

## Projets (`projets.yml`)

### Fonctionnalités existantes
- CRUD, phases, jalons, équipe, EVM

### À implémenter

#### Planification
- ⬜ Diagramme de Gantt interactif
- ⬜ Dépendances entre tâches (FS, FF, SS, SF)
- ⬜ Chemin critique
- ⬜ Jalons avec alertes
- ⬜ Baseline (référence initiale)

#### Ressources
- ⬜ Affectation ressources aux tâches
- ⬜ Charge par ressource
- ⬜ Détection surcharge
- ⬜ Lissage automatique

#### Budget
- ⬜ Budget initial
- ⬜ Coûts réels (temps + achats)
- ⬜ Écart budget
- ⬜ Prévision à terminaison

#### Suivi
- ⬜ % avancement global
- ⬜ Burndown chart
- ⬜ Velocity (Scrum)
- ⬜ Rapports d'avancement automatiques
- ⬜ Dashboard projet

#### Collaboration
- ⬜ Commentaires sur projet
- ⬜ Documents partagés
- ⬜ Notifications équipe
- 💡 Intégration Slack/Teams

---

## Tâches (`taches.yml`)

### Fonctionnalités existantes
- CRUD, workflow, dépendances, checklist

### À implémenter
- ⬜ Vue Kanban drag & drop
- ⬜ Vue liste avec filtres
- ⬜ Sous-tâches
- ⬜ Récurrence (tâches répétitives)
- ⬜ Estimation effort (heures, points)
- ⬜ Assignation multiple
- ⬜ Dates début/fin avec alertes
- ⬜ Pièces jointes
- ⬜ Commentaires
- ⬜ Historique des modifications
- ⬜ Templates de tâches

---

## Agenda (`agenda.yml`)

### À implémenter
- ⬜ Vue jour/semaine/mois
- ⬜ Création rapide événement
- ⬜ Types d'événements (RDV, réunion, intervention)
- ⬜ Récurrence
- ⬜ Invitations participants
- ⬜ Rappels (email, push)
- ⬜ Sync Google Calendar
- ⬜ Sync Outlook/Exchange
- ⬜ Calendrier partagé équipe
- ⬜ Créneaux disponibles
- 🔗 Lien avec interventions

---

# SERVICES / SAV

## Interventions (`interventions.yml`)

### Fonctionnalités existantes
- CRUD complet, workflow mobile 6 étapes, géolocalisation, signature

### À implémenter

#### Planification
- ⬜ Planning techniciens (vue carte/liste)
- ⬜ Optimisation tournées
- ⬜ Géolocalisation temps réel
- ⬜ Affectation automatique (proximité, compétences)
- ⬜ Durée estimée par type

#### Mobile (app technicien)
- ⬜ Mode offline complet
- ⬜ Sync automatique à reconnexion
- ⬜ Photos avant/après
- ⬜ Vidéos
- ⬜ Signature client sur écran
- ⬜ Timer intervention
- ⬜ Géolocalisation arrivée/départ

#### Rapport
- ⬜ Rapport d'intervention PDF
- ⬜ Checklist configurable
- ⬜ Pièces utilisées (déstockage auto)
- ⬜ Temps passé
- ⬜ Notes techniques
- ⬜ Anomalies détectées

#### Facturation
- 🔲 Génération facture automatique post-signature
- ⬜ Forfait + régie
- ⬜ Frais de déplacement
- ⬜ Pièces détachées

#### Suivi
- ⬜ Historique interventions par équipement
- ⬜ Historique par client
- ⬜ Statistiques technicien
- ⬜ Temps moyen par type

---

## Équipements (`equipements.yml`)

### À implémenter
- ⬜ Fiche équipement complète
- ⬜ QR code / code-barres
- ⬜ Localisation (client, site)
- ⬜ Historique des interventions
- ⬜ Historique des maintenances
- ⬜ Documents (manuel, garantie)
- ⬜ Date de mise en service
- ⬜ Date fin garantie avec alerte
- ⬜ Contrat de maintenance associé
- ⬜ Consommables liés
- ⬜ Arborescence équipements (parent/enfant)

---

## Maintenances (`maintenances.yml`)

### À implémenter
- ⬜ Types : préventive, curative, améliorative
- ⬜ Planification périodique (J, S, M, A)
- ⬜ Déclenchement sur compteur (km, heures)
- ⬜ Checklist de maintenance
- ⬜ Pièces de rechange
- ⬜ Alerte maintenance due
- ⬜ Historique des maintenances
- ⬜ Coût de maintenance par équipement
- ⬜ MTBF / MTTR

---

## Tickets (`tickets.yml`)

### Fonctionnalités existantes
- CRUD, workflow support

### À implémenter
- ⬜ Création par email (parsing)
- ⬜ Création depuis portail client
- ⬜ Catégorisation automatique
- ⬜ Priorité (critique, haute, normale, basse)
- ⬜ SLA par priorité avec alertes
- ⬜ Assignation automatique
- ⬜ Escalade automatique
- ⬜ Réponses prédéfinies (macros)
- ⬜ Base de connaissances
- ⬜ Satisfaction client (NPS)
- ⬜ Temps de résolution
- ⬜ Fusion de tickets
- 💡 Chatbot première ligne

---

## Réclamations (`reclamations.yml`)

### Fonctionnalités existantes
- CRUD, ISO 10002

### À implémenter
- ⬜ Workflow réclamation
- ⬜ Catégorisation (produit, service, livraison)
- ⬜ Gravité
- ⬜ Actions correctives
- ⬜ Compensation/geste commercial
- ⬜ Analyse causes racines
- ⬜ Statistiques réclamations
- ⬜ Rapport qualité

---

## SLA (`sla.yml`)

### À implémenter
- ⬜ Définition SLA par service/priorité
- ⬜ Temps de réponse cible
- ⬜ Temps de résolution cible
- ⬜ Calcul automatique respect SLA
- ⬜ Alertes avant dépassement
- ⬜ Rapport SLA mensuel
- ⬜ Pénalités contractuelles

---

# BTP

## Chantiers (`chantiers.yml`)

### À implémenter
- ⬜ Fiche chantier complète
- ⬜ Adresse avec géolocalisation
- ⬜ Planning chantier (Gantt)
- ⬜ Affectation équipes
- ⬜ Suivi avancement (%)
- ⬜ Photos d'avancement
- ⬜ Journal de chantier
- ⬜ Météo (impact planning)
- ⬜ Incidents/accidents
- ⬜ Documents (permis, plans, PPSPS)
- ⬜ Budget et coûts réels
- ⬜ Sous-traitants

---

## Situations de travaux (`situations_travaux.yml`)

### Fonctionnalités existantes
- Conforme NF P03-001, CCAG Travaux

### À implémenter
- ⬜ Situation mensuelle automatique
- ⬜ Avancement par poste du devis
- ⬜ Révision de prix
- ⬜ Retenue de garantie (5%)
- ⬜ Acomptes déduits
- ⬜ Génération PDF conforme
- ⬜ Validation maître d'ouvrage
- ⬜ Historique des situations

---

## Retenues de garantie (`retenues_garantie.yml`)

### Fonctionnalités existantes
- Conforme Loi 71-584

### À implémenter
- ⬜ Calcul automatique (5% HT)
- ⬜ Suivi par affaire/facture
- ⬜ Date de libération (1 an après réception)
- ⬜ Alerte avant libération
- ⬜ Caution bancaire de substitution
- ⬜ Libération partielle
- ⬜ Génération courrier de libération

---

# FLOTTE

## Véhicules (`vehicules.yml`)

### À implémenter
- ⬜ Fiche véhicule complète
- ⬜ Documents (carte grise, assurance)
- ⬜ Kilométrage avec historique
- ⬜ Affectation conducteur
- ⬜ Carnet d'entretien
- ⬜ Alertes (contrôle technique, assurance, vidange)
- ⬜ Suivi carburant
- ⬜ Coût total de possession (TCO)
- ⬜ Géolocalisation temps réel
- ⬜ Historique des trajets
- ⬜ Réservation véhicule
- ⬜ Sinistres/accidents
- ⬜ Amendes

---

# MÉDICAL

## Patients (`patients.yml`)

### Fonctionnalités existantes
- CRUD, données RGPD

### À implémenter
- ⬜ Dossier médical sécurisé
- ⬜ Historique consultations
- ⬜ Antécédents
- ⬜ Allergies
- ⬜ Traitements en cours
- ⬜ Documents médicaux
- ⬜ Consentements RGPD
- ⬜ Droit à l'oubli
- ⬜ Export données patient
- ⬜ Chiffrement renforcé

---

## Consultations (`consultations.yml`)

### À implémenter
- ⬜ Prise de RDV en ligne
- ⬜ Rappel SMS/email
- ⬜ Fiche consultation
- ⬜ Actes réalisés
- ⬜ Prescriptions
- ⬜ Ordonnances PDF
- ⬜ Facturation actes
- ⬜ Tiers payant
- ⬜ Intégration carte Vitale
- ⬜ Téléconsultation

---

# ASSURANCE

## Polices d'assurance (`polices_assurance.yml`)

### Fonctionnalités existantes
- Types RC Pro, Décennale, GLI, PNO

### À implémenter
- ⬜ Suivi des polices
- ⬜ Échéances et alertes
- ⬜ Documents (attestations)
- ⬜ Montants garantis
- ⬜ Franchises
- ⬜ Historique des sinistres
- ⬜ Renouvellement automatique
- ⬜ Comparaison devis assureurs

---

## Sinistres (`sinistres.yml`)

### À implémenter
- ⬜ Déclaration de sinistre
- ⬜ Type de sinistre
- ⬜ Circonstances
- ⬜ Photos/documents
- ⬜ Suivi du dossier
- ⬜ Indemnisation
- ⬜ Expertise
- ⬜ Historique des échanges assureur

---

# COMMUNICATION

## Réunions (`reunions.yml`)

### Fonctionnalités existantes
- Visio avec transcription IA et CR auto

### À implémenter
- ⬜ Planification réunion
- ⬜ Invitations par email
- ⬜ Intégration Zoom/Meet/Teams
- ⬜ Enregistrement vidéo
- ⬜ Transcription automatique (Whisper)
- ⬜ Résumé IA des points clés
- ⬜ Actions à suivre extraites
- ⬜ Compte-rendu PDF
- ⬜ Partage avec participants
- 🔗 Création tâches depuis actions

---

## Modèles d'email (`modeles_email.yml`)

### Fonctionnalités existantes
- Types configurés, variables Jinja2

### À implémenter
- ⬜ Éditeur WYSIWYG
- ⬜ Variables dynamiques (client, facture, etc.)
- ⬜ Preview avant envoi
- ⬜ Pièces jointes par défaut
- ⬜ Modèles par langue
- ⬜ Test envoi
- ⬜ Versioning des modèles

---

## Notifications (`notifications.yml`)

### À implémenter
- ⬜ Notifications in-app
- ⬜ Notifications push (mobile)
- ⬜ Notifications email
- ⬜ Notifications SMS
- ⬜ Préférences utilisateur
- ⬜ Regroupement (digest)
- ⬜ Historique des notifications
- ⬜ Marquer comme lu

---

# SYSTÈME / PARAMÈTRES

## Entreprise (`entreprise.yml`)

### Fonctionnalités existantes
- Config singleton, identité, préfixes numérotation

### À implémenter
- ⬜ Logo en plusieurs formats
- ⬜ Identité visuelle (couleurs)
- ⬜ Tampons et signatures
- ⬜ Mentions légales personnalisées
- ⬜ CGV par type de document
- ⬜ Coordonnées bancaires multiples
- ⬜ Établissements multiples
- ⬜ Certifications/labels

---

## Séquences (`sequences.yml`)

### À implémenter
- ⬜ Numérotation par type de document
- ⬜ Préfixe personnalisé
- ⬜ Reset annuel/mensuel
- ⬜ Format configurable (FA-2024-00001)
- ⬜ Séquence par établissement
- ⬜ Garantie unicité

---

## Webhooks (`webhooks.yml`)

### À implémenter
- ⬜ Événements déclencheurs
- ⬜ URL cible
- ⬜ Authentification (Basic, Bearer, HMAC)
- ⬜ Retry automatique
- ⬜ Historique des appels
- ⬜ Payload personnalisable
- ⬜ Filtres (conditions)
- ⬜ Test manuel

---

## Workflows (`workflows.yml`)

### À implémenter
- ⬜ Définition transitions
- ⬜ Conditions de transition
- ⬜ Actions automatiques
- ⬜ Notifications sur transition
- ⬜ Approbations multi-niveaux
- ⬜ Délais et escalades
- ⬜ Historique des transitions
- ⬜ Visualisation graphique

---

## Champs personnalisés (`champs_personnalises.yml`)

### À implémenter
- ⬜ Ajout champs sans code
- ⬜ Types supportés (text, number, date, select, relation)
- ⬜ Champs obligatoires
- ⬜ Valeurs par défaut
- ⬜ Visibilité par rôle
- ⬜ Ordre d'affichage
- ⬜ Groupes de champs

---

## Autocomplétion IA (`autocompletion_ia.yml`)

### Fonctionnalités existantes
- Lookup SIRET, adresses API gouv.fr

### À implémenter
- 🔲 Autocomplétion entreprise (SIRET → nom, adresse, TVA)
- 🔲 Autocomplétion adresse française
- ⬜ Validation TVA intracommunautaire (VIES)
- ⬜ Validation IBAN
- ⬜ Suggestions intelligentes (ML)
- ⬜ Historique des recherches
- ⬜ Cache des résultats
- ⬜ Multi-providers (fallback)

---

## RGPD (`rgpd.yml`)

### À implémenter
- ⬜ Registre des traitements
- ⬜ Demande d'accès aux données
- ⬜ Demande de rectification
- ⬜ Demande de suppression (droit à l'oubli)
- ⬜ Demande de portabilité (export)
- ⬜ Gestion des consentements
- ⬜ Historique des demandes
- ⬜ Anonymisation des données
- ⬜ Durées de conservation
- ⬜ Alertes purge automatique

---

## Documents

→ **Voir module GED** (`ged.yml`) dans la section "Modules supplémentaires"

---

# INTÉGRATIONS GLOBALES

## APIs externes
- ⬜ Open Banking (Powens, Bridge, Fintecture)
- ⬜ Stripe (paiements)
- ⬜ GoCardless (prélèvements SEPA)
- ⬜ Mailjet/Sendinblue (emails transactionnels)
- ⬜ Twilio/OVH (SMS)
- ⬜ DocuSign/Yousign (signatures)
- ⬜ Google Maps (géolocalisation)
- ⬜ Chorus Pro (factures publiques)
- ⬜ INSEE/SIRENE (données entreprises)
- ⬜ VIES (validation TVA UE)

## E-commerce
- 💡 WooCommerce
- 💡 PrestaShop
- 💡 Shopify
- 💡 Amazon/Cdiscount

## Comptabilité externe
- ⬜ Export Sage
- ⬜ Export Cegid
- ⬜ Export QuickBooks
- ⬜ Export EBP

## Calendriers
- ⬜ Google Calendar
- ⬜ Microsoft Outlook/Exchange
- ⬜ Apple Calendar (CalDAV)

## Communication multicanal

### Email
- ⬜ Envoi emails transactionnels (factures, devis, relances)
- ⬜ Réception emails (boîte dédiée par tenant)
- ⬜ Parsing emails entrants → création ticket/lead/réclamation
- ⬜ Réponse depuis AZALPLUS (thread conservé)
- ⬜ Tracking ouverture/clic
- ⬜ Pièces jointes automatiques (PDF)
- ⬜ Signatures personnalisées par utilisateur
- ⬜ Templates HTML responsive
- ⬜ Providers : Mailjet, Sendinblue, SendGrid, Amazon SES, SMTP custom

### SMS
- ⬜ Envoi SMS transactionnels (rappel RDV, confirmation)
- ⬜ Réception SMS (numéro dédié)
- ⬜ SMS bidirectionnel (réponse client)
- ⬜ Campagnes SMS marketing
- ⬜ Providers : Twilio, OVH, Vonage, AllMySMS

### WhatsApp Business
- ⬜ Envoi messages WhatsApp (templates approuvés)
- ⬜ Réception messages WhatsApp
- ⬜ Conversation bidirectionnelle
- ⬜ Envoi documents (devis, factures PDF)
- ⬜ Notifications automatiques (intervention planifiée, livraison)
- ⬜ Chatbot WhatsApp
- ⬜ Provider : WhatsApp Business API (Meta), Twilio, 360dialog

### Téléphonie
- 💡 Click-to-call depuis fiche client (appel direct sur mobile)
- 💡 Journal des appels (manuel ou auto via intégration)
- 💡 Rappels d'appels à faire

### Notifications push
- ⬜ Push mobile (iOS/Android) via Firebase FCM
- ⬜ Push navigateur (Web Push)
- ⬜ Préférences utilisateur (activer/désactiver par type)

### Courrier postal
- 💡 Envoi lettres recommandées (AR24, Maileva)
- 💡 Mise en demeure automatique
- 💡 Relances papier si email échoue

### Portail client
- 💡 Messagerie interne client ↔ entreprise
- 💡 Historique des échanges centralisé
- 💡 Demandes de support
- 💡 Commentaires sur documents (devis, factures)

### Centralisation (inbox unifiée)
- ⬜ Boîte de réception unique (tous canaux)
- ⬜ Vue conversation par client (email + SMS + WhatsApp + appels)
- ⬜ Assignation à un utilisateur
- ⬜ Statuts : non lu, en cours, traité
- ⬜ Réponse depuis n'importe quel canal
- ⬜ Historique complet par contact

---

# MOBILE

## Application mobile technicien
- ⬜ Login biométrique
- ⬜ Liste interventions du jour
- ⬜ Navigation GPS intégrée
- ⬜ Mode offline complet
- ⬜ Sync en arrière-plan
- ⬜ Photos avec timestamp/géoloc
- ⬜ Signature client
- ⬜ Scan code-barres équipements
- ⬜ Timer intervention
- ⬜ Notifications push
- ⬜ Chat avec le bureau

## Application mobile commercial
- 💡 Catalogue produits offline
- 💡 Création devis sur tablette
- 💡 Signature client
- 💡 Prise de commande
- 💡 Historique client

---

# REPORTING / BI

## Tableaux de bord
- ⬜ Dashboard dirigeant
- ⬜ Dashboard commercial
- ⬜ Dashboard technique
- ⬜ Dashboard financier
- ⬜ Widgets personnalisables
- ⬜ Période configurable
- ⬜ Comparaison N vs N-1

## Rapports
- ⬜ Générateur de rapports
- ⬜ Rapports programmés (email)
- ⬜ Export PDF/Excel
- ⬜ Graphiques interactifs
- ⬜ Filtres dynamiques

## KPIs
- ⬜ CA par période/client/produit
- ⬜ Marge brute
- ⬜ Taux de conversion devis
- ⬜ DSO (délai paiement)
- ⬜ NPS (satisfaction client)
- ⬜ Temps moyen intervention
- ⬜ Taux d'occupation techniciens

---

# IA / AUTOMATISATION

## Assistants IA
- ⬜ Catégorisation automatique mouvements
- ⬜ Suggestions de rapprochement
- ⬜ Prédiction de churn
- ⬜ Scoring leads automatique
- ⬜ Résumé de réunions
- ⬜ Génération de comptes-rendus
- ⬜ Chatbot support client
- ⬜ Analyse de sentiments (réclamations)

## Automatisations
- ⬜ Workflows automatiques
- ⬜ Relances programmées
- ⬜ Alertes configurables
- ⬜ Actions sur événements
- ⬜ Intégration n8n/Zapier

---

# RÉSUMÉ STATISTIQUES

| Catégorie | Modules | Fonctionnalités identifiées |
|-----------|---------|----------------------------|
| Commercial | 11 | ~120 |
| Achats | 3 | ~30 |
| Inventaire | 4 | ~50 |
| Comptabilité | 6 | ~80 |
| RH | 4 | ~50 |
| Projets | 3 | ~60 |
| Services/SAV | 6 | ~80 |
| BTP | 3 | ~35 |
| Flotte | 1 | ~15 |
| Médical | 2 | ~25 |
| Assurance | 2 | ~20 |
| Communication | 3 | ~30 |
| Système | 10 | ~60 |
| Intégrations | - | ~30 |
| Mobile | - | ~25 |
| Reporting | - | ~20 |
| IA | - | ~15 |
| **TOTAL** | **73** | **~800+** |

---

# PARCOURS PAR TYPE DE TPE

## 🔧 Artisans (plombiers, électriciens, maçons...)

### Besoins critiques
| Priorité | Fonctionnalité | Module |
|----------|----------------|--------|
| 🔲 | Devis rapide sur chantier (mobile) | Devis |
| 🔲 | Intervention avec signature client | Interventions |
| 🔲 | Facture générée après signature | Factures |
| 🔲 | Paiement instantané "Payer maintenant" | Open Banking |
| 🔲 | Photos avant/après avec géoloc | Interventions |
| ⬜ | Planning techniciens | Agenda |
| ⬜ | Gestion stock camionnette | Stock |
| ⬜ | Situations de travaux (BTP) | Situations |
| ⬜ | Retenue de garantie 5% | Retenues |

### Parcours type
```
Client appelle → Création intervention → Planification
        ↓
Technicien reçoit notification mobile
        ↓
Arrivée sur site → Photos avant → Travaux
        ↓
Photos après → Rapport → Signature client
        ↓
Facture générée automatiquement
        ↓
Email avec lien "Payer maintenant" (Open Banking)
        ↓
Virement instantané → TPE payée
```

### Modules prioritaires
1. Interventions (mobile-first)
2. Devis / Factures
3. Clients
4. Paiement Open Banking
5. Stock simplifié

---

## 🛒 Commerces (boutiques, restauration...)

### Besoins critiques
| Priorité | Fonctionnalité | Module |
|----------|----------------|--------|
| 🔲 | Catalogue produits simple | Produits |
| 🔲 | Vente comptoir (Tap to Pay) | Compte bancaire |
| 🔲 | Gestion stock temps réel | Stock |
| 🔲 | Factures clients | Factures |
| ⬜ | Commandes fournisseurs | Commandes achat |
| ⬜ | Alertes stock bas | Stock |
| ⬜ | Programme fidélité | Clients |
| 💡 | Caisse enregistreuse (NF525) | Caisse |
| 💡 | Sync e-commerce | Intégrations |

### Parcours type
```
Client achète en boutique
        ↓
Encaissement Tap to Pay (smartphone)
        ↓
Stock mis à jour automatiquement
        ↓
Alerte si stock bas
        ↓
Commande fournisseur automatique
        ↓
Réception marchandise → Stock mis à jour
```

### Modules prioritaires
1. Produits / Stock
2. Compte bancaire (Tap to Pay)
3. Clients
4. Commandes fournisseurs
5. Factures

---

## 💼 Services (consultants, coachs, formateurs...)

### Besoins critiques
| Priorité | Fonctionnalité | Module |
|----------|----------------|--------|
| 🔲 | Devis prestations | Devis |
| 🔲 | Factures avec mentions obligatoires | Factures |
| 🔲 | Paiement en ligne | Open Banking |
| 🔲 | Suivi temps par client/projet | Temps |
| ⬜ | Gestion projets simple | Projets |
| ⬜ | Agenda / RDV | Agenda |
| ⬜ | Abonnements récurrents | Abonnements |
| ⬜ | Notes de frais | Notes frais |
| 💡 | Visio intégrée | Réunions |
| 💡 | Portail client | Portail |

### Parcours type
```
Prospect contacte → Lead créé
        ↓
RDV découverte → Opportunité
        ↓
Devis envoyé → Signature en ligne
        ↓
Projet créé → Temps saisi
        ↓
Fin du mois → Facture générée
        ↓
Envoi email avec "Payer maintenant"
        ↓
Encaissement instantané
```

### Modules prioritaires
1. Devis / Factures
2. Clients
3. Paiement Open Banking
4. Temps / Projets
5. Agenda

---

## 🚀 Auto-entrepreneurs / Créateurs

### Besoins critiques
| Priorité | Fonctionnalité | Module |
|----------|----------------|--------|
| 🔲 | Onboarding ultra-simple (< 5 min) | Entreprise |
| 🔲 | Devis en 2 clics | Devis |
| 🔲 | Facture depuis devis | Factures |
| 🔲 | Paiement instantané | Open Banking |
| 🔲 | Suivi CA vs plafond micro | Dashboard |
| ⬜ | Export comptable simplifié | Comptabilité |
| ⬜ | Déclaration URSSAF (CA) | Export |
| ⬜ | Tableau de bord épuré | Dashboard |

### Parcours type
```
Inscription en 3 étapes (SIRET auto-complété)
        ↓
Premier devis créé en 1 minute
        ↓
Client accepte (signature en ligne)
        ↓
Facture générée → Envoyée par email/WhatsApp
        ↓
Client paie instantanément
        ↓
Dashboard : CA du mois, alerte si proche du plafond
```

### Modules prioritaires
1. Onboarding simplifié
2. Devis / Factures (ultra-simple)
3. Paiement Open Banking
4. Dashboard simple
5. Export URSSAF

---

# PROFILS MÉTIERS (activation modules)

## Principe

- 106 modules = trop pour un utilisateur
- Solution : activer automatiquement les modules selon le métier
- Un fichier YAML simple à maintenir

---

## Fichier de configuration (`config/profils_metiers.yml`)

```yaml
metiers:
  plombier:
    label: "Plombier / Chauffagiste"
    icone: "wrench"
    naf: ["43.22A", "43.22B"]
    modules: [clients, devis, factures, interventions, equipements]

  restaurant:
    label: "Restaurant"
    icone: "utensils"
    naf: ["56.10A", "56.10C"]
    modules: [clients, factures, caisse, stock, haccp]
```

---

## Flux d'inscription

### Cas 1 : SIRET connu
```
Saisie SIRET → API INSEE → Code NAF → Profil auto → Modules activés
```

### Cas 2 : Entreprise en création (pas de SIRET)
```
Sélection métier manuelle → Profil → Modules activés
→ Mention "SIRET en cours d'attribution" sur documents
→ Rappel après 7j / 30j pour ajouter SIRET
```

---

## Interface de sélection métier (si pas de SIRET)

### À implémenter
- 🔲 Champ de recherche avec suggestions ("plom" → Plombier...)
- 🔲 Grille des ~12 métiers populaires (icônes cliquables)
- 🔲 Liste déroulante par catégorie (~8 catégories, ~80 métiers)
- ⬜ Option "Autre activité" → profil généraliste

### Catégories
- Artisanat du bâtiment
- Commerce et restauration
- Services aux entreprises
- Services à la personne
- Santé et bien-être
- Transport et logistique
- Création et communication
- Immobilier

---

## Activation des modules

### À implémenter
- 🔲 Lecture du profil métier
- 🔲 Activation automatique des modules listés
- 🔲 Menu affiche seulement les modules activés
- ⬜ Accès au catalogue complet pour activer d'autres modules

---

## Demande de modules supplémentaires

### À implémenter
- ⬜ Page "Catalogue des modules"
- ⬜ Activation en 1 clic (self-service)
- ⬜ Formulaire "Je ne trouve pas ce que je cherche"

---

## Maintenance

| Action | Comment |
|--------|---------|
| Ajouter un métier | 5 lignes dans le YAML |
| Modifier les modules | Éditer une ligne |
| Ajouter un code NAF | Ajouter dans la liste |

**Pas de base de données, pas d'interface admin complexe.**

---

# ONBOARDING TPE (critique)

## Étapes d'inscription (< 5 minutes)

### Étape 1 : Identification
- ⬜ Saisie SIRET uniquement
- 🔲 Autocomplétion données entreprise (API INSEE)
- ⬜ Nom, adresse, forme juridique auto-remplis
- ⬜ N° TVA intra auto-généré

### Étape 2 : Compte utilisateur
- ⬜ Email + mot de passe
- ⬜ Vérification email (magic link)
- ⬜ Connexion Google/Apple (optionnel)

### Étape 3 : Personnalisation
- ⬜ Upload logo (optionnel, skip possible)
- ⬜ Choix couleur principale
- ⬜ IBAN pour recevoir les paiements

### Étape 4 : Premier document
- ⬜ Création devis guidée (wizard)
- ⬜ Templates par secteur (plombier, consultant, etc.)
- ⬜ Envoi immédiat possible

### Gamification onboarding
- 💡 Checklist de démarrage (5 étapes = badge)
- 💡 Tutoriels vidéo courts (< 2 min)
- 💡 Aide contextuelle (tooltips)

---

# PRIORITÉS DE DÉVELOPPEMENT

## Phase 1 : MVP (0-6 mois) — 500 TPE

### Objectif : Boucle de base fonctionnelle

```
Devis → Commande → Facture → Paiement Open Banking
```

| Module | Priorité | Dépendances |
|--------|----------|-------------|
| Entreprise (onboarding) | P0 | - |
| Clients | P0 | Entreprise |
| Devis | P0 | Clients |
| Commandes | P0 | Devis |
| Factures | P0 | Commandes |
| **Paiement Open Banking** | P0 | Factures, Fintecture |
| Email transactionnel | P0 | - |
| Dashboard simple | P1 | - |

### Intégrations Phase 1
- 🔲 Fintecture (Open Banking) — **critique**
- 🔲 API INSEE/SIRENE (autocomplétion SIRET)
- 🔲 API Adresse gouv.fr
- ⬜ Mailjet/Sendinblue (emails)

---

## Phase 2 : Expansion (6-12 mois) — 2 000 TPE

### Objectif : Interventions + Stock + Compte bancaire

| Module | Priorité | Dépendances |
|--------|----------|-------------|
| Interventions (mobile) | P0 | Clients, Factures |
| Produits / Stock | P1 | - |
| **Compte bancaire Swan** | P1 | - |
| Tap to Pay | P1 | Compte bancaire |
| SMS / WhatsApp | P1 | - |
| Relances automatiques | P1 | Factures |
| Rapprochement bancaire | P2 | Compte bancaire |

### Intégrations Phase 2
- 🔲 Swan (compte bancaire BaaS) — **critique**
- ⬜ Twilio (SMS)
- ⬜ WhatsApp Business API
- ⬜ Webhook / n8n

---

## Phase 3 : Maturité (12-24 mois) — 5 000 TPE

### Objectif : Données + Financement + Verticalisation

| Module | Priorité | Dépendances |
|--------|----------|-------------|
| Données anonymisées B2B | P0 | 5000+ TPE |
| BTP (situations, retenues) | P1 | Chantiers |
| Projets avancés | P1 | - |
| Comptabilité complète | P2 | - |
| RH simplifié | P2 | - |
| **Factoring (Defacto)** | P2 | Factures |
| App mobile native | P2 | - |

### Intégrations Phase 3
- 💡 Defacto (factoring)
- 💡 Chorus Pro (marchés publics)
- 💡 Export FEC
- 💡 WooCommerce / Shopify

---

# MODULES À CRÉER (manquants)

| Module | Fichier | Priorité | Description |
|--------|---------|----------|-------------|
| Commandes clients | `commandes.yml` | P0 | Entre devis et facture |
| Bons de livraison | `bons_livraison.yml` | P1 | Gestion livraisons |
| Paiements Open Banking | `paiements_openbanking.yml` | P0 | Intégration Fintecture |
| Compte bancaire | `compte_bancaire.yml` | P1 | Intégration Swan |
| Caisse | `caisse.yml` | P2 | NF525 pour commerces |
| Abonnements | `abonnements.yml` | P1 | Factures récurrentes |
| Départements | `departements.yml` | P2 | Organisation RH |
| Entrepôts | `entrepots.yml` | P2 | Multi-dépôts |
| Emplacements | `emplacements.yml` | P2 | Stockage précis |
| Catégories produits | `categories.yml` | P1 | Hiérarchie produits |

---

# RÉSUMÉ FINAL

## Statistiques mises à jour

| Catégorie | Modules | Fonctionnalités |
|-----------|---------|-----------------|
| Monétisation | 3 | ~40 |
| Commercial | 13 | ~150 |
| Achats | 3 | ~30 |
| Inventaire | 6 | ~60 |
| Comptabilité | 6 | ~80 |
| RH | 4 | ~50 |
| Projets | 3 | ~60 |
| Services/SAV | 6 | ~80 |
| BTP | 3 | ~35 |
| Flotte | 1 | ~15 |
| Communication | - | ~50 |
| Système | 10 | ~60 |
| Mobile | - | ~30 |
| Reporting | - | ~25 |
| IA | - | ~20 |
| Onboarding | - | ~15 |
| **TOTAL** | **~80** | **~850+** |

---

# MODULES SUPPLÉMENTAIRES

## GED - Gestion Électronique de Documents (`ged.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Stockage et organisation
- ⬜ Upload fichiers multiples (drag & drop)
- ⬜ Types acceptés : PDF, images, Office, vidéos
- ⬜ Limite de taille configurable par tenant
- ⬜ Stockage S3/MinIO
- ⬜ Arborescence dossiers
- ⬜ Tags et métadonnées
- ⬜ Catégories personnalisées

#### Indexation et recherche
- ⬜ OCR automatique (extraction texte des PDF/images)
- ⬜ Recherche full-text
- ⬜ Recherche par métadonnées
- ⬜ Filtres avancés (date, type, auteur)
- ⬜ Indexation automatique du contenu

#### Versioning
- ⬜ Historique des versions
- ⬜ Comparaison entre versions
- ⬜ Restauration version antérieure
- ⬜ Commentaires par version

#### Partage et collaboration
- ⬜ Liens de partage externe (avec expiration)
- ⬜ Permissions par dossier/fichier
- ⬜ Annotations sur documents
- ⬜ Validation workflow (approbation)
- ⬜ Notification modification

#### Intégration modules
- 🔗 Documents attachés aux clients, factures, interventions, etc.
- ⬜ Génération automatique de dossiers par entité
- ⬜ Templates de nommage automatique

#### Archivage légal
- ⬜ Coffre-fort électronique (valeur probante)
- ⬜ Horodatage certifié
- ⬜ Conservation 10 ans (factures)
- ⬜ Export archives

---

## Cautions et garanties bancaires (`cautions.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Types de cautions
- ⬜ Caution de soumission (appels d'offres)
- ⬜ Caution de bonne exécution
- ⬜ Caution de retenue de garantie (substitution)
- ⬜ Caution de restitution d'acompte
- ⬜ Garantie bancaire à première demande

#### Gestion
- ⬜ Suivi par affaire/chantier
- ⬜ Montant et pourcentage
- ⬜ Date de début/fin
- ⬜ Banque émettrice
- ⬜ Frais de caution
- ⬜ Documents attachés (original, copie)

#### Alertes
- ⬜ Alerte échéance proche
- ⬜ Alerte renouvellement
- ⬜ Alerte libération possible
- ⬜ Notification banque

#### Reporting
- ⬜ Encours total cautions
- ⬜ Coût annuel des cautions
- ⬜ Cautions par banque

---

## Articles / Nomenclatures (`articles.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Nomenclatures (BOM)
- ⬜ Composition produit fini
- ⬜ Multi-niveaux (sous-ensembles)
- ⬜ Quantités par composant
- ⬜ Unités de mesure
- ⬜ Pourcentage de perte
- ⬜ Alternatives composants

#### Calculs
- ⬜ Coût de revient calculé
- ⬜ Marge calculée automatiquement
- ⬜ Explosion nomenclature
- ⬜ Où utilisé (reverse BOM)

#### Variantes
- ⬜ Nomenclature par variante
- ⬜ Options configurables
- ⬜ Règles de compatibilité

---

## RH Complet (`rh_complet.yml`) - Extensions employés

### Fonctionnalités supplémentaires à implémenter

#### Recrutement
- ⬜ Fiches de poste
- ⬜ Publication annonces (Indeed, LinkedIn)
- ⬜ Réception candidatures
- ⬜ Parsing CV automatique
- ⬜ Pipeline recrutement (Kanban)
- ⬜ Entretiens planifiés
- ⬜ Évaluation candidats
- ⬜ Onboarding checklist

#### Formation
- ⬜ Catalogue formations
- ⬜ Plan de formation
- ⬜ Inscriptions
- ⬜ Suivi présence
- ⬜ Évaluations à chaud/froid
- ⬜ Certifications obtenues
- ⬜ Budget formation

#### Entretiens
- ⬜ Entretien annuel
- ⬜ Entretien professionnel
- ⬜ Objectifs SMART
- ⬜ Évaluation compétences
- ⬜ Plan de développement
- ⬜ Historique des entretiens

#### Pointage
- ⬜ Badgeuse virtuelle (mobile)
- ⬜ Pointage géolocalisé
- ⬜ Gestion des horaires
- ⬜ Heures supplémentaires
- ⬜ Travail de nuit/weekend
- ⬜ Export pour paie

#### Paie (intégration)
- 💡 Éléments variables de paie
- 💡 Export Silae, PayFit, ADP
- 💡 Bulletins de paie (stockage)
- 💡 DSN (Déclaration Sociale Nominative)

---

## Apporteurs d'affaires (`apporteurs.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Gestion partenaires
- ⬜ Fiche apporteur (coordonnées, contrat)
- ⬜ Type : agent commercial, partenaire, prescripteur
- ⬜ Secteur géographique
- ⬜ Secteur d'activité
- ⬜ Contrat d'apporteur (PDF)
- ⬜ Statuts (actif, suspendu, résilié)

#### Commissions
- ⬜ Barème de commissions (% ou fixe)
- ⬜ Commission par produit/service
- ⬜ Commission récurrente (abonnements)
- ⬜ Seuils et paliers
- ⬜ Durée de commissionnement
- ⬜ Calcul automatique

#### Suivi affaires
- ⬜ Affaires apportées (leads, devis, ventes)
- ⬜ Attribution automatique
- ⬜ Suivi conversion
- ⬜ CA généré par apporteur

#### Paiements
- ⬜ Relevé de commissions
- ⬜ Factures d'apporteur (auto-facturation ou saisie)
- ⬜ Statut paiement
- ⬜ Historique des versements

#### Portail apporteur
- 💡 Accès apporteur (lecture seule)
- 💡 Suivi de ses affaires
- 💡 Relevés de commissions
- 💡 Soumission de leads

---

## E-commerce (`ecommerce.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Catalogue en ligne
- ⬜ Publication produits depuis catalogue
- ⬜ Photos multiples
- ⬜ Descriptions HTML
- ⬜ Prix public / prix promo
- ⬜ Disponibilité temps réel
- ⬜ Catégories et filtres

#### Panier et commande
- ⬜ Panier client
- ⬜ Compte client (inscription/connexion)
- ⬜ Commande invité
- ⬜ Adresses de livraison multiples
- ⬜ Choix transporteur
- ⬜ Calcul frais de port

#### Paiement
- ⬜ Paiement CB (Stripe, PayPal)
- ⬜ Paiement Open Banking
- ⬜ Paiement en plusieurs fois
- ⬜ Carte cadeau
- ⬜ Code promo

#### Intégration ERP
- 🔗 Sync stock temps réel
- 🔗 Création commande automatique
- 🔗 Facturation automatique
- 🔗 Mise à jour statut commande

#### Synchronisation marketplaces
- 💡 Amazon
- 💡 Cdiscount
- 💡 Leboncoin Pro
- 💡 Facebook Shop

#### CMS intégré
- 💡 Pages statiques (À propos, CGV, etc.)
- 💡 Blog
- 💡 SEO (meta tags, sitemap)

---

## Caisse / POS (`caisse.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Interface de vente
- ⬜ Interface tactile optimisée
- ⬜ Recherche produit rapide
- ⬜ Scan code-barres
- ⬜ Pavé numérique
- ⬜ Produits favoris
- ⬜ Catégories avec icônes
- ⬜ Mode kiosque (plein écran)

#### Panier
- ⬜ Ajout/suppression articles
- ⬜ Modification quantité
- ⬜ Remise par ligne
- ⬜ Remise globale
- ⬜ Commentaire sur article
- ⬜ Mise en attente ticket

#### Paiement
- ⬜ Multi-modes (espèces, CB, chèque)
- ⬜ Paiement mixte
- ⬜ Rendu monnaie calculé
- ⬜ Tap to Pay (NFC smartphone)
- ⬜ Terminal CB externe
- ⬜ QR code paiement

#### Ticket et facturation
- ⬜ Ticket de caisse (impression thermique)
- ⬜ Facture simplifiée
- ⬜ Facture complète
- ⬜ Envoi par email/SMS

#### Conformité NF525
- 🔲 Inaltérabilité des données
- 🔲 Sécurisation des données
- 🔲 Conservation des données
- 🔲 Archivage automatique
- ⬜ Certificat de conformité
- ⬜ Export contrôle fiscal

#### Gestion caisse
- ⬜ Ouverture/fermeture de caisse
- ⬜ Fond de caisse
- ⬜ Z de caisse (clôture)
- ⬜ X de caisse (intermédiaire)
- ⬜ Mouvements de caisse (entrées/sorties)
- ⬜ Écarts de caisse

#### Multi-caisses
- ⬜ Plusieurs caisses par établissement
- ⬜ Droits par caissier
- ⬜ Consolidation journalière

---

## Sites web (`sites_web.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Création site vitrine
- ⬜ Templates prédéfinis par secteur
- ⬜ Éditeur drag & drop
- ⬜ Blocs préconçus (hero, services, témoignages)
- ⬜ Personnalisation couleurs/polices
- ⬜ Import logo et images
- ⬜ Responsive automatique

#### Pages
- ⬜ Page d'accueil
- ⬜ Page services/produits
- ⬜ Page à propos
- ⬜ Page contact (formulaire)
- ⬜ Blog / Actualités
- ⬜ Pages légales (CGV, CGU, mentions)

#### Formulaires
- ⬜ Formulaire de contact
- ⬜ Demande de devis
- ⬜ Prise de RDV en ligne
- 🔗 Création lead automatique

#### SEO
- ⬜ Meta title / description par page
- ⬜ URL personnalisées
- ⬜ Sitemap XML auto
- ⬜ Google Analytics intégré
- ⬜ Schema.org (données structurées)

#### Hébergement
- ⬜ Sous-domaine AZALPLUS (nom.azalplus.fr)
- ⬜ Domaine personnalisé (option)
- ⬜ SSL automatique (Let's Encrypt)
- ⬜ CDN pour performance

#### Maintenance
- ⬜ Statistiques de visites
- ⬜ Formulaires reçus
- ⬜ Modifications en temps réel
- ⬜ Prévisualisation avant publication

---

## Sauvegardes (`sauvegardes.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Sauvegardes automatiques
- ⬜ Backup quotidien automatique
- ⬜ Backup à la demande
- ⬜ Rétention configurable (7j, 30j, 90j, 1an)
- ⬜ Stockage distant (S3, GCS)
- ⬜ Chiffrement des sauvegardes

#### Contenu sauvegardé
- ⬜ Base de données complète
- ⬜ Documents/fichiers
- ⬜ Configuration tenant
- ⬜ Historique des modifications

#### Restauration
- ⬜ Restauration complète
- ⬜ Restauration sélective (module, période)
- ⬜ Restauration dans environnement de test
- ⬜ Historique des restaurations

#### Export données
- ⬜ Export complet (RGPD portabilité)
- ⬜ Export par module (CSV, JSON)
- ⬜ Export FEC (comptabilité)
- ⬜ Export documents (ZIP)

#### Monitoring
- ⬜ Statut dernière sauvegarde
- ⬜ Alertes en cas d'échec
- ⬜ Taille des sauvegardes
- ⬜ Historique des sauvegardes

---

## Import de données (`import_donnees.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Import fichiers
- ⬜ Import CSV
- ⬜ Import Excel (xlsx)
- ⬜ Import JSON
- ⬜ Mapping colonnes (source → destination)
- ⬜ Preview avant import
- ⬜ Validation des données
- ⬜ Gestion des erreurs (skip, stop, log)

#### Import depuis autres logiciels (API)
- ⬜ Odoo (API REST)
- ⬜ Pennylane (API)
- ⬜ Axonaut (API)
- ⬜ Dolibarr (API/export)
- ⬜ Sellsy (API)

#### Import fichiers (sans API)
- ⬜ Sage (export fichier)
- ⬜ Ciel (export fichier)
- ⬜ EBP (export fichier)
- ⬜ QuickBooks (export fichier)

#### Données importables
- ⬜ Clients
- ⬜ Fournisseurs
- ⬜ Produits
- ⬜ Factures (historique)
- ⬜ Paiements
- ⬜ Écritures comptables
- ⬜ Employés

#### Assistant d'import
- ⬜ Wizard étape par étape
- ⬜ Détection automatique du format
- ⬜ Suggestions de mapping
- ⬜ Dédoublonnage automatique
- ⬜ Rapport d'import détaillé

#### Historique
- ⬜ Log des imports
- ⬜ Rollback possible (annulation import)
- ⬜ Fichiers sources conservés

---

## Répondeur téléphonique IA (`repondeur_ia.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Réception d'appels
- ⬜ Numéro virtuel dédié (ou transfert)
- ⬜ Décroché automatique
- ⬜ Message d'accueil personnalisé
- ⬜ Reconnaissance vocale (speech-to-text)
- ⬜ Compréhension intention (NLU)

#### Conversations IA
- ⬜ Réponses contextuelles
- ⬜ FAQ automatique
- ⬜ Prise de RDV vocale
- ⬜ Qualification lead
- ⬜ Collecte informations (nom, email, besoin)
- ⬜ Synthèse vocale naturelle (TTS)

#### Actions automatiques
- 🔗 Création lead/ticket depuis appel
- 🔗 Planification RDV dans agenda
- ⬜ Envoi SMS de confirmation
- ⬜ Notification équipe (nouvel appel)
- ⬜ Escalade vers humain si besoin

#### Transcription et analyse
- ⬜ Transcription complète de l'appel
- ⬜ Résumé IA de la conversation
- ⬜ Détection de sentiment
- ⬜ Tags automatiques
- ⬜ Historique des appels

#### Configuration
- ⬜ Horaires de disponibilité
- ⬜ Message hors horaires
- ⬜ Transfert vers mobile si urgent
- ⬜ Plusieurs scénarios (vente, SAV, RDV)

#### Providers
- ⬜ Intégration Twilio (voix)
- ⬜ Intégration OpenAI Whisper (STT)
- ⬜ Intégration OpenAI GPT (NLU)
- ⬜ Intégration ElevenLabs ou OpenAI (TTS)

---

## Secrétariat IA (`secretariat_ia.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Gestion emails entrants
- ⬜ Lecture automatique des emails
- ⬜ Classification (urgent, info, spam)
- ⬜ Extraction informations clés
- ⬜ Suggestion de réponse
- ⬜ Réponse automatique (si autorisé)
- ⬜ Transfert vers bon interlocuteur

#### Prise de RDV intelligente
- ⬜ Analyse demande de RDV par email
- ⬜ Proposition créneaux disponibles
- ⬜ Confirmation automatique
- ⬜ Rappels automatiques
- ⬜ Gestion des reports

#### Rédaction assistée
- ⬜ Génération emails professionnels
- ⬜ Reformulation (ton, longueur)
- ⬜ Traduction automatique
- ⬜ Correction orthographe/grammaire
- ⬜ Modèles intelligents

#### Tâches administratives
- ⬜ Rappels automatiques (relances, échéances)
- ⬜ Création tâches depuis emails
- ⬜ Suivi des demandes
- ⬜ Rapports d'activité

#### Intégrations
- 🔗 Agenda (créneaux disponibles)
- 🔗 Clients (historique)
- 🔗 Tâches (création automatique)
- 🔗 Tickets (création depuis email)

---

## Rapprochement bancaire automatique (`rapprochement_bancaire.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Import relevés
- ⬜ Connexion Open Banking (Powens, Bridge)
- ⬜ Sync automatique quotidien
- ⬜ Import manuel (OFX, QIF, CSV)
- ⬜ Multi-comptes bancaires

#### Rapprochement automatique
- ⬜ Matching montant exact
- ⬜ Matching référence (n° facture)
- ⬜ Matching par nom client/fournisseur
- ⬜ Suggestions IA pour cas ambigus
- ⬜ Apprentissage des habitudes
- ⬜ Règles de rapprochement personnalisées

#### Types de rapprochement
- 🔗 Factures clients (encaissements)
- 🔗 Factures fournisseurs (décaissements)
- 🔗 Salaires (virements paie)
- 🔗 Notes de frais (remboursements)
- 🔗 Charges récurrentes (loyer, assurance, etc.)
- 🔗 Prélèvements (URSSAF, impôts)
- 🔗 Acomptes clients
- 🔗 Avances fournisseurs

#### Interface
- ⬜ Vue liste mouvements non rapprochés
- ⬜ Drag & drop pour rapprocher
- ⬜ Split mouvement (rapprochement partiel)
- ⬜ Rapprochement multiple (1 virement = N factures)
- ⬜ Validation rapide (batch)

#### Catégorisation
- ⬜ Catégories automatiques
- ⬜ Règles par libellé
- ⬜ Affectation compte comptable
- ⬜ TVA déduite automatiquement

#### Écritures comptables
- 🔗 Génération écriture de lettrage
- ⬜ Lettrage automatique
- ⬜ Écart de règlement (escompte, frais)
- ⬜ Export pour comptable

#### Alertes
- ⬜ Mouvements non rapprochés > 7j
- ⬜ Écarts de montant
- ⬜ Doublons détectés
- ⬜ Factures payées en retard

---

## BI / Tableaux de bord (`bi.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Tableaux de bord
- ⬜ Dashboard dirigeant (vue globale)
- ⬜ Dashboard commercial (pipeline, CA)
- ⬜ Dashboard financier (trésorerie, DSO)
- ⬜ Dashboard opérationnel (interventions, stock)
- ⬜ Dashboard RH (effectifs, absences)
- ⬜ Dashboards personnalisés

#### Widgets
- ⬜ KPIs avec évolution
- ⬜ Graphiques (barres, lignes, camemberts)
- ⬜ Tableaux de données
- ⬜ Listes top/flop
- ⬜ Jauges et indicateurs
- ⬜ Cartes géographiques

#### Données
- ⬜ Toutes les entités de l'ERP
- ⬜ Agrégations (somme, moyenne, compte)
- ⬜ Filtres dynamiques
- ⬜ Périodes comparatives (N vs N-1)
- ⬜ Drill-down (détail par clic)

#### Création
- ⬜ Builder graphique (no-code)
- ⬜ Glisser-déposer widgets
- ⬜ Redimensionnement
- ⬜ Formules calculées
- ⬜ Conditions de couleur

#### Partage
- ⬜ Rapports PDF automatiques
- ⬜ Envoi email programmé
- ⬜ Export Excel
- ⬜ Liens de partage (lecture seule)
- ⬜ Intégration TV/écran

---

## Budget (`budget.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Création budget
- ⬜ Budget annuel
- ⬜ Budget mensuel détaillé
- ⬜ Budget par département/projet
- ⬜ Budget par poste comptable
- ⬜ Budget par catégorie (recettes/dépenses)
- ⬜ Saisonnalité (répartition non linéaire)

#### Types de budget
- ⬜ Budget de fonctionnement
- ⬜ Budget d'investissement
- ⬜ Budget de trésorerie
- ⬜ Budget prévisionnel ventes

#### Suivi
- ⬜ Réalisé vs budget
- ⬜ Écarts (montant et %)
- ⬜ Alertes dépassement
- ⬜ Re-prévision (forecast)
- ⬜ Tendance fin d'année

#### Reporting
- ⬜ Tableau budget mensuel
- ⬜ Graphique réalisé vs prévu
- ⬜ Analyse des écarts
- ⬜ Export Excel
- ⬜ Comparaison N vs N-1

---

## Conformité (`conformite.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Checklist conformité
- ⬜ RGPD (protection données)
- ⬜ Facturation électronique (2026)
- ⬜ NF525 (caisses)
- ⬜ Anti-fraude TVA
- ⬜ Archivage légal
- ⬜ Droit du travail

#### Audit
- ⬜ Auto-diagnostic conformité
- ⬜ Score de conformité
- ⬜ Points à améliorer
- ⬜ Historique des contrôles
- ⬜ Preuves de conformité

#### Documents
- ⬜ Registre des traitements (RGPD)
- ⬜ Politique de confidentialité
- ⬜ Conditions générales
- ⬜ Attestations et certificats

#### Alertes
- ⬜ Échéances réglementaires
- ⬜ Nouvelles obligations
- ⬜ Contrôles à effectuer

---

## Copropriété / Syndic (`copropriete.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Gestion immeubles
- ⬜ Fiche immeuble (adresse, lots, tantièmes)
- ⬜ Lots (appartements, caves, parkings)
- ⬜ Copropriétaires
- ⬜ Locataires
- ⬜ Règlement de copropriété

#### Charges
- ⬜ Budget prévisionnel
- ⬜ Appels de fonds trimestriels
- ⬜ Répartition par tantièmes
- ⬜ Charges individuelles
- ⬜ Régularisation annuelle

#### Assemblées générales
- ⬜ Convocations
- ⬜ Ordre du jour
- ⬜ Feuille de présence
- ⬜ Procès-verbal
- ⬜ Résolutions et votes
- ⬜ Carnet d'entretien

#### Travaux
- ⬜ Gestion des travaux
- ⬜ Appel de fonds travaux
- ⬜ Suivi chantier
- ⬜ Réception travaux

#### Comptabilité syndic
- ⬜ Plan comptable copropriété
- ⬜ Clôture annuelle
- ⬜ Annexes comptables
- ⬜ Extranet copropriétaires

---

## Prévisions (`previsions.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Prévision de trésorerie
- ⬜ Solde actuel
- ⬜ Encaissements prévus (factures échues)
- ⬜ Décaissements prévus (factures fournisseurs)
- ⬜ Charges récurrentes (loyer, salaires)
- ⬜ TVA à payer
- ⬜ Projection 30/60/90 jours
- ⬜ Graphique évolution trésorerie

#### Prévision des ventes
- ⬜ Historique + tendance
- ⬜ Saisonnalité
- ⬜ Pipeline commercial pondéré
- ⬜ Abonnements récurrents
- ⬜ Projection CA

#### Prévision des charges
- ⬜ Charges fixes identifiées
- ⬜ Charges variables (% CA)
- ⬜ Échéancier fiscal/social
- ⬜ Investissements prévus

#### Scénarios
- ⬜ Scénario optimiste/pessimiste
- ⬜ Simulation what-if
- ⬜ Impact décisions (embauche, achat)
- ⬜ Comparaison scénarios

#### Alertes
- ⬜ Alerte trésorerie basse
- ⬜ Alerte pic de décaissement
- ⬜ Recommandations IA

---

## HACCP (`haccp.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Plan HACCP
- ⬜ Analyse des dangers
- ⬜ Points critiques (CCP)
- ⬜ Limites critiques
- ⬜ Procédures de surveillance
- ⬜ Actions correctives
- ⬜ Documentation

#### Relevés températures
- ⬜ Saisie manuelle
- ⬜ Sondes connectées (IoT)
- ⬜ Alertes dépassement
- ⬜ Historique complet
- ⬜ Graphiques de suivi

#### Traçabilité
- ⬜ Lots matières premières
- ⬜ DLC/DDM
- ⬜ Fournisseurs
- ⬜ Traçabilité amont/aval
- ⬜ Rappel produits

#### Contrôles
- ⬜ Checklist nettoyage
- ⬜ Checklist réception
- ⬜ Contrôles visuels
- ⬜ Analyses laboratoire
- ⬜ Non-conformités

#### Documentation
- ⬜ Plan de nettoyage
- ⬜ Fiches techniques produits
- ⬜ Attestations fournisseurs
- ⬜ Certificats sanitaires

---

## Base de connaissances (`base_connaissances.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Création de contenu
- ⬜ Articles (markdown/WYSIWYG)
- ⬜ Catégories hiérarchiques
- ⬜ Tags
- ⬜ Pièces jointes
- ⬜ Vidéos intégrées
- ⬜ Versioning articles

#### Organisation
- ⬜ Arborescence navigation
- ⬜ Articles connexes
- ⬜ Table des matières auto
- ⬜ Ordre personnalisable

#### Recherche
- ⬜ Recherche full-text
- ⬜ Suggestions pendant frappe
- ⬜ Filtres (catégorie, date, auteur)
- ⬜ Articles populaires

#### Collaboration
- ⬜ Multi-auteurs
- ⬜ Workflow publication (brouillon → review → publié)
- ⬜ Commentaires internes
- ⬜ Historique des modifications

#### Accès
- ⬜ Public (FAQ client)
- ⬜ Interne (équipe)
- ⬜ Par rôle
- ⬜ Portail client intégré

#### Feedback
- ⬜ "Cet article vous a-t-il aidé ?"
- ⬜ Commentaires utilisateurs
- ⬜ Analytics (vues, recherches)

---

## Gestion immobilière (`immobilier.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Parc immobilier
- ⬜ Biens (appartements, maisons, locaux)
- ⬜ Caractéristiques (surface, pièces, étage)
- ⬜ Photos et documents
- ⬜ Diagnostic (DPE, amiante, plomb)
- ⬜ Valeur et fiscalité

#### Locataires
- ⬜ Fiche locataire
- ⬜ Bail (type, dates, loyer)
- ⬜ Garants
- ⬜ État des lieux (entrée/sortie)
- ⬜ Caution

#### Gestion locative
- ⬜ Quittances de loyer
- ⬜ Appel de loyer automatique
- ⬜ Révision de loyer (IRL)
- ⬜ Charges locatives
- ⬜ Régularisation annuelle

#### Encaissements
- ⬜ Suivi paiements loyers
- ⬜ Relances impayés
- ⬜ Prélèvement automatique
- ⬜ Historique des paiements

#### Travaux et entretien
- ⬜ Demandes locataires
- ⬜ Interventions programmées
- ⬜ Fournisseurs/artisans
- ⬜ Coûts par bien

#### Comptabilité
- ⬜ Revenus fonciers
- ⬜ Charges déductibles
- ⬜ Déclaration fiscale (2044)
- ⬜ Rentabilité par bien

---

## Contrôle qualité (`qualite.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Contrôles
- ⬜ Plans de contrôle
- ⬜ Points de contrôle
- ⬜ Critères d'acceptation
- ⬜ Fréquence contrôles
- ⬜ Échantillonnage

#### Exécution
- ⬜ Saisie résultats contrôle
- ⬜ Mesures (valeurs numériques)
- ⬜ Conformité (OK/NOK)
- ⬜ Photos des défauts
- ⬜ Signature contrôleur

#### Non-conformités
- ⬜ Déclaration NC
- ⬜ Classification (critique, majeure, mineure)
- ⬜ Actions immédiates
- ⬜ Analyse causes (5 pourquoi, Ishikawa)
- ⬜ Actions correctives/préventives
- ⬜ Vérification efficacité

#### Traçabilité
- ⬜ Historique par produit/lot
- ⬜ Certificats de conformité
- ⬜ Libération lots
- ⬜ Blocage/déblocage

#### Reporting
- ⬜ Taux de conformité
- ⬜ Pareto des défauts
- ⬜ Évolution qualité
- ⬜ Coût de non-qualité

---

## Parrainage (`parrainage.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Programme
- ⬜ Règles de parrainage
- ⬜ Récompense parrain
- ⬜ Récompense filleul
- ⬜ Conditions d'éligibilité
- ⬜ Durée programme

#### Parrainage
- ⬜ Code parrain unique
- ⬜ Lien de parrainage
- ⬜ Partage réseaux sociaux
- ⬜ QR code

#### Suivi
- ⬜ Filleuls inscrits
- ⬜ Filleuls convertis (première commande)
- ⬜ Récompenses à verser
- ⬜ Récompenses versées

#### Récompenses
- ⬜ Crédit sur compte
- ⬜ Réduction sur prochaine facture
- ⬜ Virement bancaire
- ⬜ Cadeau physique

#### Gamification
- ⬜ Niveaux (bronze, argent, or)
- ⬜ Classement top parrains
- ⬜ Badges et récompenses spéciales

---

## Location de matériel (`location_materiel.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Catalogue location
- ⬜ Fiches matériels
- ⬜ Photos et caractéristiques
- ⬜ Tarifs (jour, semaine, mois)
- ⬜ Caution requise
- ⬜ Disponibilité temps réel

#### Réservations
- ⬜ Calendrier de réservation
- ⬜ Demande de réservation
- ⬜ Confirmation / Refus
- ⬜ Check-in / Check-out
- ⬜ État des lieux (entrée/sortie)

#### Contrats
- ⬜ Contrat de location
- ⬜ Conditions générales
- ⬜ Assurance
- ⬜ Signature électronique

#### Facturation
- ⬜ Facturation automatique
- ⬜ Facturation à la durée réelle
- ⬜ Pénalités retard
- ⬜ Dommages et réparations
- ⬜ Caution encaissée/restituée

#### Planning
- ⬜ Vue planning global
- ⬜ Disponibilité par matériel
- ⬜ Alertes maintenance préventive
- ⬜ Entretien entre locations

---

## Ressources (`ressources.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Types de ressources
- ⬜ Humaines (employés, intérimaires)
- ⬜ Matérielles (véhicules, outils)
- ⬜ Locaux (salles, bureaux)
- ⬜ Virtuelles (licences logiciels)

#### Capacité
- ⬜ Capacité par ressource
- ⬜ Unité (heures, jours, quantité)
- ⬜ Calendrier de disponibilité
- ⬜ Périodes d'indisponibilité

#### Planification
- ⬜ Affectation aux projets/tâches
- ⬜ Vue charge par ressource
- ⬜ Surcharge / sous-charge
- ⬜ Optimisation automatique
- ⬜ Conflits de réservation

#### Coûts
- ⬜ Coût horaire/journalier
- ⬜ Coût par projet
- ⬜ Budget ressources
- ⬜ Réel vs prévu

---

## Appels d'offres / RFQ (`appels_offres.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Réponse aux appels d'offres
- ⬜ Veille appels d'offres
- ⬜ Fiche AO (client, objet, délai)
- ⬜ Documents requis
- ⬜ Checklist de réponse
- ⬜ Décision go/no-go

#### Constitution dossier
- ⬜ Documents administratifs
- ⬜ Références et attestations
- ⬜ Mémoire technique
- ⬜ Offre financière (BPU, DQE)
- ⬜ Planning prévisionnel

#### Collaboration
- ⬜ Équipe projet AO
- ⬜ Répartition tâches
- ⬜ Revue avant soumission
- ⬜ Historique versions

#### Soumission
- ⬜ Génération dossier complet
- ⬜ Envoi dématérialisé
- ⬜ Accusé de réception

#### Suivi
- ⬜ Statut (en cours, soumis, gagné, perdu)
- ⬜ Résultat et feedback
- ⬜ Analyse win/loss
- ⬜ Statistiques par type d'AO

---

## Gestion des risques (`risques.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Identification
- ⬜ Registre des risques
- ⬜ Catégories (financier, opérationnel, juridique, etc.)
- ⬜ Description du risque
- ⬜ Causes et conséquences

#### Évaluation
- ⬜ Probabilité (1-5)
- ⬜ Impact (1-5)
- ⬜ Criticité (matrice)
- ⬜ Risque brut / résiduel
- ⬜ Cartographie des risques

#### Traitement
- ⬜ Stratégie (éviter, réduire, transférer, accepter)
- ⬜ Actions de mitigation
- ⬜ Responsable
- ⬜ Délai
- ⬜ Coût des actions

#### Suivi
- ⬜ Statut des actions
- ⬜ Réévaluation périodique
- ⬜ Indicateurs de risque
- ⬜ Historique des incidents

#### Reporting
- ⬜ Dashboard risques
- ⬜ Top 10 risques
- ⬜ Évolution dans le temps
- ⬜ Rapport comité des risques

---

## Expéditions (`expeditions.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Préparation
- ⬜ Liste des commandes à expédier
- ⬜ Bon de préparation
- ⬜ Picking (prélèvement stock)
- ⬜ Colisage (répartition en colis)
- ⬜ Pesée et dimensions

#### Transporteurs
- ⬜ Multi-transporteurs (Colissimo, Chronopost, DHL, UPS, etc.)
- ⬜ Tarifs par transporteur
- ⬜ Choix automatique (meilleur prix/délai)
- ⬜ Contrats négociés

#### Étiquetage
- ⬜ Génération étiquettes transport
- ⬜ Bordereau d'expédition
- ⬜ Documents douaniers (export)
- ⬜ Impression en masse

#### Tracking
- ⬜ Numéro de suivi
- ⬜ Suivi temps réel (webhook transporteur)
- ⬜ Notification client (expédié, en livraison, livré)
- ⬜ Preuve de livraison

#### Retours
- ⬜ Demande de retour
- ⬜ Étiquette retour
- ⬜ Réception retour
- ⬜ Remboursement ou échange

---

## Réseaux sociaux (`reseaux_sociaux.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Connexion comptes
- ⬜ Facebook / Instagram
- ⬜ LinkedIn
- ⬜ X (Twitter)
- ⬜ Google Business Profile

#### Publication
- ⬜ Création de posts
- ⬜ Planification
- ⬜ Multi-plateformes
- ⬜ Images et vidéos
- ⬜ Hashtags suggérés

#### Modération
- ⬜ Inbox unifié (commentaires, messages)
- ⬜ Réponses depuis l'ERP
- ⬜ Assignation à l'équipe
- ⬜ Historique par contact

#### Analytics
- ⬜ Statistiques par plateforme
- ⬜ Engagement (likes, partages, commentaires)
- ⬜ Croissance followers
- ⬜ Meilleurs posts

#### Leads
- 🔗 Création lead depuis message/commentaire
- ⬜ Suivi conversions

---

## Sondages et enquêtes (`sondages.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Création
- ⬜ Types de questions (choix unique, multiple, texte, échelle, NPS)
- ⬜ Logique conditionnelle (branching)
- ⬜ Pages et sections
- ⬜ Personnalisation visuelle
- ⬜ Preview

#### Distribution
- ⬜ Lien public
- ⬜ QR code
- ⬜ Envoi par email
- ⬜ Envoi par SMS
- ⬜ Intégration site web

#### Collecte
- ⬜ Réponses en temps réel
- ⬜ Anonyme ou identifié
- ⬜ Date limite
- ⬜ Limitation réponses

#### Analyse
- ⬜ Tableau de résultats
- ⬜ Graphiques automatiques
- ⬜ Export Excel/CSV
- ⬜ Filtres et croisements
- ⬜ NPS calculé

#### Cas d'usage
- ⬜ Satisfaction client (post-intervention)
- ⬜ Feedback produit
- ⬜ Enquête employés
- ⬜ Étude de marché

---

## Garanties (`garanties.yml`) ⚠️ MODULE À CRÉER

### Fonctionnalités à implémenter

#### Définition garanties
- ⬜ Types (constructeur, commerciale, étendue)
- ⬜ Durée par produit
- ⬜ Conditions d'application
- ⬜ Exclusions

#### Suivi
- ⬜ Garantie par équipement vendu
- ⬜ Date de début/fin
- ⬜ Alerte fin de garantie
- ⬜ Historique des interventions sous garantie

#### Réclamations
- ⬜ Demande de prise en charge
- ⬜ Vérification éligibilité
- ⬜ Intervention SAV
- ⬜ Remplacement / remboursement
- ⬜ Suivi dossier

#### Fournisseur
- ⬜ Demande garantie fournisseur
- ⬜ Retour produit
- ⬜ Avoir fournisseur
- ⬜ Historique retours

#### Reporting
- ⬜ Coût des garanties
- ⬜ Taux de retour par produit
- ⬜ Causes de panne fréquentes

---

# RÉSUMÉ FINAL

## Modules fusionnés (nettoyage redondances)

| Supprimé | Fusionné dans | Raison |
|----------|---------------|--------|
| Funnel de vente | Opportunités | Même fonctionnalité (pipeline commercial) |
| Documents | GED | GED = Documents + OCR + archivage légal |
| Emailing | Campagnes marketing | Campagnes = multi-canal (email, SMS, etc.) |

## Statistiques complètes

| Catégorie | Modules | Fonctionnalités |
|-----------|---------|-----------------|
| Monétisation | 3 | ~40 |
| Commercial | 14 | ~200 |
| Achats | 4 | ~40 |
| Inventaire | 7 | ~80 |
| Comptabilité | 8 | ~100 |
| RH | 5 | ~80 |
| Projets | 4 | ~70 |
| Services/SAV | 7 | ~100 |
| BTP | 4 | ~50 |
| Flotte | 2 | ~30 |
| Médical | 2 | ~25 |
| Assurance | 2 | ~20 |
| Communication | 5 | ~80 |
| Système | 14 | ~100 |
| E-commerce | 2 | ~50 |
| BI / Reporting | 3 | ~50 |
| Immobilier | 2 | ~50 |
| Qualité / Conformité | 4 | ~60 |
| IA / Automatisation | 3 | ~50 |
| Mobile | 2 | ~30 |
| Onboarding | 1 | ~15 |
| **TOTAL** | **~103** | **~1400+** |

---

**Document de référence AZALPLUS - Phase d'identification des besoins**

*Dernière mise à jour : 2026-03-12*
