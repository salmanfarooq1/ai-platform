"""Release manifest: every external image index and the local app build, bound by one hash.

External images and Dockerfile bases must be pinned by a multi-arch *index* digest. The raw
index is fetched once while resolving pins; its bytes must hash to the pinned digest, its media
type must be an index (not a child manifest) and it must list the selected platform. The local
app build is a different kind of identity, labelled `local-build` and never given an index digest. Its
stable identity is `content_id`: the ordered layer digests plus the runtime config that changes behaviour. The
Docker store ID is recorded for information only: under the containerd image store it is the local OCI index
digest, which includes build attestations and so changes on every rebuild. Verification is offline.

Usage: python -m scripts.release.build_manifest build|verify --output/--manifest PATH
"""
import argparse
import hashlib
import json
import platform as host_platform
import re
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml

from scripts.poc_lib.runner import CommandError
from scripts.supply_chain.check_pins import REFERENCE, dockerfile_references

VERSION = 1
INDEX_TYPES = frozenset({
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
})
CHILD_TYPES = frozenset({
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
})
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
APP_SERVICES = ("api", "worker")
Resolver = Callable[[str], bytes]


class ManifestError(ValueError):
    """The release identity is unsafe or does not match. The message never includes secrets."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_digest(manifest: Mapping[str, Any]) -> str:
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def default_platform() -> str:
    machine = host_platform.machine().lower()
    return "linux/" + {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(machine, machine)


def check_pin(location: str, ref: object) -> str:
    """Return the digest of a strictly pinned `name:tag@sha256:<64 hex>` reference."""
    if not isinstance(ref, str) or REFERENCE.fullmatch(ref) is None:
        raise ManifestError(f"{location}: expected a tag and a complete sha256 digest")
    repository_tag, digest = ref.split("@", 1)
    tag = repository_tag.rsplit(":", 1)[1]
    hex_part = digest.removeprefix("sha256:")
    if tag == "latest" or len(set(hex_part)) < 3:
        raise ManifestError(f"{location}: floating tag or placeholder digest")
    return digest


def collect_inputs(root: Path) -> list[dict[str, str]]:
    """Every external image in every Compose profile and every Dockerfile base, validated."""
    compose = yaml.safe_load((root / "docker-compose.yml").read_text())
    found: list[dict[str, str]] = []
    for name, service in sorted(compose.get("services", {}).items()):
        if "image" in service:
            found.append({"location": f"docker-compose.yml:{name}", "ref": service["image"]})
    dockerfile = root / "Dockerfile"
    for location, ref in dockerfile_references(root, dockerfile):
        found.append({"location": location, "ref": ref})
    for item in found:
        check_pin(item["location"], item["ref"])
    return found


def verify_index(ref: str, raw: bytes, platform: str) -> dict[str, Any]:
    """Check raw registry bytes against the pinned digest and extract the index facts."""
    digest = check_pin(ref, ref)
    if "sha256:" + hashlib.sha256(raw).hexdigest() != digest:
        raise ManifestError(f"{ref}: registry bytes do not match the pinned digest")
    try:
        document = json.loads(raw)
        media_type = document["mediaType"]
        entries = document["manifests"]
    except (ValueError, KeyError, TypeError):
        raise ManifestError(f"{ref}: not a multi-arch index (a child manifest has no platform list)") from None
    if media_type in CHILD_TYPES or media_type not in INDEX_TYPES:
        raise ManifestError(f"{ref}: pinned digest is not a multi-arch index")
    platforms = sorted({
        f"{e['platform']['os']}/{e['platform']['architecture']}"
        for e in entries
        if isinstance(e, dict) and isinstance(e.get("platform"), dict)
        and e["platform"].get("os") != "unknown"
    })
    if platform not in platforms:
        raise ManifestError(f"{ref}: index has no {platform} entry")
    return {"ref": ref, "digest": digest, "media_type": media_type, "platforms": platforms,
            "selected_platform": platform}


CONFIG_FIELDS = ("Entrypoint", "Cmd", "Env", "User", "WorkingDir", "ExposedPorts", "Labels")
COMPOSE_LABEL_PREFIX = "com.docker.compose."
ID_NOTE = "local store id (not stable across rebuilds)"


def local_identity(images: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    """Validate the local build and return its recorded identity.

    Compose labels each service's image with its service name, so `api` and `worker` have different image
    IDs (the Docker store's ID, which may itself be an OCI index of the *local* build: it is never a registry
    index digest, and it changes on every rebuild). They are still one artifact when `content_id` (ordered layer
    digests and runtime config) is identical. The store ID is recorded as information, labelled as unstable.
    """
    if set(images) != set(APP_SERVICES):
        raise ManifestError("local build must name exactly the api and worker images")
    for service, image in images.items():
        if not IMAGE_ID.fullmatch(image.get("image_id", "")) or not IMAGE_ID.fullmatch(image.get("content_id", "")):
            raise ManifestError(f"{service}: not an immutable image ID")
    if len({image["content_id"] for image in images.values()}) != 1:
        raise ManifestError("api and worker must run one artifact")
    return {"source": "local-build", "content_id": images[APP_SERVICES[0]]["content_id"],
            "services": {name: _service_record(images[name]) for name in sorted(images)}}


def _service_record(image: Mapping[str, str]) -> dict[str, str]:
    record = {"image_id": image["image_id"], "image_id_note": ID_NOTE}
    child = image.get("platform_manifest_digest")
    if child:
        if not DIGEST.fullmatch(child):
            raise ManifestError("platform manifest digest is malformed")
        record["platform_manifest_digest"] = child
    return record


def build_manifest(root: Path, resolver: Resolver, local_images: Mapping[str, Mapping[str, str]], *, platform: str,
                   source: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve and prove every pin, then bind the honest local build and the Compose/Dockerfile hashes."""
    inputs = collect_inputs(root)
    local = local_identity(local_images)
    proofs: dict[str, dict[str, Any]] = {}
    for item in inputs:
        ref = item["ref"]
        if ref in proofs:
            continue
        try:
            raw = resolver(ref)
        except ManifestError as exc:
            raise ManifestError(f"{item['location']}: {exc}") from None
        except Exception:
            raise ManifestError(f"{item['location']}: index proof unavailable") from None
        proofs[ref] = verify_index(ref, raw, platform)
    manifest: dict[str, Any] = {
        "version": VERSION,
        "source": dict(source),
        "compose_sha256": sha256_file(root / "docker-compose.yml"),
        "dockerfile_sha256": sha256_file(root / "Dockerfile"),
        "external_images": [proofs[ref] for ref in sorted(proofs)],
        "local_app": {**local, "build_inputs": sorted({i["ref"] for i in inputs if i["location"].startswith("Dockerfile:")})},
    }
    manifest["manifest_sha256"] = manifest_digest(manifest)
    return manifest


def verify_manifest(manifest: Mapping[str, Any], root: Path, local_images: Mapping[str, Mapping[str, str]], *, platform: str) -> None:
    """Offline checks of a stored manifest against the tree and the images that now exist."""
    try:
        if manifest.get("version") != VERSION or manifest.get("manifest_sha256") != manifest_digest(manifest):
            raise ManifestError("manifest hash does not match its content")
        if (manifest["compose_sha256"] != sha256_file(root / "docker-compose.yml")
                or manifest["dockerfile_sha256"] != sha256_file(root / "Dockerfile")):
            raise ManifestError("manifest is stale: Compose or Dockerfile changed")
        recorded = {image["ref"]: image for image in manifest["external_images"]}
        inputs = {item["ref"] for item in collect_inputs(root)}
        if set(recorded) != inputs:
            raise ManifestError("manifest is stale: the pinned image set changed")
        for ref, image in recorded.items():
            if (image["digest"] != check_pin(ref, ref) or image["media_type"] not in INDEX_TYPES
                    or image["selected_platform"] != platform or platform not in image["platforms"]):
                raise ManifestError("manifest index proof does not match its pin")
        local = manifest["local_app"]
        if local.get("source") != "local-build" or {"digest", "index_digest"} & set(local):
            raise ManifestError("local app identity must be labelled local-build without an index digest")
        current = local_identity(local_images)
        if local["content_id"] != current["content_id"]:
            raise ManifestError("local app image changed since the manifest was written (layers or runtime config)")
    except (KeyError, TypeError, AttributeError):
        raise ManifestError("manifest is malformed") from None


def _stable_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """The runtime config that changes behaviour; compose-generated labels differ per service and are excluded."""
    stable = {field: config.get(field) for field in CONFIG_FIELDS}
    labels = stable["Labels"] or {}
    stable["Labels"] = {k: v for k, v in sorted(labels.items()) if not k.startswith(COMPOSE_LABEL_PREFIX)}
    return stable


def _platform_manifest_digest(document: Mapping[str, Any], platform: str | None) -> str | None:
    """The selected platform's child manifest digest, when the local store reports one (containerd store)."""
    for entry in document.get("Manifests") or []:
        try:
            image_platform = entry["ImageData"]["Platform"]
            if (entry.get("Kind") == "image" and platform
                    and f"{image_platform['os']}/{image_platform['architecture']}" == platform):
                digest = entry["Descriptor"]["digest"]
                if isinstance(digest, str) and DIGEST.fullmatch(digest):
                    return digest
        except (KeyError, TypeError):
            continue
    return None


def inspect_local_image(runner: Any, name: str, env: Mapping[str, str] | None = None,
                        platform: str | None = None) -> dict[str, str]:
    """Local identity: `content_id` (stable) over layers and runtime config, plus the informational store ID."""
    out = runner.run(["docker", "image", "inspect", "--format", "{{json .}}", name], env=env).text
    try:
        document = json.loads(out)
        if isinstance(document, list):
            document = document[0]
        image_id = document["Id"]
        layers = document["RootFS"]["Layers"]
        config = document.get("Config") or {}
        if not isinstance(layers, list) or not layers:
            raise ValueError
        body = {"layers": layers, "config": _stable_config(config)}
    except (ValueError, KeyError, TypeError, IndexError):
        raise ManifestError(f"{name}: cannot read the image layers and config") from None
    content = "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    result = {"image_id": image_id, "content_id": content}
    child = _platform_manifest_digest(document, platform)
    if child:
        result["platform_manifest_digest"] = child
    return result


def registry_resolver(runner: Any, *, sleep: Callable[[float], None] = time.sleep) -> Resolver:
    """Fetch the raw index bytes with buildx; the digest in the reference is checked by the caller."""
    def resolve(ref: str) -> bytes:
        for attempt in range(3):
            try:
                return bytes(runner.run(["docker", "buildx", "imagetools", "inspect", "--raw", ref]).stdout)
            except CommandError as exc:
                if attempt < 2:
                    sleep(0.25 * (2 ** attempt))
                    continue
                lines = exc.stderr.decode("utf-8", "replace").strip().splitlines()
                cause = lines[-1] if lines else f"command exited {exc.returncode}"
                if re.search(r"(?i)(https?://|token|password|secret|authorization|credential|bearer|[?=&])", cause):
                    cause = f"command exited {exc.returncode} (details redacted)"
                cause = re.sub(r"[A-Za-z0-9_+/.-]{24,}", "[redacted]", cause)
                cause = re.sub(r"[^\w .,:;()/+-]", "?", cause)[:160]
                raise ManifestError(f"{ref}: index proof unavailable: {cause}") from None
        raise AssertionError("unreachable")
    return resolve


def main(argv: list[str] | None = None) -> int:
    from scripts.poc_lib.runner import LocalRunner
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--project", required=True, help="Compose project that built api and worker")
    check = sub.add_parser("verify")
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--project", required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    runner = LocalRunner()
    images = {s: inspect_local_image(runner, f"{args.project}-{s}", platform=default_platform()) for s in APP_SERVICES}
    try:
        if args.command == "build":
            commit = runner.run(["git", "rev-parse", "HEAD"], check=False).text.strip()
            dirty = bool(runner.run(["git", "status", "--porcelain"], check=False).text.strip())
            manifest = build_manifest(root, registry_resolver(runner), images, platform=default_platform(),
                                      source={"commit": commit, "dirty": dirty})
            args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        else:
            verify_manifest(json.loads(args.manifest.read_text()), root, images, platform=default_platform())
    except ManifestError as exc:
        print(f"release manifest refused: {exc}", file=sys.stderr)
        return 1
    print("release manifest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
