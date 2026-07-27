#!/bin/bash
docker exec postgres psql -U postgres -d rag_platform -c "SELECT namespace, document_id, COUNT(*) as chunks FROM documents GROUP BY namespace, document_id ORDER BY namespace, document_id;"
