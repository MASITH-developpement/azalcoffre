# Todolist Signature Électronique

## ✅ TERMINÉ (12/03/2026)

**Module consolidé créé:** `modules/signature_electronique.yml`

### Fonctionnalités implémentées

| Fonction | Statut | Description |
|----------|--------|-------------|
| ✅ Documents | FAIT | Devis, contrats, mandats SEPA, NDA |
| ✅ Signataires | FAIT | Multi-signataires, ordre séquentiel/parallèle |
| ✅ Authentification | FAIT | Email, SMS, OTP |
| ✅ Niveaux eIDAS | FAIT | Simple, avancée, qualifiée |
| ✅ Certificats | FAIT | X.509, horodatage TSA |
| ✅ Preuve | FAIT | Dossier preuve, journal audit |
| ✅ Rappels | FAIT | Automatiques, paramétrable |
| ✅ Annulation/Refus | FAIT | Motifs, dates |
| ✅ Providers | FAIT | Interne, Yousign, DocuSign, Universign |
| ✅ Archivage | FAIT | Coffre-fort numérique, conservation |
| ✅ Workflow | FAIT | BROUILLON → EN_ATTENTE → SIGNE |

### Actions disponibles
- `envoyer_signature`
- `renvoyer_invitation`
- `verifier_signature`
- `telecharger_preuve`
- `archiver_document`
- `annuler_demande`

### Valeur juridique
- **Simple** : Valeur probante (acceptation click)
- **Avancée** : Identification signataire + intégrité
- **Qualifiée** : Certificat qualifié (équivalent manuscrit)
