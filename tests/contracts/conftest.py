"""The contract suites build their own adapters from the sync fixtures in tests/db_fixtures.py (a throwaway
Postgres as `gap_app`, the test Redis), so every parameter of a suite runs in the same event loop."""
