#!/bin/bash
# Remove synthetic/test documents from the legal namespace.
# These were ingested by the old ingest_compliance_corpus.py and are 
# LLM-generated approximations — replaced by real statutory text.

PSQL="docker exec postgres psql -U postgres -d rag_platform"

SYNTHETIC=("gdpr-policy-v1" "employee-handbook-v3" "compliance-api-spec-v2")

echo "Removing synthetic documents from legal namespace..."
for doc_id in "${SYNTHETIC[@]}"; do
    result=$($PSQL -c "DELETE FROM documents WHERE document_id = '${doc_id}' AND namespace = 'legal' RETURNING id;" 2>&1)
    count=$(echo "$result" | grep -c "^(" || echo 0)
    echo "  removed: $doc_id"
done

echo ""
echo "Final corpus state:"
$PSQL -c "SELECT namespace, document_id, COUNT(*) as chunks FROM documents WHERE namespace IN ('legal','kyc_aml') GROUP BY namespace, document_id ORDER BY namespace, document_id;"
echo ""
$PSQL -c "SELECT namespace, COUNT(*) as total_chunks FROM documents WHERE namespace IN ('legal','kyc_aml') GROUP BY namespace;"
echo "Done."
