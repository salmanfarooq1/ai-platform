"""
MCP prompt definitions.

Prompts are reusable workflow templates surfaced as clickable options in
MCP client interfaces. They guide the LLM through multi-step tasks by
providing step-by-step instructions as the initial message.
"""
from api.mcp.server import mcp


@mcp.prompt("compliance-research")
async def prompt_compliance_research(question: str, namespace: str = "legal") -> str:
    """Guided compliance research workflow.

    Generates a prompt that instructs the LLM to first check what
    namespaces are available, then search the right one, then
    synthesize a cited answer.
    """
    return (
        f"I need to research a compliance question: '{question}'\n\n"
        f"Please follow these steps:\n"
        f"1. Call list_namespaces to see what document scopes are available.\n"
        f"2. Search the '{namespace}' namespace (or whichever is most relevant) "
        f"using search_documents with the question.\n"
        f"3. If the question spans multiple regulations, use multi_namespace_search.\n"
        f"4. Synthesize a clear answer citing the specific chunks you found.\n"
        f"5. If you cannot find relevant context, say so explicitly."
    )


@mcp.prompt("cost-audit")
async def prompt_cost_audit(days: int = 30) -> str:
    """Cost audit workflow for reviewing LLM spend."""
    return (
        f"I need to audit LLM costs for the past {days} days.\n\n"
        f"1. Call get_cost_summary with days={days} to see per-day breakdown.\n"
        f"2. Identify which endpoints consume the most tokens.\n"
        f"3. Flag any days where cost_usd exceeds $1.00.\n"
        f"4. Suggest optimizations if agent queries dominate spend."
    )
