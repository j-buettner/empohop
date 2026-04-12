#!/usr/bin/env python3
"""
Flask-based HTTP server for the Planetary Health Knowledge Graph visualisations.

Development:
    python server.py [kg_file] [--port PORT]

Production (with gunicorn):
    KG_FILE=data/processed/my_kg.json gunicorn -w 1 server:app

The module-level ``app`` object is the WSGI entry point consumed by gunicorn.
To serve a non-default knowledge-graph file set the KG_FILE environment variable
or pass the path on the command line when running directly.
"""

import argparse
import json
import logging
import os
import sys
from typing import Optional

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from config import DEFAULT_KG_FILE
from logging_config import configure_logging

logger = logging.getLogger(__name__)

# Base directory — all static files are served relative to this
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_critic_file(kg_file: str) -> Optional[str]:
    """
    Derive the critic-evaluation file path from the knowledge-graph file path.
    Searches for a matching critic file in:
      1. data/critic_results_<suffix>/ — sibling of the KG output dir
      2. data/critic_results/           — default location
    Returns ``None`` if no matching file exists.
    """
    if kg_file.endswith("_knowledge_graph.json"):
        base = kg_file[: -len("_knowledge_graph.json")]
    else:
        base = os.path.splitext(kg_file)[0]
        if base.endswith("_knowledge_graph"):
            base = base[: -len("_knowledge_graph")]

    stem = os.path.basename(base)

    # Derive sibling critic dir from KG dir (e.g. data/processed_v2 → data/critic_results_v2)
    kg_dir = os.path.dirname(kg_file)
    kg_dir_name = os.path.basename(kg_dir)  # e.g. "processed_v2"
    suffix = kg_dir_name[len("processed"):] if kg_dir_name.startswith("processed") else ""
    sibling_critic_dir = os.path.join(os.path.dirname(kg_dir), f"critic_results{suffix}")

    for critic_dir in [sibling_critic_dir, "data/critic_results"]:
        candidate = os.path.join(critic_dir, f"{stem}_critic_evaluation.json")
        if os.path.exists(candidate):
            return candidate
    return None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(kg_file: str = DEFAULT_KG_FILE) -> Flask:
    """
    Create and return the configured Flask application.

    Args:
        kg_file: Path to the knowledge-graph JSON file to expose via the API.
    """
    _UI_DIR = os.path.join(_BASE_DIR, "ui")
    flask_app = Flask(__name__, static_folder=_UI_DIR, static_url_path="")
    CORS(flask_app)

    critic_file = _infer_critic_file(kg_file)

    # ------------------------------------------------------------------ #
    # API routes
    # ------------------------------------------------------------------ #

    @flask_app.route("/api/knowledge-graph")
    def knowledge_graph():
        try:
            with open(kg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return jsonify(data)
        except FileNotFoundError:
            return jsonify({"error": f"Knowledge graph file not found: {kg_file}"}), 404
        except Exception as exc:
            logger.exception("Error reading knowledge graph")
            return jsonify({"error": str(exc)}), 500

    @flask_app.route("/api/critic-data")
    def critic_data():
        if not critic_file or not os.path.exists(critic_file):
            return jsonify({"error": "Critic data not available"}), 404
        try:
            with open(critic_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return jsonify(data)
        except Exception as exc:
            logger.exception("Error reading critic data")
            return jsonify({"error": str(exc)}), 500

    @flask_app.route("/api/manifest")
    def manifest():
        manifest_file = os.path.join(_BASE_DIR, "data", "manifest.json")
        if not os.path.exists(manifest_file):
            return jsonify({"error": "manifest.json not found — run generate_manifest.py"}), 404
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @flask_app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "kg_file": kg_file})

    # ------------------------------------------------------------------ #
    # Static / index route
    # ------------------------------------------------------------------ #

    @flask_app.route("/")
    def index():
        return send_from_directory(_UI_DIR, "index.html")

    # Expose data directory (manifest.json and KG files) at /data/<path>
    # so that the relative URL ../../data/manifest.json from ui/visualization/*/
    # resolves correctly on the dev server too.
    @flask_app.route("/data/<path:filename>")
    def data_files(filename):
        return send_from_directory(os.path.join(_BASE_DIR, "data"), filename)

    # Expose schema JSON files (used by both the pipeline and the UI)
    @flask_app.route("/schema/json-schema/<path:filename>")
    def schema_json(filename):
        return send_from_directory(os.path.join(_BASE_DIR, "schema", "json-schema"), filename)

    logger.info("Knowledge graph file : %s", kg_file)
    if critic_file:
        logger.info("Critic data file     : %s", critic_file)
    else:
        logger.info("Critic data          : not available")

    return flask_app


# ---------------------------------------------------------------------------
# Module-level app for gunicorn  (gunicorn server:app)
# ---------------------------------------------------------------------------

app = create_app()


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    configure_logging()

    parser = argparse.ArgumentParser(
        description="Serve Planetary Health Knowledge Graph files"
    )
    parser.add_argument(
        "kg_file",
        nargs="?",
        default=DEFAULT_KG_FILE,
        help=f"Knowledge graph JSON file to serve (default: {DEFAULT_KG_FILE})",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8080,
        help="Port to serve on (default: 8080)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.kg_file):
        logger.error("Knowledge graph file not found: %s", args.kg_file)
        available = [
            f"  data/processed/{f}"
            for f in os.listdir("data/processed")
            if f.endswith("_knowledge_graph.json")
        ] if os.path.exists("data/processed") else []
        if available:
            logger.info("Available files:\n%s", "\n".join(available))
        sys.exit(1)

    dev_app = create_app(args.kg_file)
    logger.info("Dev server running at http://localhost:%d/", args.port)
    logger.info("Use gunicorn for production: gunicorn -w 1 server:app")
    dev_app.run(host="localhost", port=args.port, debug=False)
