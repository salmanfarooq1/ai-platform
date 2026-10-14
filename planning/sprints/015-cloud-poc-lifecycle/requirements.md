# Sprint 015: Cloud POC lifecycle. Requirements

Platform pillar, infra and packaging, Kernel. The stack starts, backs up and stops on a cloud VM from one command, and leaves almost nothing behind.

Source: new scope (cloud-terraform-portability research note, owner direction of 2026-10-11). No old pack.

## Scope
1. **Infrastructure as code with OpenTofu.**
   - Plain HCL, run with OpenTofu (MPL-2.0). Terraform CLI is not a requirement (BSL). Layout: `infra/terraform/interface.md`, `modules/<name>/`, `stacks/<name>-<env>/`.
   - The interface is a documented contract of inputs and outputs: network, VM size, disk, bucket, backup bucket, DNS name, SSH key, expiry tag, and outputs for address and bucket names. One module per cloud. No single module that switches cloud by a variable.
   - The first module is a generic VM module that any VM provider can satisfy. The first real cloud is an open question (see the end). Candidates: GCP, AWS, Hetzner.
   - CI runs `tofu fmt -check` and `tofu validate` on every module. A plan against a mock or local provider proves the interface outputs.
2. **Compose bundle on one VM first.**
   - `deploy/compose/` holds the compose file with every image pinned by GHCR digest (`ghcr.io/OWNER/IMAGE@sha256:...`). A release job publishes the images and the bundle.
   - A wheelhouse (`poetry export`, `pip wheel`, `pip install --no-index --find-links`) bakes Python dependencies into the image. The image digest is the lock.
   - Only the web edge is public, over TLS. Every other port stays on localhost (011). Access is by SSH key. Secrets are generated on the VM and never go into git, state or logs.
   - A small VM runs `core` and `lake` with the fake model or a hosted model (013). The local model profile needs about 12 GB, and the size table says so.
3. **The `poc` commands** (`scripts/poc`, one entry point).
   - `poc up <stack>`: apply, install the bundle, restore the latest backup if one exists, wait for health.
   - `poc seed`: load the reference company (014). `poc demo`: run the M0 showcase script and write evidence.
   - `poc backup`: `pg_dump -Fc` of every platform database, the object store and the keys, into the backup bucket with restic and rclone. The set grows as databases arrive: `lakehouse` is added by 021 and 022, which pause writes first.
   - `poc down`: back up, destroy compute and disks, keep the bucket and the registry. A leak check lists anything still billed.
4. **Restore test.**
   - A CI job and a script: seed, back up, down, up, restore. Row counts match, the receipt chain verifies, and the smoke tests pass.
   - The restore drill runs on a local Compose host in CI. The real cloud run is a manual step in `scripts/verify/poc.sh` with its output saved as evidence.
5. **Upgrade from the previous release.**
   - A CI job installs the previous release bundle, seeds it, upgrades to the current bundle, runs the migrations, and checks that old receipts still verify.
   - With no previous tag, it builds from the last merged sprint commit.
6. **Idle cost recorded.** After `poc down`, only storage remains. The Builder records what remains and the measured monthly cost in `evidence/idle-cost.md`. No amount is promised in the plan.
7. **ADR-0032:** cloud deployment and the POC lifecycle. M0 journey steps added to `scripts/showcase/m0.sh`: `poc up`, the model deny, modules off, `poc backup`, `poc down`, `poc up` again.

## Out of scope
- Kubernetes, Helm and the second and third cloud (031). Managed Postgres, HA and failover (031).
- Encryption at rest, a key port and a secrets manager (031). Disk encryption is the provider default here.
- Client trial-account handling and the POC kit (a track outside the map).
- Container services such as ECS, Cloud Run and Container Apps. Rejected: three resource models for no gain.

## Nav placement
No UI change.

## Questions this sprint closes
- None from the open list. Cloud provider terms for trial accounts go to `planning/QUESTIONS.md`.

## Open questions for the owner
- Which cloud first: GCP, AWS or Hetzner? It decides the first real module. Default: the generic "any VM provider" module, so the sprint is not blocked.
- Is OpenTofu acceptable to every client, or must Terraform also work? The plan assumes plain HCL runs on both.
