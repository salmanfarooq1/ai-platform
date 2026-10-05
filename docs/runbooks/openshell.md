# Runbook: sandboxed agent runs with NVIDIA OpenShell

This is for `AGENT_RUNTIME=openshell` (Sprint 009, ADR-0009). Each agent run executes inside an OpenShell sandbox. The agent's only network route is the platform gateway, its only writable place is one work directory, and it has CPU, memory and wall-clock limits. The default runtime does not change: with `AGENT_RUNTIME` unset, nothing here is needed.

## Status
- **Verified in the Sprint 009 build container** against OpenShell **0.1.2** with the Docker driver, by `scripts/verify/openshell.sh` (output in `planning/sprints/009-sandboxed-agents/evidence/openshell-live.txt`). Acceptance A2 to A5 passed live, and so did the memory limit, the CPU limit and "cancel removes the sandbox".
- **Not verified:** the standard images from `ghcr.io` (the container could not pull them, see "Images"), Podman, Kubernetes, the microVM driver, WSL 2, macOS, any other OpenShell version, Landlock-denial events (OpenShell logs none), a real model (the check uses fakes), and more than one run at a time.
- Facts below come from three places, and each says which: the pinned release at tag `v0.1.2` (its docs, installer and checksums), the `openshell` 0.1.2 Python wheel, and what the live gateway did here.

## What is pinned, and the sources
Nothing is downloaded unpinned. Every item has a version and a SHA-256. A checksum was checked against the release's own checksum file (`openshell-checksums-sha256.txt`, and the sandbox and supervisor equivalents), which sits on the same host as the file, so it proves the download is intact, not who made it.

| Item | Version | SHA-256 | Source |
|---|---|---|---|
| Project | Apache-2.0 (`LICENSE` at the tag: `c4be3ace...20dd`) | | https://github.com/NVIDIA/OpenShell |
| Python SDK wheel `openshell-0.1.2-py3-none-any.whl` | 0.1.2 (PyPI, 2026-09-28) | `8c409da4f176d42418d92366fe201f47cceef2c0fa432bfbce2bf938649d59cf` | https://pypi.org/project/openshell/0.1.2/ |
| `cloudpickle-3.1.2-py3-none-any.whl` (the SDK imports it) | 3.1.2 | `9acb47f6afd73f60dc1df93bb801b472f05ff42fa6c84167d25cb206be1fbf4a` | PyPI |
| Debian package `openshell_0.1.2-1_amd64.deb` (CLI, gateway, prover) | 0.1.2-1 | `1f5416ea08f32fdc621f20a2cc0324298e60aba8bbe996459d9e3b44195f23df` | `https://github.com/NVIDIA/OpenShell/releases/download/v0.1.2/` |
| `openshell-sandbox-x86_64-unknown-linux-musl.tar.gz` | 0.1.2 | `f07ad7177f4c3ff7743f89531eda36bb784c56b45b166f49c5a51fbcfa5274a6` | same release |
| `openshell-supervisor-x86_64-unknown-linux-gnu.tar.gz` | 0.1.2 | `801d717f4211b4c24449b08a47ce5571ff623ce993c10d44e133dbe2edc36611` | same release |
| `install.sh` at tag `v0.1.2` (not used by this runbook) | 0.1.2 | `5c98a86a4b811c471b212219cb2a62d458244220ffa71ac8e3baf3700b17b871` | https://raw.githubusercontent.com/NVIDIA/OpenShell/v0.1.2/install.sh |

The README of the project suggests `curl ... install.sh | sh` from `main`. Do not use that: it is unpinned. The tagged installer above accepts `OPENSHELL_VERSION=v0.1.2` and checks package checksums itself, so it is an acceptable alternative to the manual steps below.

The Python SDK is a dev and verification dependency only. It is not in `pyproject.toml`, and `adapters/openshell_driver.py` imports it only when a driver is built. Install it with:
```bash
poetry run pip install --no-deps --require-hashes -r scripts/verify/openshell-requirements.txt
```

## Requirements (from the project's Support Matrix at v0.1.2)
- Linux (Debian or Ubuntu, amd64 or arm64), macOS on Apple Silicon (through Docker Desktop), or Windows with WSL 2 (experimental).
- Docker Engine or Docker Desktop 28.0 or newer, or Podman 5, for the Docker and Podman drivers.
- **Kernel:** Landlock ABI 3 or newer (Linux 6.2 or newer, with Landlock enabled), and seccomp user notification with `SECCOMP_IOCTL_NOTIF_ADDFD`. A kernel version alone is not enough: a disabled Landlock LSM, or a runtime profile that blocks seccomp operations, makes launch fail closed. Kernels before 5.19 run in a reduced "legacy read-only" mode.
- glibc 2.28 or newer for the gateway binary.
- Check Landlock quickly: `python3 -c "import ctypes; print(ctypes.CDLL(None).syscall(444, None, 0, 1))"` prints the ABI number on x86_64 (7 in the build container). A negative number means no Landlock.

## Install the gateway and CLI
```bash
V=v0.1.2; B=https://github.com/NVIDIA/OpenShell/releases/download/$V
curl -fsSL -o openshell.deb $B/openshell_0.1.2-1_amd64.deb
echo "1f5416ea08f32fdc621f20a2cc0324298e60aba8bbe996459d9e3b44195f23df  openshell.deb" | sha256sum -c -
sudo dpkg -i openshell.deb               # or: dpkg-deb -x openshell.deb ./openshell-root   (no root, no system change)
```
The package installs `openshell`, `openshell-gateway`, `openshell-prover` and a per-user systemd unit. Start the gateway with `systemctl --user enable --now openshell-gateway`, then `openshell gateway add https://127.0.0.1:17670 --local --name openshell`. Without systemd (a container, for example) run the gateway yourself:
```bash
export OPENSHELL_LOCAL_TLS_DIR=$HOME/.local/state/openshell/tls
openshell-gateway generate-certs --output-dir "$OPENSHELL_LOCAL_TLS_DIR" --server-san host.openshell.internal
OPENSHELL_COMPUTE_DRIVER=docker openshell-gateway &      # listens on 127.0.0.1:17670, mTLS
openshell gateway add https://127.0.0.1:17670 --local --name openshell && openshell status
```
Use mTLS. With `--disable-tls` the gateway refuses to create Docker sandboxes (`docker sandboxes require launch-scoped gateway authentication`). The platform finds the gateway through the OpenShell CLI configuration (`XDG_CONFIG_HOME`), or `OPENSHELL_ENDPOINT` names one.

## Images
The Docker driver needs three images.
1. **The supervisor and sandbox runtime images** `ghcr.io/nvidia/openshell/supervisor:0.1.2` and `ghcr.io/nvidia/openshell/sandbox:0.1.2`. The gateway pulls them by itself. Normally you do nothing. **In the build container the pull failed** (`ghcr.io` answered, the blob host `pkg-containers.githubusercontent.com` was forbidden), so they were rebuilt locally from the two checksum-checked release archives above and given the same tags. The images that worked held both binaries, `/openshell-supervisor` and `/openshell-sandbox`, on a glibc base:
   ```dockerfile
   FROM <any glibc image, for example ubuntu:22.04>
   USER root
   COPY openshell-supervisor /openshell-supervisor
   COPY openshell-sandbox /openshell-sandbox
   ENTRYPOINT []
   ```
   Build it with `docker build --pull=false -t ghcr.io/nvidia/openshell/supervisor:0.1.2 -t ghcr.io/nvidia/openshell/sandbox:0.1.2 .` and **restart the gateway**: it reads the image ids at startup and keeps them. This workaround is only for a host that cannot reach `ghcr.io`.
2. **The workload image** (`OPENSHELL_IMAGE`). The built-in default is `nvcr.io/nvidia/base/ubuntu:24.04`, a minimal Ubuntu without Python. The agent program needs `python3` and nothing else (it is standard library only). The image must also have:
   - a non-root user named `sandbox` and `USER sandbox` (OpenShell refuses a workload whose identity has uid or gid 0: `workload identity must not contain UID or GID zero`);
   - the work directory, owned by that user. The filesystem policy makes the work directory the only writable place, so it cannot be created from inside. The driver checks for it before it runs the command and fails with a clear message.
   ```dockerfile
   FROM <an image with python3, for example ubuntu:24.04 plus apt-get install python3>
   USER root
   RUN id sandbox >/dev/null 2>&1 || useradd -m -s /bin/bash sandbox
   RUN mkdir -p /sandbox/work && chown sandbox:sandbox /sandbox/work
   ENTRYPOINT []
   CMD ["sleep", "infinity"]
   USER sandbox
   ```
   In the build container this was built `FROM redis/redis-stack-server:latest` (Ubuntu 22.04 with python3.10), because it was the local image that had Python and Docker Hub was rate limited.

## Platform settings
```bash
AGENT_RUNTIME=openshell
SANDBOX_GATEWAY_URL=http://172.17.0.1:8000     # this API, as the sandbox sees it. Not loopback: OpenShell blocks loopback and link-local targets
OPENSHELL_IMAGE=registry.example/agent-workload:1
# optional: OPENSHELL_ENDPOINT, OPENSHELL_WORKSPACE, SANDBOX_CPU, SANDBOX_MEMORY, SANDBOX_WALL_SECONDS,
#           SANDBOX_WORK_DIR, SANDBOX_READ_ONLY_PATHS, SANDBOX_NETWORK_BINARIES
```
The default image and the compose `worker` service have neither the OpenShell SDK nor Docker, so run the worker on the host that has them (`poetry run python -m workers`) when you use `openshell`. The API still queues each run as a job. The **worker** (`python -m workers`, or `EMBEDDED_WORKERS=1`) starts the sandbox, so the worker host needs the OpenShell gateway, Docker and the SDK. The API process only needs to be reachable from the sandbox on `SANDBOX_GATEWAY_URL`. Bind it to an address the sandbox can reach (`--host 0.0.0.0`, or the bridge address).

## Run the live check
```bash
docker compose up -d postgres redis
OPENSHELL_SANDBOX_IMAGE=<workload image> scripts/verify/openshell.sh
```
It installs the pinned SDK if needed, checks the SDK surface, then (in one process, with a throwaway database and fake model and embeddings) serves the platform with the real driver and runs:

| Check | What it proves | Expected |
|---|---|---|
| A3 | A direct call to a model provider fails, and an event says so | `failed (URLError)`; a `network_denied` row that OpenShell wrote |
| A4 | A read outside the work directory fails, and an event says so | `failed (PermissionError)`; a `file_denied` row (from the probe's report, see below) |
| L1, L2 | The memory limit is on the container and kills a hog; the CPU limit is on it | exit status 137; 128 MiB and 0.5 CPU |
| L3 | Cancelling a run removes its sandbox | no `openshell.ai/managed-by` containers left |
| A2 | An authorised question completes in the sandbox | one allowed `tool.call`, events `start` then `exit`, not flagged |
| A5 | A tool argument the policy forbids is a deny row | `tool_argument_not_allowed`, a flagged partial answer |

It exits 0 when every check passed, 1 when one failed, 2 when the host cannot run it.

## What the live run showed (so you do not have to find it again)
- **Binary identity.** A network rule names the executable that opens the connection by its **real path**, not a symlink: `/usr/bin/python3` is a symlink, and the connection came from `/usr/bin/python3.10`. The rule is `SANDBOX_NETWORK_BINARIES`, default the glob `/usr/bin/python3*`. With the wrong path every call to the gateway is `DENIED ... [reason:transparent_tcp_policy_denied]`.
- **Names.** The gateway refuses a sandbox or template name over 19 characters. The driver names them `r` plus 18 hex digits of the run id.
- **Reads.** OpenShell adds baseline read paths when a policy has a network rule: `/usr`, `/lib`, `/etc`, `/app`, `/var/log`, `/proc` and `/dev/urandom` (read), `/tmp` and `/dev/null` (write). So `/etc/hostname` is readable inside the sandbox, and the A4 probe reads `/var/lib/dpkg/status`, which Landlock refuses (`CHECK_OUTSIDE_PATH` names another file for another image). A read that fails for any other reason (a missing file) is reported as such and does not pass A4.
- **No event for a refused read.** Landlock gives the process `EACCES` and OpenShell logs nothing. The check run records the `file_denied` row from the probe's own report and marks it `source: agent_check`. A real agent run has no such row, so absence of a `file_denied` event does not prove no read was attempted.
- **Events.** A refused connection comes through as `NET:OPEN [MED] DENIED <exe>(pid) -> host:port [reason:...]` and `NET:REFUSE [MED] DENIED host [reason:policy_dns_ineligible]`. Routine lines (ssh relays, policy load, startup) are not stored.
- **Memory.** A process over the limit exits 137 and OpenShell wrote no event of its own. The runtime adds a `limit_hit` row marked `source: exit_code`.

## Accepted risks (QA, Sprint 009)
- **The run token crosses the Docker bridge in plain HTTP** (`SANDBOX_GATEWAY_URL=http://...`). The bridge is local to the host and the token lives for the wall limit plus a minute, on one run's two routes. TLS from the sandbox to the platform is a hosting item (Q38). Do not point `SANDBOX_GATEWAY_URL` at a network you do not control.
- **Base images are not pinned by digest here.** The container could not fetch digests. On the first pull, record each image's digest (`docker image inspect --format '{{index .RepoDigests 0}}' <image>`) and reference the image by `@sha256:...` in `OPENSHELL_IMAGE` and in the Dockerfiles above.

## Policy rules for tool arguments (QA fixes)
`set-policy` refuses `tool_arguments` for a tool the platform does not have, and refuses `pattern`, `patternProperties` and `format` in a schema (a regex can backtrack without end). Use enums, lengths and types. A schema check also has a 0.25 second limit and runs off the event loop: a timeout is a deny. A run token stops working when the API key that started the run is revoked.

## Troubleshooting
| You see | Cause and fix |
|---|---|
| `docker sandboxes require launch-scoped gateway authentication` | The gateway runs without TLS. Run it with mTLS (`generate-certs`, the unit's way) and register it with `--local`. |
| `workload identity must not contain UID or GID zero` | The image runs as root. Add a `sandbox` user and `USER sandbox`. |
| `exec: "/openshell-supervisor": stat ... no such file` | The supervisor image does not hold `/openshell-supervisor`. |
| `No such image: sha256:...` from the gateway | You rebuilt an image after the gateway started. Restart the gateway. |
| `name exceeds maximum length (36 > 19)` | A run id was used as a name. The driver already shortens it: if you see this, the driver is out of date. |
| Every gateway call is `DENIED ... transparent_tcp_policy_denied` | The interpreter's real path is not in `SANDBOX_NETWORK_BINARIES`. `readlink -f $(which python3)` inside the image. |
| `the sandbox image has no work directory /sandbox/work` | Build the directory into the image, owned by `sandbox`. |
| The run fails `sandbox_unavailable` | The sandbox did not start. The worker log has the gateway's reason; `openshell status` says whether the gateway is up. |
| The run fails `wall_time_exceeded` | It hit `SANDBOX_WALL_SECONDS`. The run has a `limit_hit` event. |
| The run fails `bad_output` | The agent's last stdout line was not `{"result": ...}`, or the output was over 1 MiB. |
