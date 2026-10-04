"""API version prefix. Every product route is mounted under this prefix."""

API_PREFIX = "/v1"

# Paths that stay unversioned for the platform health check.
UNVERSIONED_PATHS = ("/", "/health")
