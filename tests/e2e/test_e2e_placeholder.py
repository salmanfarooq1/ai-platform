"""
Keeps the e2e tier collectible before the API app exists end-to-end.
Delete this file once real e2e tests land - e.g. test_chat_flow.py posting
a real compliance question to /api/chat and asserting on the full response shape.
"""
import pytest


@pytest.mark.skip(reason="API app not assembled yet")
def test_e2e_placeholder():
    pass
