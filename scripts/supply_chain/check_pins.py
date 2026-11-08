"""Validate parsed registry references, excluding YAML and Dockerfile comments."""
import re
import shlex
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_COMPOSE = "docker-compose.yml"
REFERENCE = re.compile(
    r"(?:[a-zA-Z0-9][a-zA-Z0-9._-]*(?::[0-9]+)?/)*"
    r"[a-z0-9][a-z0-9._-]*:[a-zA-Z0-9_][a-zA-Z0-9_.-]*@sha256:[0-9a-f]{64}"
)


def assert_compose_inventory(root: Path) -> None:
    active = root / ACTIVE_COMPOSE
    candidates = {
        path.name
        for pattern in ("*compose*.yml", "*compose*.yaml")
        for path in root.glob(pattern)
        if path.is_file() and path != active
    }
    if candidates:
        names = ", ".join(sorted(candidates))
        raise ValueError(
            f"unregistered root Compose files: {names}; only {ACTIVE_COMPOSE} is active"
        )


def load_active_compose(root: Path) -> dict:
    """Load the sole active Compose file after rejecting unscanned indirection."""
    assert_compose_inventory(root)
    compose = yaml.safe_load((root / "docker-compose.yml").read_text())
    if not isinstance(compose, dict):
        raise ValueError("active Compose file must contain a mapping")
    if "include" in compose:
        raise ValueError("top-level Compose include is not registered for image validation")
    services = compose.get("services", {})
    if not isinstance(services, dict):
        raise ValueError("Compose services must be a mapping")
    for name, service in services.items():
        if not isinstance(service, dict):
            raise ValueError(f"Compose service {name} must be a mapping")
        if "extends" in service:
            raise ValueError(f"Compose service {name} uses unregistered extends")
    return compose


def compose_references(root: Path):
    compose = load_active_compose(root)
    for name, service in compose.get("services", {}).items():
        if "image" in service:
            yield f"docker-compose.yml:{name}", service["image"]


def built_services(root: Path) -> list[str]:
    compose = load_active_compose(root)
    services = []
    for name, service in compose.get("services", {}).items():
        if "build" in service:
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name) or "image" in service:
                raise ValueError("built services require a valid service name and an implicit local image")
            services.append(name)
    return sorted(services)


def references(root: Path):
    yield from compose_references(root)
    for file in ("tests.yml", "frontend.yml"):
        workflow = yaml.safe_load((root / ".github/workflows" / file).read_text())
        for name, job in workflow.get("jobs", {}).items():
            if container := job.get("container"):
                yield f"{file}:{name}:container", container if isinstance(container, str) else container["image"]
            for service, value in job.get("services", {}).items():
                yield f"{file}:{name}:{service}", value["image"]
    dockerfiles = [path for pattern in ("Dockerfile*", "*.Dockerfile") for path in root.rglob(pattern)
                   if path.is_file() and not {"node_modules", ".git", "scratch"}.intersection(path.parts)]
    for dockerfile in sorted(set(dockerfiles)):
        yield from dockerfile_references(root, dockerfile)


def dockerfile_references(root: Path, dockerfile: Path):
    stages = set()
    for number, line in enumerate(dockerfile.read_text().splitlines(), 1):
        location = f"{dockerfile.relative_to(root)}:{number}"
        if re.match(r"^\s*COPY\s+", line, re.IGNORECASE):
            for token in shlex.split(line, comments=True)[1:]:
                if token.startswith("--from="):
                    source = token.split("=", 1)[1]
                    if source.lower() not in stages and not source.isdecimal():
                        yield location, source
        if not re.match(r"^\s*FROM\s+", line, re.IGNORECASE):
            continue
        tokens = shlex.split(line, comments=True)
        parts = tokens[1:]
        if parts and parts[0].startswith("--platform="):
            parts = parts[1:]
        if not parts:
            raise ValueError(f"{location}: missing FROM image")
        image = parts[0]
        if image.lower() not in stages and image.lower() != "scratch":
            yield location, image
        if len(parts) == 3 and parts[1].upper() == "AS":
            stages.add(parts[2].lower())
        elif len(parts) != 1:
            raise ValueError(f"{location}: invalid FROM instruction")


def main() -> int:
    problems = []
    try:
        if sys.argv[1:] == ["--built-services"]:
            print("\n".join(built_services(ROOT)))
            return 0
        compose_only = sys.argv[1:] == ["--compose-images"]
        found = list(compose_references(ROOT) if compose_only else references(ROOT))
        for location, image in found:
            if not compose_only:
                print(f"{location}: {image}")
            if not isinstance(image, str) or not REFERENCE.fullmatch(image):
                problems.append(f"{location}: expected a tag and complete sha256 digest")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, yaml.YAMLError) as exc:
        problems.append(f"image references could not be validated: {exc}")
    for problem in problems:
        print(problem)
    if not problems and compose_only:
        print("\n".join(sorted({image for _, image in found})))
    elif not problems:
        print("all registry image references have a tag and @sha256 digest")
    return int(bool(problems))


if __name__ == "__main__":
    sys.exit(main())
