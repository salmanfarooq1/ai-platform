"""Token budgets for the agent's model calls. The models themselves come from the `ChatModelPort` adapter
(`adapters/litellm_chat.py`), so this module imports no provider.

The port does not enforce anything: every call on the returned model is preceded by `enforce(model.invoke)`
in the graph nodes (see `_model_allowed` in `graph.py`).
"""

AGENT_MAX_TOKENS = 4000
VERIFIER_MAX_TOKENS = 500
