#!/bin/bash
# Run all pilots sequentially after pilot 5 finishes.
# Each pilot overwrites its existing (incomplete) output directory.

set -e
cd "$(dirname "$0")"

echo "=== Waiting for pilot 5 to finish... ==="
while pgrep -f "Pilot texts 5" > /dev/null; do
    sleep 30
    echo "  still running pilot 5..."
done
echo "  Pilot 5 done."

echo ""
echo "=== Pilot 1: Protected Areas ==="
KG_CONTEXT=protected_areas python llm_processor.py \
    "data/extracted/pilot_texts/Pilot texts 1 [Protected Areas]_chunks.json" \
    --output-dir data/processed/pilot_1_protected_areas \
    --backend external

echo ""
echo "=== Pilot 2: Sustainable Agriculture ==="
KG_CONTEXT=community_based_forestry python llm_processor.py \
    "data/extracted/pilot_texts/Pilot texts 2 [Sustainable agriculture]_chunks.json" \
    --output-dir data/processed/pilot_2_sustainable_agriculture \
    --backend external

echo ""
echo "=== Pilot 3: Beyond GDP ==="
KG_CONTEXT=beyond_gdp python llm_processor.py \
    "data/extracted/pilot_texts/Pilot texts 3 [Beyond GDP measurement]_chunks.json" \
    --output-dir data/processed/pilot_3_beyond_gdp \
    --backend external

echo ""
echo "=== Pilot 4: Ecovillages ==="
KG_CONTEXT=ecovillages python llm_processor.py \
    "data/extracted/pilot_texts/Pilot texts 4 [ecovillages]_chunks.json" \
    --output-dir data/processed/pilot_4_ecovillages \
    --backend external

echo ""
echo "=== All pilots complete ==="
