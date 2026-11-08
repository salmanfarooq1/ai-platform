"""Validate profile-scoped image exceptions and render a Grype config."""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ALLOWED_PROFILES = {"streams", "lake", "models"}
CVE = re.compile(r"CVE-\d{4}-\d{4,}")


def render_config(root: Path, image_ref: str, today: date | None = None) -> dict:
    today = today or date.today()
    compose = yaml.safe_load((root / "docker-compose.yml").read_text())
    entries = []
    path = root / "scripts/supply_chain/image-exceptions.txt"
    if not path.exists():
        path = root / "image-exceptions.txt"
    exception_lines = path.read_text().splitlines() if path.exists() else []
    compose_images = {}
    for service_name, service in compose.get("services", {}).items():
        image = service.get("image")
        if image:
            profiles = service.get("profiles") or []
            compose_images.setdefault(image, []).extend((service_name, profile) for profile in profiles)
            if not profiles:
                compose_images[image].append((service_name, None))
    for number, line in enumerate(exception_lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 5)
        if len(parts) != 6:
            raise ValueError(f"{path}:{number}: expected six pipe-separated fields")
        ref, cve, package, profile, expiry_field, reason = parts
        match = re.fullmatch(r"expires (\d{4}-\d{2}-\d{2})", expiry_field)
        if not match or not CVE.fullmatch(cve) or not package.strip() or not reason.strip():
            raise ValueError(f"{path}:{number}: malformed exception")
        try:
            expiry = date.fromisoformat(match.group(1))
        except ValueError as exc:
            raise ValueError(f"{path}:{number}: invalid expiry date") from exc
        if expiry < today:
            raise ValueError(f"{path}:{number}: expired exception for {ref} {cve}")
        if expiry > date.fromordinal(today.toordinal() + 30):
            raise ValueError(f"{path}:{number}: exception expiry exceeds 30 days")
        owners = compose_images.get(ref)
        if not owners:
            raise ValueError(f"{path}:{number}: exception image is not used in Compose: {ref}")
        owner_profiles = {owner_profile for _, owner_profile in owners}
        if None in owner_profiles or "observability" in owner_profiles:
            raise ValueError(f"{path}:{number}: exceptions are forbidden for default or observability images: {ref}")
        if profile not in ALLOWED_PROFILES or profile not in owner_profiles:
            raise ValueError(f"{path}:{number}: exception profile does not own image {ref}")
        if ref == image_ref:
            entries.append({"vulnerability": cve, "fix-state": "fixed", "package": {"name": package}})
    return {"ignore": entries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--today", type=date.fromisoformat)
    args = parser.parse_args()
    try:
        config = render_config(args.root, args.image_ref, args.today)
        args.output.write_text(yaml.safe_dump(config, sort_keys=False))
        return 0
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
