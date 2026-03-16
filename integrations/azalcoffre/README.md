# Intégration AZALCOFFRE

Connecteur entre AZALPLUS (ERP No-Code) et AZALCOFFRE (Coffre-fort numérique NF Z42-013).

## Architecture

```
┌─────────────────────┐         ┌─────────────────────┐
│     AZALPLUS        │   API   │     AZALCOFFRE      │
│  (ERP No-Code)      │◄───────►│  (Coffre-fort)      │
│                     │  REST   │                     │
│  PostgreSQL #1      │         │  PostgreSQL #2      │
│  - Factures (méta)  │         │  - Documents (PDF)  │
│  - Clients          │         │  - Hashes SHA-512   │
│  - Produits         │         │  - Horodatages TSA  │
└─────────────────────┘         └─────────────────────┘
```

## Conformité NF Z42-013

| Exigence | Solution AZALCOFFRE |
|----------|---------------------|
| Intégrité | SHA-512 sur chaque document |
| Authenticité | Signature eIDAS (simple/avancée/qualifiée) |
| Horodatage | TSA RFC 3161 (freetsa.org ou serveur interne) |
| Traçabilité | Audit trail chaîné (previous_hash → entry_hash) |
| Pérennité | Conservation 10 ans minimum (factures) |
| Réversibilité | Export PDF + XML + métadonnées |

## Configuration

Variables d'environnement :

```bash
AZALCOFFRE_URL=http://localhost:8001
AZALCOFFRE_API_KEY=sk_live_xxx
AZALCOFFRE_TIMEOUT=30
AZALCOFFRE_VERIFY_SSL=true
```

## Usage

### Archivage automatique (recommandé)

L'archivage est automatique lors de l'envoi/réception de factures via `FacturationService` :

```python
from integrations.facturx import FacturationService, TenantConfig

config = TenantConfig(
    tenant_id=tenant_id,
    siret="12345678901234",
    tva_intra="FR12345678901",
    raison_sociale="Ma Société",
    adresse_ligne1="123 rue Example",
    code_postal="75001",
    ville="Paris",
    archivage_actif=True,  # Active l'archivage automatique
)

service = FacturationService(config)

# Envoi facture → archivage automatique
result = service.send_invoice(
    pdf_content=pdf_bytes,
    invoice_data=invoice_data,
    siret_destinataire="98765432109876",
    invoice_id=facture.id,  # UUID de la facture
)

# Vérifier l'archivage
if result.archive_info and result.archive_info.archived:
    print(f"Archivé: {result.archive_info.archive_id}")
    print(f"Hash: {result.archive_info.hash_sha512}")
    print(f"Expire: {result.archive_info.expires_at}")
```

### Archivage manuel

```python
from integrations.azalcoffre import ArchiveSync, ArchiveRequest, DocumentType

sync = ArchiveSync()

# Archiver une facture émise
result = sync.archive_invoice_sent(
    tenant_id=tenant_id,
    invoice_id=invoice_id,
    invoice_number="FA-2026-001",
    invoice_date=date(2026, 3, 15),
    pdf_content=pdf_bytes,
    seller_name="Ma Société",
    seller_siret="12345678901234",
    buyer_name="Client SA",
    buyer_siret="98765432109876",
    amount_ht=Decimal("1000.00"),
    amount_ttc=Decimal("1200.00"),
)

if result.success:
    print(f"Archive ID: {result.archive_id}")
```

### Consultation et vérification

```python
# Récupérer infos d'archivage
archive_info = service.get_archive_info(invoice_id=facture.id)

if archive_info:
    print(f"Archivé: {archive_info.archived}")
    print(f"Hash SHA-512: {archive_info.hash_sha512}")
    print(f"Horodatage TSA: {archive_info.tsa_timestamp}")
    print(f"Expire le: {archive_info.expires_at}")

# Télécharger l'original
pdf_original = service.download_archived_invoice(archive_info.archive_id)

# Générer certificat d'intégrité (pour contrôle fiscal)
certificat_pdf = service.get_integrity_certificate(archive_info.archive_id)
```

## Durées de conservation

| Type document | Durée | Base légale |
|---------------|-------|-------------|
| Factures | 10 ans | Code de commerce L123-22 |
| Avoirs | 10 ans | Code de commerce L123-22 |
| Bulletins de paie | 50 ans | Droit du travail |
| Contrats | 5 ans après expiration | Code civil |

## Portails d'accès

Les factures archivées sont accessibles depuis :

1. **AZALPLUS** : Vue intégrée dans la fiche facture
2. **AZALCOFFRE Portail Admin** : Gestion complète des archives
3. **AZALCOFFRE Portail Client** : Accès client à ses documents

## Backup programmé

AZALCOFFRE effectue des sauvegardes automatiques :

- **Quotidien** : Sauvegarde incrémentale chiffrée (AES-256)
- **Hebdomadaire** : Sauvegarde complète
- **Stockage** : Distant (S3/GCS) + local

Voir `azalcoffre/moteur/backup.py` pour la configuration.
