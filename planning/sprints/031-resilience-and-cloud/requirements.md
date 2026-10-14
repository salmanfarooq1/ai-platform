# Sprint 031: Resilience and cloud. Requirements

Platform (Kernel). A real deployment survives a failure within stated targets, keeps data encrypted at rest under keys the client can own, keeps secrets in a manager, and runs on more than one cloud from the same core. This is a two-part sprint: part a covers items 1–3, part b covers items 4–6.

Source: new scope (enterprise-gaps-how and cloud-terraform-portability research notes, bundle A). It builds on the 015 POC lifecycle.

## Scope
1. **Targets and drills.**
   - Stated RPO and RTO per deployment shape. The proposed targets are RPO 0 and RTO under 2 minutes for the database on a managed zone-redundant service or CloudNativePG with synchronous replication, and RPO under 24 hours for the single-VM POC shape.
   - These are targets proven by a drill, not promises (owner question Q-04).
   - A failover drill script measures the real numbers and stores them as evidence. A restore drill covers the database, the DuckLake catalog, the object store and the keys as one set. The catalog and the files are backed up in an order that never leaves the catalog pointing at missing files.
2. **HA reference topology.**
   - Managed Postgres with zone-redundant HA, or CloudNativePG on Kubernetes as the portable path, or Patroni on VMs.
   - Two or more stateless API replicas. Workers claim jobs with leases (already true) and are tested under a killed worker.
   - The DuckLake catalog is a normal HA Postgres database.
3. **Encryption at rest and keys.**
   - Volume and managed-database encryption by default. Object store server-side encryption with KMS keys.
   - A `KeyManager` port for data keys, with adapters for OpenBao Transit, AWS, Azure and GCP KMS, and PKCS#11. The 017 signing-key port uses it where a cloud KMS is chosen.
   - Envelope encryption for app secrets.
   - Community Postgres has no TDE. `pg_tde` needs a patched server and is documented as an option only, after its licence is checked.
4. **Secrets manager.**
   - OpenBao (MPL-2.0) per deployment, synced to pods by External Secrets Operator, with short TTLs and reload.
   - Small clients may use the cloud's secret store through the same port.
   - The 021 connection secrets move here from files.
   - Break-glass: a sealed root token with two-person unseal, audited.
5. **More clouds and Kubernetes.**
   - The 015 module interface gets its second and third cloud modules (the first is the owner's choice, Q-03).
   - Managed equivalents per cloud are recorded in a table: Postgres with pgvector (version parity checked against our pin), cache (Azure has no managed Valkey, so we use the pgvector cache adapter or Valkey in the cluster), object storage, Kafka, KMS, secrets and model endpoints.
   - RLS and our migrations are tested on each managed Postgres.
   - One Helm chart (`deploy/helm/gap`) with values per cloud. Plain HCL, run by OpenTofu and tested with Terraform too.
6. **Upgrades.** The 015 "upgrade from previous release" job also runs against the Helm install and a managed database. ADR-0034.

## Out of scope
- Multi-region active-active. FIPS 140-3 crypto.
- A SOC 2 report (needs an auditor). The trust package is 032.
- Cloud-specific services that have no counterpart on the other clouds.

## Nav placement
- Platform > Deployment: the shape, the last drill results (RPO and RTO measured), key and secret status.

## Questions this sprint closes
- Proposes defaults for owner questions Q-04 (targets proven by drill) and Q-05 (VMs for POCs, Helm on managed Kubernetes for production).

## Open questions for the owner
- Q-03 must be answered by the start of this sprint if it was not answered for 015, because it decides which managed HA and KMS adapters are built first.
