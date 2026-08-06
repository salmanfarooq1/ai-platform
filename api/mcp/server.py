"""
MCP server instance.

Creates the central MCPServer object that all tools, resources, and
prompts register themselves onto. Import this module to access the
shared server instance. Do not define tools or resources here.
"""
from mcp.server import MCPServer

mcp = MCPServer(
    "RAG-Platform",
    instructions=(
        "Compliance document research server. Use search_documents for "
        "single-namespace queries and multi_namespace_search for cross-regulation "
        "comparisons. Call list_namespaces first if you are unsure which scope to use."
    ),
)
mcp._dependency_overrides = {}

