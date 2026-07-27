#!/bin/bash
# Remove the 6 blocked ecfr.gov files and their ingested chunks from the DB.
# These contained CAPTCHA/IP-challenge HTML, not real regulatory text.

REAL_DIR="/home/ubuntu/ai-platform/data/compliance/real"
PSQL="docker exec postgres psql -U postgres -d rag_platform"

BLOCKED_LEGAL=("hipaa_164_502" "hipaa_164_514")
BLOCKED_KYC=("cfr_1010_230" "cfr_1010_311" "cfr_1010_430" "cfr_1020_320")

echo "Removing blocked ecfr.gov files and their DB chunks..."

for doc_id in "${BLOCKED_LEGAL[@]}"; do
    rm -f "$REAL_DIR/${doc_id}.md"
    $PSQL -c "DELETE FROM documents WHERE document_id = '${doc_id}' AND namespace = 'legal';" 2>&1
    echo "  removed: $doc_id (legal)"
done

for doc_id in "${BLOCKED_KYC[@]}"; do
    rm -f "$REAL_DIR/kyc_aml/${doc_id}.md"
    $PSQL -c "DELETE FROM documents WHERE document_id = '${doc_id}' AND namespace = 'kyc_aml';" 2>&1
    echo "  removed: $doc_id (kyc_aml)"
done

echo ""
echo "Remaining chunk counts:"
$PSQL -c "SELECT namespace, COUNT(*) FROM documents GROUP BY namespace;" 2>&1
echo "Done."
