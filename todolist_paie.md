# Todolist Module Paie - Gestion des salaires & DSN

## ✅ TERMINÉ (12/03/2026)

**Module consolidé créé:** `modules/paie.yml`

### Fonctionnalités implémentées

| Fonction | Statut | Description |
|----------|--------|-------------|
| ✅ Bulletin de paie | FAIT | Numéro, période, employé, dates |
| ✅ Données employeur | FAIT | SIRET, raison sociale, APE, convention |
| ✅ Données salarié | FAIT | Matricule, N° SS, poste, catégorie |
| ✅ Temps de travail | FAIT | Horaire, heures sup 25%/50%, complémentaires |
| ✅ Rémunération | FAIT | Salaire base, primes (ancienneté, 13ème, objectifs) |
| ✅ Indemnités | FAIT | Transport, repas, TR, km, avantages nature |
| ✅ Absences | FAIT | Type, retenue, IJSS, subrogation |
| ✅ Cotisations salariales | FAIT | Maladie, vieillesse, retraite, CSG/CRDS |
| ✅ Cotisations patronales | FAIT | Maladie, AF, AT, retraite, formation |
| ✅ Réductions | FAIT | Fillon, exo heures sup |
| ✅ Net et PAS | FAIT | Net avant impôt, taux PAS, net à payer |
| ✅ Retenues | FAIT | Acomptes, avances, saisies |
| ✅ Cumuls annuels | FAIT | Brut, net imposable, PAS, heures |
| ✅ Congés | FAIT | CP N-1, CP N, RTT (acquis/pris/solde) |
| ✅ DSN | FAIT | Intégration, type, période, statut |
| ✅ Workflow | FAIT | BROUILLON → CALCULE → VALIDE → PAYE → ARCHIVE |

### Actions disponibles
- `calculer_bulletin`
- `generer_pdf`
- `envoyer_salarie`
- `exporter_dsn`
- `generer_virement_sepa`
- `calculer_cotisations`
- `appliquer_convention`

---

## Notes

Les anciens modules séparés (17 fichiers) ont été consolidés en un seul module `paie.yml` comprenant toutes les fonctionnalités:
- ~~parametres_paie.yml~~
- ~~conventions_collectives.yml~~
- ~~rubriques_paie.yml~~
- ~~cotisations.yml~~
- ~~plan_comptable_paie.yml~~
- ~~primes.yml~~
- ~~elements_variables.yml~~
- ~~bulletins_paie.yml~~
- ~~lignes_bulletin.yml~~
- ~~dsn.yml~~
- ~~dsn_evenements.yml~~
- ~~acomptes.yml~~
- ~~satd.yml~~
- ~~baremes_saisie.yml~~
- ~~absences_paie.yml~~
- ~~solde_tout_compte.yml~~
- ~~etats_paie.yml~~
