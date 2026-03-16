# Todolist Module Médical - Honoraires / CPAM / Mutuelles

## ✅ TERMINÉ (12/03/2026)

**Module consolidé créé:** `modules/medical.yml`

### Fonctionnalités implémentées

| Fonction | Statut | Description |
|----------|--------|-------------|
| ✅ FSE | FAIT | Numéro, type (FSE/DRE), nature assurance |
| ✅ Patient | FAIT | NIR, date naissance, rang, qualité |
| ✅ Carte Vitale | FAIT | Numéro, validité |
| ✅ Organisme AMO | FAIT | Nom, code régime/caisse/centre |
| ✅ Organisme AMC | FAIT | Mutuelle, n° adhérent, garantie |
| ✅ Praticien | FAIT | N° AM, spécialité, secteur conventionnel |
| ✅ Actes | FAIT | Liste actes, nomenclature NGAP/CCAM |
| ✅ Montants | FAIT | Total, honoraires, dépassement |
| ✅ Remboursement | FAIT | Base, taux, parts AMO/AMC, RAC |
| ✅ Tiers payant | FAIT | TP AMO/AMC, montants |
| ✅ Exonérations | FAIT | ALD, maternité, AT, CSS |
| ✅ Parcours soins | FAIT | Médecin traitant, accès direct |
| ✅ Télétransmission | FAIT | N° lot, fichier B2, date envoi |
| ✅ Retours NOEMIE | FAIT | ARL, RSP, montants payés |
| ✅ Rejets | FAIT | Code, motif, date |
| ✅ Paiement patient | FAIT | Mode, date, montant |
| ✅ Impayés | FAIT | Montant, relances, contentieux |
| ✅ Workflow | FAIT | BROUILLON → VALIDEE → ENVOYEE → ACCEPTEE → PAYEE |

### Actions disponibles
- `ajouter_acte`
- `calculer_montants`
- `valider_fse`
- `integrer_lot`
- `envoyer_teletransmission`
- `importer_retour_noemie`
- `rapprocher_paiement`
- `generer_relance`
- `imprimer_duplicata`

---

## Notes

Les anciens modules séparés (7 fichiers) ont été consolidés en un seul module `medical.yml`:
- ~~nomenclatures_medicales.yml~~
- ~~organismes_payeurs.yml~~
- ~~fse.yml~~
- ~~tiers_payant.yml~~
- ~~teletransmission.yml~~
- ~~conventions_praticiens.yml~~
- ~~impayes_medicaux.yml~~
