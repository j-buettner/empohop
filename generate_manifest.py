#!/usr/bin/env python3
"""
Generate data/manifest.json listing all available knowledge graphs.

Run this after processing new pilots:
    python generate_manifest.py

The manifest is consumed by the UI visualizations to populate the
pilot-switcher dropdown and load KG files directly by path (no server needed).
"""

import glob
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
OUT_FILE = os.path.join(BASE_DIR, "data", "manifest.json")

# Human-readable labels keyed by directory name.
# Add entries here when new pilots are added.
LABELS = {
    "pilot_1_protected_areas":        "Pilot 1 — Protected Areas",
    "pilot_2_sustainable_agriculture": "Pilot 2 — Sustainable Agriculture",
    "pilot_3_beyond_gdp":              "Pilot 3 — Beyond GDP",
    "pilot_4_ecovillages":             "Pilot 4 — Ecovillages & Transition Towns",
    "pilot_5_environmental_movement":  "Pilot 5 — Environmental Movement & Governance",
}


def main():
    entries = []
    pattern = os.path.join(PROCESSED_DIR, "**", "*_knowledge_graph.json")
    for kg_abs in sorted(glob.glob(pattern, recursive=True)):
        if os.path.sep + "raw" + os.path.sep in kg_abs:
            continue
        dir_name = os.path.basename(os.path.dirname(kg_abs))
        # Path relative to the code_base root (used as fetch URL from the UI)
        kg_rel = os.path.relpath(kg_abs, BASE_DIR)
        label = LABELS.get(dir_name) or dir_name.replace("_", " ").title()
        entries.append({"id": dir_name, "label": label, "path": kg_rel})

    if not entries:
        print("No knowledge graph files found in", PROCESSED_DIR, file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(entries)} entries to {OUT_FILE}")
    for e in entries:
        print(f"  {e['id']}: {e['path']}")


if __name__ == "__main__":
    main()
