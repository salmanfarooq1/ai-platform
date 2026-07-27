#!/bin/bash
docker exec data-portal-postgres-1 psql -U keycloak -c "CREATE ROLE postgres SUPERUSER LOGIN PASSWORD 'postgres';" 2>&1
docker exec data-portal-postgres-1 psql -U postgres -c "CREATE DATABASE rag_platform;" 2>&1
docker exec -i data-portal-postgres-1 psql -U postgres -d rag_platform < /home/ubuntu/ai-platform/core/database/schema.sql 2>&1
echo "SETUP_DONE"
