"""
api/agent/
Agent layer for the RAG platform using LangGraph.

Two LLM roles in one graph: a reasoning and retrieval role that decides what
to search for, and an optional verifier role that checks the drafted
answer against what was retrieved.
"""
