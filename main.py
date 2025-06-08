import argparse
import json
import logging
import os
import sys
import webbrowser
from http.server import HTTPServer

from human_review import ReviewManager, ReviewServer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Main function to run the human review interface"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run the human review interface for planetary health knowledge graph")
    parser.add_argument("--tasks-file", default="data/review/review_tasks.json", help="Path to the review tasks file")
    parser.add_argument("--output-dir", default="data/review/corrected", help="Directory to save corrected data")
    parser.add_argument("--host", default="localhost", help="Host to run the server on")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
    parser.add_argument("--no-browser", action="store_true", help="Don't open the browser automatically")
    args = parser.parse_args()
    
    try:
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(args.tasks_file), exist_ok=True)
        os.makedirs(args.output_dir, exist_ok=True)
        
        # Initialize review manager
        review_manager = ReviewManager(args.tasks_file, args.output_dir)
        
        # Set up the server
        server_address = (args.host, args.port)
        ReviewServer.review_manager = review_manager
        httpd = HTTPServer(server_address, ReviewServer)
        
        # Start the server
        url = f"http://{args.host}:{args.port}"
        logger.info(f"Starting server at {url}")
        
        # Open the browser
        if not args.no_browser:
            webbrowser.open(url)
        
        # Run the server
        httpd.serve_forever()
        
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"Error running server: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
