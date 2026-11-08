#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p sbom
poetry run cyclonedx-py environment --of JSON --output-file sbom/python.cdx.json --validate
(cd ui && npm exec --yes --package=@cyclonedx/cyclonedx-npm@6.0.1 -- cyclonedx-npm --output-format JSON --output-file ../sbom/npm.cdx.json)
poetry run python - <<'PY'
import json
from pathlib import Path
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator
for path in sorted(Path('sbom').glob('*.cdx.json')):
    raw = path.read_text()
    document = json.loads(raw)
    assert document['bomFormat'] == 'CycloneDX'
    schemas = {'1.5': SchemaVersion.V1_5, '1.6': SchemaVersion.V1_6}
    assert document['specVersion'] in schemas
    assert document['components']
    error = JsonStrictValidator(schemas[document['specVersion']]).validate_str(raw)
    assert error is None, str(error)
    print(f"{path}: spec {document['specVersion']}, {len(document['components'])} components; strict schema validation passed")
PY
