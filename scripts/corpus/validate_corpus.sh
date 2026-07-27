#!/bin/bash
# Validate all fetched files - check for placeholder/error content

REAL_DIR="/home/ubuntu/ai-platform/data/compliance/real"

echo "=== FILE SIZE REPORT ==="
for f in "$REAL_DIR"/*.md "$REAL_DIR"/kyc_aml/*.md; do
    size=$(wc -c < "$f")
    chars=$(wc -m < "$f")
    name=$(basename "$f")
    if [ "$size" -lt 500 ]; then
        echo "  SUSPECT  $name  ($size bytes)"
        echo "  --- Content preview ---"
        head -5 "$f"
        echo "  --- End ---"
    else
        echo "  OK       $name  ($size bytes)"
    fi
done

echo ""
echo "=== SPOT CHECKS ==="
echo "--- Art.33 (72h rule) ---"
grep -c "72" "$REAL_DIR/gdpr_art_33.md" && echo "Found '72' in Art.33"

echo "--- CCPA 1798.82 (30 days) ---"
grep -c "30" "$REAL_DIR/ccpa_1798_82.md" && echo "Found '30' in 1798.82"

echo "--- Art.83 (20 million / 4%) ---"
grep -c "20.000.000\|20,000,000\|4 %" "$REAL_DIR/gdpr_art_83.md" && echo "Found fine amounts in Art.83"
