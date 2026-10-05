"""Adapters: the only code that imports provider SDKs (`litellm`, `redis`, `boto3`, ...) and the Postgres driver
for knowledge data. Each implements a port from `ports/`. `registry.py` builds them from `Settings`."""
