"""End-to-end: the MCP server is mounted under /v1/mcp and speaks MCP over SSE."""
import asyncio
import json
from uuid import UUID

from api.mcp.context import current_principal
from api.mcp.server import mcp
from core.identity.models import Principal
from tests.e2e.conftest import eventually

EXPECTED_TOOLS = {"list_namespaces", "search_documents", "multi_namespace_search", "get_ingestion_status", "get_cost_summary"}


async def test_in_process_server_lists_the_tools(app):
    tools = await mcp.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS


async def test_in_process_tool_reads_the_real_database(client, app, tenant_a, fake_llm, fake_embeddings):
    await client.post("/v1/ingest", params={"namespace": "legal"},
                      files={"file": ("gdpr.md", b"# GDPR\n\nBreach notification within 72 hours.\n", "text/markdown")})

    # The session's principal is what SseApp binds from the verified credential.
    token = current_principal.set(Principal(
        id=UUID(tenant_a.principal_id), tenant_id=UUID(tenant_a.id), kind="service", scopes=frozenset({"query", "kb:read"}),
    ))
    try:
        result = await mcp.call_tool("get_ingestion_status", {"namespace": "legal"})
    finally:
        current_principal.reset(token)

    payload = json.loads(_text(result))
    assert payload["namespace"] == "legal"
    assert payload["document_count"] == 1
    assert payload["latest_document"]["document_id"] == "gdpr.md"


def _text(result) -> str:
    return result.content[0].text


class SseProbe:
    """Open GET /v1/mcp/sse straight against the ASGI app and keep the stream open."""

    def __init__(self, app, headers: dict[str, str] | None = None):
        self.app = app
        self.extra_headers = headers or {}
        self.chunks: list[bytes] = []
        self.status: int | None = None
        self.headers: dict[str, str] = {}
        self._disconnect = asyncio.Event()
        self.task: asyncio.Task | None = None

    async def __aenter__(self):
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
            "path": "/v1/mcp/sse", "raw_path": b"/v1/mcp/sse", "query_string": b"", "root_path": "", "scheme": "http",
            "headers": [(b"host", b"test"), (b"accept", b"text/event-stream"),
                        *[(k.lower().encode(), v.encode()) for k, v in self.extra_headers.items()]],
            "server": ("test", 80), "client": ("127.0.0.1", 1234), "state": {},
        }

        sent_request = False

        async def receive():
            nonlocal sent_request
            if not sent_request:  # a GET has an empty body, delivered first as ASGI requires
                sent_request = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await self._disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                self.status = message["status"]
                self.headers = {k.decode().lower(): v.decode() for k, v in message["headers"]}
            elif message["type"] == "http.response.body":
                self.chunks.append(message.get("body", b""))

        self.task = asyncio.create_task(self.app(scope, receive, send))
        return self

    async def __aexit__(self, *exc):
        self._disconnect.set()
        assert self.task is not None
        try:
            await asyncio.wait_for(self.task, timeout=5)
        except asyncio.TimeoutError:
            self.task.cancel()

    @property
    def text(self) -> str:
        return b"".join(self.chunks).decode()


async def test_sse_endpoint_is_versioned_and_handles_an_mcp_session(client, app, tenant_a):
    async with SseProbe(app, tenant_a.headers("query_only")) as sse:
        await eventually(lambda: "event: endpoint" in sse.text)
        assert sse.status == 200
        assert sse.headers["content-type"].startswith("text/event-stream")

        data_line = next(line for line in sse.text.splitlines() if line.startswith("data: /v1/mcp/messages/"))
        endpoint = data_line.removeprefix("data: ")
        assert "session_id=" in endpoint

        initialize = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "e2e-test", "version": "0"}},
        }
        resp = await client.post(endpoint, json=initialize)
        assert resp.status_code == 202

        await eventually(lambda: '"serverInfo"' in sse.text)
        message_line = next(line for line in sse.text.splitlines() if line.startswith("data: {"))
        reply = json.loads(message_line.removeprefix("data: "))
        assert reply["id"] == 1
        assert reply["result"]["serverInfo"]["name"] == "RAG-Platform"


async def test_unversioned_mcp_paths_do_not_exist(client):
    assert (await client.get("/mcp/sse")).status_code == 404
    assert (await client.post("/mcp/messages/?session_id=x", json={})).status_code == 404
