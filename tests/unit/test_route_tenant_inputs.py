"""Strict rule 1: no route reads a tenant from request input (requirement 5, edge cases)."""
import ast
import inspect
from pathlib import Path

from api.main import create_app
from api.models import schemas

ROOT = Path(__file__).resolve().parents[2]
ROUTER_FILES = sorted((ROOT / "api" / "routers").glob("*.py")) + [ROOT / "api" / "agent" / "router.py"]
FORBIDDEN_NAMES = {"tenant_id", "tenant", "x_tenant_id", "principal_id"}


def _schema_properties(spec: dict, schema: dict) -> set[str]:
    if "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    return set(schema.get("properties", {}))


def test_no_operation_in_the_openapi_contract_accepts_a_tenant_from_the_caller():
    """Query, header, path and body fields of every operation, read from the published contract."""
    spec = create_app().openapi()
    operations = 0
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            operations += 1
            for param in op.get("parameters", []):
                assert param["name"].lower().replace("-", "_") not in FORBIDDEN_NAMES, f"{method} {path}: {param['name']}"
            for content in op.get("requestBody", {}).get("content", {}).values():
                fields = _schema_properties(spec, content.get("schema", {}))
                assert not fields & FORBIDDEN_NAMES, f"{method} {path} body has {fields & FORBIDDEN_NAMES}"
    assert operations >= 10


def test_request_models_have_no_tenant_field():
    for name, cls in inspect.getmembers(schemas, inspect.isclass):
        fields = getattr(cls, "model_fields", {})
        assert not set(fields) & FORBIDDEN_NAMES, name
    from api.agent.router import AgentRequest
    from api.routers.feedback import FeedbackRequest

    assert not set(AgentRequest.model_fields) & FORBIDDEN_NAMES
    assert not set(FeedbackRequest.model_fields) & FORBIDDEN_NAMES


def test_in_routers_every_use_of_tenant_id_derives_from_the_principal():
    """Source-level check: `tenant_id` appears in a router only as `principal.tenant_id` or a local
    assigned from it, never as a function parameter, a Query/Form/Header, or `request.<anything>`."""
    for path in ROUTER_FILES:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args + node.args.kwonlyargs]
                assert "tenant_id" not in args, f"{path.name}:{node.name} takes tenant_id"
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "tenant_id" for t in node.targets):
                assert ast.unparse(node.value) == "principal.tenant_id", f"{path.name}: {ast.unparse(node)}"
            if isinstance(node, ast.Attribute) and node.attr == "tenant_id":
                assert ast.unparse(node.value) == "principal", f"{path.name}: {ast.unparse(node)}"
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value.lower() not in {"x-tenant-id", "x_tenant_id"}, path.name
