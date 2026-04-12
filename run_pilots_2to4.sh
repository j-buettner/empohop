#!/bin/bash
# Resume sequential pilot runs from pilot 2 (pilot 1 already completed).

set -e
cd "$(dirname "$0")"

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
echo "=== Pilots 2-4 complete ==="
