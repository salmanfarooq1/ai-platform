"""WP1: release manifest refuses floating or child-manifest inputs and binds the honest local build."""
import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml

from scripts.release import build_manifest as bm

ROOT = Path(__file__).resolve().parents[2]
INDEX = "application/vnd.oci.image.index.v1+json"
CHILD = "application/vnd.oci.image.manifest.v1+json"
LOCAL_ID = "sha256:" + "ab" * 32
CONTENT = "sha256:" + "5a" * 32


def local_images(api=LOCAL_ID, worker="sha256:" + "ac" * 32, content=CONTENT, worker_content=None):
    """Compose labels each service image, so IDs differ per service while the layer content is shared."""
    return {"api": {"image_id": api, "content_id": content},
            "worker": {"image_id": worker, "content_id": worker_content or content}}


def _index(media_type=INDEX, platforms=("amd64", "arm64")):
    return json.dumps({
        "schemaVersion": 2, "mediaType": media_type,
        "manifests": [{"mediaType": CHILD, "digest": "sha256:" + "11" * 32, "size": 1,
                       "platform": {"os": "linux", "architecture": arch}} for arch in platforms],
    }).encode()


class Registry:
    """Fake registry: serves a raw index whose sha256 equals the pinned digest."""

    def __init__(self):
        self.calls = []

    def __call__(self, ref):
        self.calls.append(ref)
        raw = _index()
        return raw


def _tree(tmp_path):
    """A copy of the compose file and Dockerfile whose digests the fake registry can vouch for."""
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    registry_raw = {}
    for service in compose["services"].values():
        if "image" in service:
            raw = _index()
            digest = hashlib.sha256(raw).hexdigest()
            service["image"] = service["image"].split("@")[0] + "@sha256:" + digest
            registry_raw[service["image"]] = raw
    (tmp_path / "docker-compose.yml").write_text(yaml.safe_dump(compose, sort_keys=False))
    dockerfile = (ROOT / "Dockerfile").read_text()
    raw = _index()
    digest = hashlib.sha256(raw).hexdigest()
    import re
    dockerfile = re.sub(r"@sha256:[0-9a-f]{64}", "@sha256:" + digest, dockerfile)
    (tmp_path / "Dockerfile").write_text(dockerfile)
    for ref in re.findall(r"\S+@sha256:[0-9a-f]{64}", dockerfile):
        registry_raw[ref] = raw
    return registry_raw


def _resolver(raws):
    def resolve(ref):
        if ref not in raws:
            raise bm.ManifestError(f"index proof unavailable for {ref}")
        return raws[ref]
    return resolve


def _build(tmp_path, raws, **kwargs):
    return bm.build_manifest(
        tmp_path, _resolver(raws), local_images(),
        platform="linux/amd64", source={"commit": "c" * 40, "dirty": False}, **kwargs)


def test_rejects_unpinned_and_platform_images(tmp_path):
    raws = _tree(tmp_path)
    good = _build(tmp_path, raws)
    assert good["external_images"], "every profile image is covered"
    compose_path = tmp_path / "docker-compose.yml"
    original = compose_path.read_text()
    compose = yaml.safe_load(original)
    victims = {name: svc["image"] for name, svc in compose["services"].items() if "image" in svc}
    assert {"prometheus", "ollama", "seaweedfs"} <= set(victims)  # optional profiles are checked too
    mutations = {
        "floating-tag": lambda ref: ref.split("@")[0],
        "latest-tag": lambda ref: ref.split(":")[0] + ":latest@sha256:" + "ab" * 32,
        "placeholder-digest": lambda ref: ref.split("@")[0] + "@sha256:" + "0" * 64,
        "placeholder-text": lambda ref: ref.split("@")[0] + "@sha256:<PLACEHOLDER>",
        "short-digest": lambda ref: ref.split("@")[0] + "@sha256:" + "ab" * 8,
        "uppercase-digest": lambda ref: ref.split("@")[0] + "@sha256:" + "AB" * 32,
        "wrong-algorithm": lambda ref: ref.split("@")[0] + "@sha512:" + "ab" * 32,
    }
    for name, svc in victims.items():
        for label, mutate in mutations.items():
            broken = copy.deepcopy(compose)
            broken["services"][name]["image"] = mutate(svc)
            compose_path.write_text(yaml.safe_dump(broken, sort_keys=False))
            with pytest.raises(bm.ManifestError):
                _build(tmp_path, raws)
    compose_path.write_text(original)
    # Dockerfile bases are checked the same way, including the runtime stage.
    dockerfile = tmp_path / "Dockerfile"
    text = dockerfile.read_text()
    first = next(line for line in text.splitlines() if line.startswith("FROM "))
    for label, replacement in (("floating", first.split("@")[0]), ("placeholder", first.split("@")[0] + "@sha256:" + "0" * 64),
                               ("malformed", first.split("@")[0] + "@sha256:xyz")):
        dockerfile.write_text(text.replace(first, replacement, 1))
        with pytest.raises(bm.ManifestError):
            _build(tmp_path, raws)
    dockerfile.write_text(text)
    # A digest that names a single-platform child manifest is not an index.
    child = _index(media_type=CHILD)
    ref = next(iter(raws))
    child_ref = ref.split("@")[0] + "@sha256:" + hashlib.sha256(child).hexdigest()
    with pytest.raises(bm.ManifestError, match="index"):
        bm.verify_index(child_ref, child, "linux/amd64")
    single = json.dumps({"schemaVersion": 2, "mediaType": CHILD, "config": {}, "layers": []}).encode()
    with pytest.raises(bm.ManifestError, match="index"):
        bm.verify_index(ref.split("@")[0] + "@sha256:" + hashlib.sha256(single).hexdigest(), single, "linux/amd64")
    # A served manifest whose bytes do not hash to the pinned digest is refused.
    tampered = dict(raws)
    tampered[ref] = _index(platforms=("amd64",)) + b" "
    with pytest.raises(bm.ManifestError, match="digest"):
        _build(tmp_path, tampered)
    # The selected platform must be in the index.
    only_arm = {r: _index(platforms=("arm64",)) for r in raws}
    with pytest.raises(bm.ManifestError):
        bm.build_manifest(tmp_path, _resolver(only_arm), local_images(),
                          platform="linux/amd64", source={"commit": "c" * 40, "dirty": False})


def test_manifest_binds_local_build_and_indexes(tmp_path):
    raws = _tree(tmp_path)
    manifest = _build(tmp_path, raws)
    # External images carry verified index proof; the local app build has no index digest.
    for image in manifest["external_images"]:
        assert image["media_type"] == INDEX
        assert image["ref"].endswith("@sha256:" + image["digest"].removeprefix("sha256:"))
        assert image["selected_platform"] == "linux/amd64"
        assert "linux/amd64" in image["platforms"] and "linux/arm64" in image["platforms"]
    local = manifest["local_app"]
    assert local["source"] == "local-build"
    assert local["content_id"] == CONTENT and set(local["services"]) == {"api", "worker"}
    assert local["services"]["api"]["image_id"] == LOCAL_ID and local["services"]["worker"]["image_id"] != LOCAL_ID
    assert "index_digest" not in local and "digest" not in local
    assert local["build_inputs"] and all("@sha256:" in ref for ref in local["build_inputs"])
    assert manifest["compose_sha256"] == hashlib.sha256((tmp_path / "docker-compose.yml").read_bytes()).hexdigest()
    assert manifest["source"] == {"commit": "c" * 40, "dirty": False}
    bm.verify_manifest(manifest, tmp_path, local_images(), platform="linux/amd64")
    # Verification is offline: it never asks the registry again.
    # Stale or tampered manifests, changed images and a missing proof all refuse.
    images = local_images()
    # A new local store ID with the same content is accepted: the ID is informational (see the rebuild tests below).
    bm.verify_manifest(manifest, tmp_path, local_images(api="sha256:" + "cd" * 32, worker="sha256:" + "ce" * 32),
                       platform="linux/amd64")
    changed = local_images(content="sha256:" + "cd" * 32)
    with pytest.raises(bm.ManifestError, match="local"):
        bm.verify_manifest(manifest, tmp_path, changed, platform="linux/amd64")
    with pytest.raises(bm.ManifestError, match="one artifact"):
        bm.verify_manifest(manifest, tmp_path, local_images(worker_content="sha256:" + "cd" * 32), platform="linux/amd64")
    tampered = copy.deepcopy(manifest)
    tampered["external_images"][0]["digest"] = "sha256:" + "ee" * 32
    with pytest.raises(bm.ManifestError):
        bm.verify_manifest(tampered, tmp_path, images, platform="linux/amd64")
    relabelled = copy.deepcopy(manifest)
    relabelled["local_app"]["content_id"] = "sha256:" + "cd" * 32
    with pytest.raises(bm.ManifestError):
        bm.verify_manifest(relabelled, tmp_path, images, platform="linux/amd64")
    fake_index = copy.deepcopy(manifest)
    fake_index["local_app"]["index_digest"] = "sha256:" + "11" * 32
    with pytest.raises(bm.ManifestError):
        bm.verify_manifest(fake_index, tmp_path, images, platform="linux/amd64")
    # A changed Compose or Dockerfile makes the manifest stale.
    compose_path = tmp_path / "docker-compose.yml"
    backup = compose_path.read_bytes()
    compose_path.write_bytes(backup + b"\n# changed\n")
    with pytest.raises(bm.ManifestError, match="stale"):
        bm.verify_manifest(manifest, tmp_path, images, platform="linux/amd64")
    compose_path.write_bytes(backup)
    dockerfile = tmp_path / "Dockerfile"
    shutil.copy(dockerfile, tmp_path / "Dockerfile.bak")
    dockerfile.write_text(dockerfile.read_text() + "\n# changed\n")
    with pytest.raises(bm.ManifestError, match="stale"):
        bm.verify_manifest(manifest, tmp_path, images, platform="linux/amd64")
    shutil.copy(tmp_path / "Dockerfile.bak", dockerfile)
    # The two services must run one artifact, and image IDs must be real ones.
    with pytest.raises(bm.ManifestError, match="one artifact"):
        bm.build_manifest(tmp_path, _resolver(raws), local_images(worker_content="sha256:" + "cd" * 32),
                          platform="linux/amd64", source={"commit": "c" * 40, "dirty": False})
    with pytest.raises(bm.ManifestError, match="image ID"):
        bm.build_manifest(tmp_path, _resolver(raws), {"api": {"image_id": "latest", "content_id": CONTENT}, "worker": {"image_id": "latest", "content_id": CONTENT}},
                          platform="linux/amd64", source={"commit": "c" * 40, "dirty": False})
    # Unavailable index proof refuses the build of a manifest.
    missing = dict(raws)
    missing.pop(next(iter(missing)))
    with pytest.raises(bm.ManifestError, match="unavailable"):
        _build(tmp_path, missing)


def test_manifest_hash_covers_every_field(tmp_path):
    raws = _tree(tmp_path)
    manifest = _build(tmp_path, raws)
    images = local_images()
    mutated = copy.deepcopy(manifest)
    mutated["source"]["commit"] = "d" * 40
    with pytest.raises(bm.ManifestError, match="hash"):
        bm.verify_manifest(mutated, tmp_path, images, platform="linux/amd64")
    assert manifest["manifest_sha256"] == bm.manifest_digest(manifest)


def test_real_repository_inputs_are_all_covered():
    inputs = bm.collect_inputs(ROOT)
    locations = {item["location"] for item in inputs}
    assert any(loc.startswith("Dockerfile:") for loc in locations)
    for name in ("prometheus", "grafana", "ollama", "seaweedfs", "postgres", "valkey"):
        assert f"docker-compose.yml:{name}" in locations


class _Inspect:
    """Fake runner answering `docker image inspect` with one JSON document like Docker 29."""

    def __init__(self, image_id, layers, config, manifests=None):
        document = {"Id": image_id, "RootFS": {"Layers": layers}, "Config": config}
        if manifests is not None:
            document["Manifests"] = manifests
        self.out = json.dumps([document]).encode()

    def run(self, argv, *, env=None, **kwargs):
        from types import SimpleNamespace
        return SimpleNamespace(text=self.out.decode(), stdout=self.out)


LAYERS = ["sha256:" + "1a" * 32, "sha256:" + "2b" * 32]
CONFIG = {"Entrypoint": ["tini"], "Cmd": ["serve"], "Env": ["A=1", "PATH=/x"], "User": "1000", "WorkingDir": "/app",
          "ExposedPorts": {"8000/tcp": {}}, "Labels": {"org.example": "1", "com.docker.compose.service": "api"}}


def _content(image_id="sha256:" + "01" * 32, layers=LAYERS, config=CONFIG):
    return bm.inspect_local_image(_Inspect(image_id, layers, config), "x")["content_id"]


def test_content_id_ignores_the_local_store_id_and_compose_labels():
    base = _content()
    assert _content(image_id="sha256:" + "02" * 32) == base
    relabelled = {**CONFIG, "Labels": {"org.example": "1", "com.docker.compose.service": "worker",
                                        "com.docker.compose.image": "sha256:ff"}}
    assert _content(config=relabelled) == base
    noise = {**CONFIG, "Hostname": "abc", "Image": "sha256:zz"}
    assert _content(config=noise) == base
    # The recorded identity keeps the local ID, labelled as unstable and never as an index digest.
    info = bm.inspect_local_image(_Inspect("sha256:" + "01" * 32, LAYERS, CONFIG), "x")
    assert info["image_id"] == "sha256:" + "01" * 32


@pytest.mark.parametrize("field,value", [
    ("Entrypoint", ["sh"]), ("Cmd", ["other"]), ("Env", ["A=2", "PATH=/x"]), ("User", "0"),
    ("WorkingDir", "/srv"), ("ExposedPorts", {"9000/tcp": {}}), ("Labels", {"org.example": "2"}),
])
def test_content_id_changes_with_runtime_config(field, value):
    assert _content(config={**CONFIG, field: value}) != _content()


def test_content_id_changes_with_layers_and_their_order():
    assert _content(layers=LAYERS + ["sha256:" + "3c" * 32]) != _content()
    assert _content(layers=list(reversed(LAYERS))) != _content()


def test_manifest_labels_the_local_id_and_records_a_resolvable_platform_digest(tmp_path):
    raws = _tree(tmp_path)
    child = "sha256:" + "77" * 32
    manifests = [{"Kind": "image", "Descriptor": {"digest": child},
                  "ImageData": {"Platform": {"os": "linux", "architecture": "amd64"}}},
                 {"Kind": "attestation", "Descriptor": {"digest": "sha256:" + "88" * 32}}]
    info = bm.inspect_local_image(_Inspect("sha256:" + "01" * 32, LAYERS, CONFIG, manifests), "x", platform="linux/amd64")
    assert info["platform_manifest_digest"] == child
    images = {"api": info, "worker": {**info, "image_id": "sha256:" + "02" * 32}}
    manifest = bm.build_manifest(tmp_path, _resolver(raws), images, platform="linux/amd64",
                                 source={"commit": "c" * 40, "dirty": False})
    api = manifest["local_app"]["services"]["api"]
    assert api["image_id"] == "sha256:" + "01" * 32 and api["platform_manifest_digest"] == child
    assert api["image_id_note"] == "local store id (not stable across rebuilds)"
    assert "index_digest" not in manifest["local_app"]
    bm.verify_manifest(manifest, tmp_path, images, platform="linux/amd64")
