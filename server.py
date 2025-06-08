#!/usr/bin/env python3
"""
Simple HTTP server for serving the Planetary Health Knowledge Graph files.
This server handles CORS (Cross-Origin Resource Sharing) to allow loading JSON files.
"""

import http.server
import socketserver
import os
import sys

# Default port
PORT = 8080

class CORSHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """
    Custom HTTP request handler with CORS headers.
    """
    
    def end_headers(self):
        """
        Add CORS headers to allow all origins.
        """
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()
    
    def do_OPTIONS(self):
        """
        Handle OPTIONS requests for CORS preflight.
        """
        self.send_response(200)
        self.end_headers()

def run_server(port=PORT):
    """
    Run the HTTP server on the specified port.
    """
    handler = CORSHTTPRequestHandler
    
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Serving at http://localhost:{port}/")
        print("Press Ctrl+C to stop the server.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
            httpd.server_close()
            sys.exit(0)

if __name__ == "__main__":
    # Get port from command line argument if provided
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port number: {sys.argv[1]}")
            print(f"Using default port {PORT}")
            port = PORT
    else:
        port = PORT
    
    run_server(port)
