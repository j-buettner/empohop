#!/usr/bin/env python3
"""
Regenerate per-type JSON and CSV files from existing knowledge_graph.json files.
Run this after a KG file is available but individual type files are missing.

Usage:
    python regenerate_outputs.py                    # all pilots
    python regenerate_outputs.py data/processed/pilot_1_protected_areas
"""

import csv
import json
import os
import sys
import glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Fields to include in CSV per entity type
CSV_FIELDS = {
    "events": ["id", "title", "year", "type", "description", "supporting_text", "source_chunk"],
    "actors": ["id", "name", "type", "description", "supporting_text", "source_chunk"],
    "concepts": ["id", "name", "type", "description", "supporting_text", "source_chunk"],
    "expressions": ["id", "title", "year", "authors", "description", "supporting_text", "source_chunk"],
    "locations": ["id", "name", "type", "description", "supporting_text", "source_chunk"],
}


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  wrote {path}")


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            # Flatten list fields for CSV
            flat = {}
            for k, v in row.items():
                if isinstance(v, list):
                    flat[k] = "; ".join(str(x) for x in v)
                elif isinstance(v, dict):
                    flat[k] = json.dumps(v)
                else:
                    flat[k] = v
            writer.writerow(flat)
    print(f"  wrote {path}")


def regenerate(pilot_dir):
    kg_files = glob.glob(os.path.join(pilot_dir, "*_knowledge_graph.json"))
    kg_files = [f for f in kg_files if "/raw/" not in f]
    if not kg_files:
        print(f"  No KG file found in {pilot_dir}")
        return

    kg_file = kg_files[0]
    stem = os.path.basename(kg_file).replace("_knowledge_graph.json", "")
    print(f"\n{os.path.basename(pilot_dir)} (stem: {stem})")

    with open(kg_file, encoding="utf-8") as f:
        kg = json.load(f)

    for entity_type, fields in CSV_FIELDS.items():
        entities = kg.get(entity_type, [])
        json_path = os.path.join(pilot_dir, f"{stem}_{entity_type}.json")
        csv_path  = os.path.join(pilot_dir, f"{stem}_{entity_type}.csv")
        write_json(json_path, entities)
        write_csv(csv_path, entities, fields)

    # Relationships
    rels = kg.get("relationships", [])
    write_json(os.path.join(pilot_dir, f"{stem}_relationships.json"), rels)


def main():
    if len(sys.argv) > 1:
        dirs = sys.argv[1:]
    else:
        dirs = sorted(glob.glob(os.path.join(BASE_DIR, "data", "processed", "pilot_*")))

    for d in dirs:
        regenerate(d)

    print("\nDone.")


if __name__ == "__main__":
    main()
