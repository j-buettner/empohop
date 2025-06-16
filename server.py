#!/usr/bin/env python3
"""
Simple HTTP server for serving the Planetary Health Knowledge Graph files.
This server handles CORS (Cross-Origin Resource Sharing) to allow loading JSON files.
"""

import http.server
import socketserver
import os
import sys
import argparse
import json

# Default port
PORT = 8080
# Default knowledge graph file
DEFAULT_KG_FILE = "data/processed/politics_of_ron_core_chunks_clean_knowledge_graph.json"

class CORSHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """
    Custom HTTP request handler with CORS headers.
    """
    
    def __init__(self, *args, kg_file=None, **kwargs):
        self.kg_file = kg_file or DEFAULT_KG_FILE
        super().__init__(*args, **kwargs)
    
    def end_headers(self):
        """
        Add CORS headers to allow all origins.
        """
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()
    
    def do_GET(self):
        """
        Handle GET requests with special handling for knowledge graph endpoint.
        """
        # Handle special endpoint for current knowledge graph (including query parameters)
        path_without_query = self.path.split('?')[0]
        if path_without_query == '/api/knowledge-graph' or path_without_query == '/api/knowledge-graph/':
            try:
                with open(self.kg_file, 'r', encoding='utf-8') as f:
                    data = f.read()
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(data.encode('utf-8'))
                return
            except FileNotFoundError:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                error_msg = json.dumps({"error": f"Knowledge graph file not found: {self.kg_file}"})
                self.wfile.write(error_msg.encode('utf-8'))
                return
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                error_msg = json.dumps({"error": f"Error reading knowledge graph: {str(e)}"})
                self.wfile.write(error_msg.encode('utf-8'))
                return
        
        # Default handling for other requests
        super().do_GET()
    
    def do_OPTIONS(self):
        """
        Handle OPTIONS requests for CORS preflight.
        """
        self.send_response(200)
        self.end_headers()

def run_server(port=PORT, kg_file=None):
    """
    Run the HTTP server on the specified port.
    """
    kg_file = kg_file or DEFAULT_KG_FILE
    
    # Create a handler class with the knowledge graph file
    class ConfiguredHandler(CORSHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, kg_file=kg_file, **kwargs)
    
    with socketserver.TCPServer(("", port), ConfiguredHandler) as httpd:
        print(f"Serving at http://localhost:{port}/")
        print(f"Knowledge graph file: {kg_file}")
        print(f"API endpoint: http://localhost:{port}/api/knowledge-graph")
        print("Press Ctrl+C to stop the server.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
            httpd.server_close()
            sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serve Planetary Health Knowledge Graph files")
    parser.add_argument("--port", "-p", type=int, default=PORT, help=f"Port to serve on (default: {PORT})")
    parser.add_argument("--kg-file", "-k", default=DEFAULT_KG_FILE, 
                       help=f"Knowledge graph JSON file to serve (default: {DEFAULT_KG_FILE})")
    
    args = parser.parse_args()
    
    # Check if knowledge graph file exists
    if not os.path.exists(args.kg_file):
        print(f"Error: Knowledge graph file not found: {args.kg_file}")
        print("Available files in data/processed/:")
        if os.path.exists("data/processed/"):
            for f in os.listdir("data/processed/"):
                if f.endswith("_knowledge_graph.json"):
                    print(f"  - {f}")
        sys.exit(1)
    
    run_server(args.port, args.kg_file)
