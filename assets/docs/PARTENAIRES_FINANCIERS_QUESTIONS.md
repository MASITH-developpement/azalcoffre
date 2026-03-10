# AZALPLUS — Questions Partenaires Financiers

**Contexte à présenter :**

> AZALPLUS est un ERP gratuit pour TPE. Le modèle économique repose sur :
> 1. Compte bancaire intégré (via BaaS) avec frais standards
> 2. Services financiers (factoring, prêt) via partenaires
> 3. Commission : 2€ par transaction de remboursement transitant par le compte
>
> Les fonds doivent transiter par le compte bancaire AZALPLUS du client.
> Nous fournissons les données ERP (factures, CA, historique) pour faciliter le scoring.

---

## PARTIE 1 — BaaS (Swan, Treezor)

### 1.1 Modèle commercial

- Quel est le modèle de partage de revenus ?
  - Frais de tenue de compte
  - Interchange carte
  - Virements / prélèvements

- Puis-je définir ma propre grille tarifaire client ?
  - Exemple : facturer 12€/mois au lieu de 9€

- Puis-je ajouter des frais custom sur certaines opérations ?
  - Exemple : 2€ sur chaque virement entrant tagué "remboursement prêt"

- Y a-t-il un minimum de comptes ou de volume requis ?

### 1.2 Technique / API

- Quels webhooks sont disponibles ?
  - Transaction entrante / sortante
  - Statut de virement
  - Solde insuffisant

- Puis-je déclencher un prélèvement automatique sur le compte client ?
  - Cas : détecter une mensualité entrante → prélever 2€ de frais

- Puis-je taguer / catégoriser les transactions côté API ?
  - Pour identifier : "facture X", "mensualité prêt Y"

- Latence des webhooks ? Temps réel ou batch ?

- Y a-t-il une sandbox pour tester ?

### 1.3 Intégration prêt / factoring externe

- Avez-vous des partenaires crédit/factoring déjà intégrés ?

- Si j'intègre un partenaire prêt externe (Defacto, October) :
  - Les fonds peuvent-ils arriver directement sur le compte client ?
  - Puis-je identifier automatiquement les remboursements ?

- Puis-je bloquer / réserver une somme sur le compte ?
  - Pour garantir un remboursement

### 1.4 Conformité / KYC

- Qui gère le KYC ? Vous ou moi ?

- Quel parcours pour onboarder une TPE ?
  - Documents requis
  - Délai moyen d'ouverture

- Suis-je responsable en cas de fraude client ?

- Quid du RGPD sur les données bancaires ?

### 1.5 White-label / Marque

- Le client voit quelle marque ?
  - App bancaire : "AZALPLUS" ou "Swan" ?
  - RIB : quel nom apparaît ?
  - Carte bancaire : personnalisable ?

- Puis-je intégrer l'interface bancaire dans mon ERP ?
  - Iframe, SDK, API custom ?

### 1.6 Coûts

- Coûts de setup / intégration ?

- Coûts récurrents :
  - Par compte actif ?
  - Par transaction ?
  - Maintenance mensuelle ?

- Coût d'une carte bancaire (émission, remplacement) ?

- Y a-t-il des coûts cachés ? (compliance, support, etc.)

### 1.7 Délais et accompagnement

- Délai pour être en production ?

- Avez-vous une équipe pour accompagner l'intégration ?

- Exemples de clients avec un modèle similaire ?
  - ERP/SaaS + banking intégré

---

## PARTIE 2 — Factoring (Defacto, Finexkap)

### 2.1 Modèle partenariat

- Quel statut pour AZALPLUS ?
  - Apporteur d'affaires ?
  - Agent ?
  - Partenaire white-label ?

- Quelle commission pour l'apporteur ?
  - % du montant financé ?
  - Fixe par dossier ?

- Commission one-shot ou récurrente ?

- Y a-t-il un volume minimum requis ?

### 2.2 Technique / Intégration

- Avez-vous une API pour :
  - Soumettre une demande de financement ?
  - Récupérer le statut (accepté / refusé / en cours) ?
  - Recevoir les webhooks (déblocage fonds, paiement reçu) ?

- Puis-je pré-remplir la demande avec les données ERP ?
  - Factures, CA, historique paiements

- Le scoring peut-il utiliser mes données internes ?
  - Meilleur taux si je fournis l'historique client

- Délai moyen de réponse pour une demande TPE ?

- Y a-t-il une sandbox / environnement de test ?

### 2.3 Conditions factoring

- Quels types de factures acceptés ?
  - B2B uniquement ?
  - Montant minimum / maximum ?
  - Délai de paiement max ?

- Quel pourcentage de la facture est avancé ?
  - 80% ? 90% ? 100% ?

- Commission totale pour le client final ?
  - Pour vérifier la compétitivité

- Quid si le débiteur ne paie pas ?
  - Recours contre mon client ?
  - Assurance-crédit incluse ?

### 2.4 Flux financiers

- Où arrivent les fonds débloqués ?
  - Sur n'importe quel compte ?
  - Compatible avec un compte BaaS (Swan, Treezor) ?

- Quand le débiteur paie :
  - L'argent passe par vous ou directement chez le client ?
  - Puis-je être notifié ?

### 2.5 White-label / Marque

- Le client voit quelle marque ?
  - "Financement AZALPLUS" ou votre nom ?

- Puis-je intégrer le parcours dans mon interface ?
  - Iframe ? Redirection ? API full custom ?

- Les communications (emails, relances) sont en mon nom ?

### 2.6 Juridique / Risque

- Qui porte le risque crédit ? 100% vous ou partage ?

- Suis-je responsable si un client fournit de fausses données ?

- Quel contrat : apporteur d'affaires ou agent ?
  - Implications légales pour AZALPLUS ?

---

## PARTIE 3 — Prêt classique (October, Defacto)

### 3.1 Modèle partenariat

- Quel statut pour AZALPLUS ?
  - Apporteur d'affaires ?
  - Agent ?
  - Partenaire white-label ?

- Quelle commission pour l'apporteur ?
  - % du montant prêté ?
  - Fixe par dossier validé ?

- Commission one-shot ou sur la durée du prêt ?

- Y a-t-il un volume minimum requis ?

### 3.2 Technique / Intégration

- Avez-vous une API pour :
  - Soumettre une demande de prêt ?
  - Récupérer le statut ?
  - Recevoir les webhooks (déblocage, remboursement) ?

- Puis-je pré-remplir la demande avec les données ERP ?
  - CA, factures, trésorerie historique

- Le scoring peut-il utiliser mes données internes ?

- Délai moyen entre demande et déblocage des fonds ?

- Y a-t-il une sandbox ?

### 3.3 Conditions prêt TPE

- Quels types de prêts disponibles ?
  - Montants : min / max ?
  - Durées : 3 mois à 36 mois ?
  - Taux indicatifs ?

- Critères d'éligibilité TPE ?
  - Ancienneté minimum ?
  - CA minimum ?
  - Secteurs exclus ?

- Garanties demandées ?
  - Caution personnelle ?
  - Nantissement ?

### 3.4 Flux financiers (IMPORTANT)

- Où arrivent les fonds débloqués ?
  - Sur n'importe quel compte ?
  - Compatible avec un compte BaaS (Swan, Treezor) ?

- Comment sont prélevées les mensualités ?
  - Prélèvement SEPA ?
  - Depuis le compte de mon choix ?

- **Puis-je être notifié de chaque remboursement ?**
  - Webhook avec montant et date ?
  - Pour prélever mes 2€ de frais sur le compte client

- Le remboursement peut-il transiter par le compte AZALPLUS du client ?
  - Flux : Compte client AZALPLUS → Vous

### 3.5 White-label / Marque

- Le client voit quelle marque ?
  - "Prêt AZALPLUS" ou votre nom ?

- Puis-je intégrer le parcours dans mon interface ?

- Les communications (échéancier, relances) sont en mon nom ?

### 3.6 Juridique / Risque

- Qui porte le risque crédit ? 100% vous ?

- Suis-je responsable si un client fournit de fausses données ?

- Quel contrat pour AZALPLUS ?

---

## PARTIE 4 — Revenue-Based Financing (Silvr, Karmen, Unlimitd)

### 4.1 Modèle partenariat

- Quel statut pour AZALPLUS ?
  - Apporteur d'affaires ?
  - Partenaire data ?

- Quelle commission pour l'apporteur ?
  - % du montant financé ?
  - % des frais facturés au client ?

- Y a-t-il un volume minimum requis ?

### 4.2 Fonctionnement RBF

- Comment fonctionne le remboursement ?
  - % fixe du CA mensuel ?
  - Fréquence : quotidien, hebdo, mensuel ?

- Comment détectez-vous le CA du client ?
  - Connexion bancaire (agrégateur) ?
  - Connexion Stripe / PSP ?
  - **Puis-je fournir les données directement via API ?**

- Montant max de financement pour une TPE ?

- Frais totaux pour le client (fee multiplier) ?
  - Exemple : avance 50K€, rembourse 55K€ = 1.1x

### 4.3 Technique / Intégration

- Avez-vous une API pour :
  - Soumettre une demande ?
  - Suivre le remboursement en cours ?
  - Recevoir des webhooks (prélèvement effectué) ?

- Puis-je pré-qualifier les clients avec mes données ERP ?
  - CA, récurrence revenus, historique factures

- Y a-t-il une sandbox ?

### 4.4 Flux financiers (IMPORTANT)

- Où arrivent les fonds débloqués ?
  - Compatible avec un compte BaaS ?

- Comment prélevez-vous les remboursements ?
  - Connexion directe au compte ?
  - Prélèvement SEPA ?
  - **Le prélèvement peut-il passer par le compte AZALPLUS (BaaS) ?**

- **Puis-je être notifié de chaque prélèvement ?**
  - Pour facturer mes frais (2€ ou % du prélèvement)

### 4.5 Mon modèle de frais

Le modèle "2€ par mensualité fixe" ne s'applique pas au RBF.

Options envisagées :
- 2€ par prélèvement (peu importe le montant)
- 0.5% du montant prélevé
- Frais fixe mensuel tant que le financement est actif

**Quelle option est compatible avec votre fonctionnement ?**

### 4.6 White-label / Marque

- Le client voit quelle marque ?

- Puis-je intégrer le parcours dans mon ERP ?

### 4.7 Juridique / Risque

- Qui porte le risque ? 100% vous ?

- Quid si le CA du client chute fortement ?

---

## RÉCAPITULATIF PARTENAIRES

| Partenaire | Type | Site | Priorité |
|------------|------|------|----------|
| **Swan** | BaaS | swan.io | 1 |
| **Treezor** | BaaS | treezor.com | 2 |
| **Defacto** | Factoring + Prêt | defacto.io | 1 |
| **Finexkap** | Factoring | finexkap.com | 2 |
| **October** | Prêt PME | october.eu | 2 |
| **Silvr** | RBF | silvr.co | 3 |
| **Karmen** | RBF | karmen.io | 3 |
| **Unlimitd** | RBF | unlimitd.com | 3 |

**Recommandation : commencer par Swan + Defacto** (couvrent BaaS + factoring + prêt, API modernes, orientés startups).

---

## CHECKLIST AVANT RDV

- [ ] Préparer démo AZALPLUS (parcours client type)
- [ ] Chiffres cibles : nombre de TPE visées à 1 an
- [ ] Volume estimé : CA moyen des TPE, factures/mois
- [ ] Structure juridique AZALPLUS (SAS, etc.)
- [ ] Questions spécifiques notées

---

*Document généré pour AZALPLUS — Mars 2026*
