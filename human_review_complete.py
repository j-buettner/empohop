import argparse
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional, Any
import uuid
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ReviewTask:
    """Class representing a human review task"""
    
    def __init__(self, task_data: Dict):
        """
        Initialize a review task
        
        Args:
            task_data: Task data from the review tasks file
        """
        self.task_id = task_data.get("task_id", str(uuid.uuid4()))
        self.priority = task_data.get("priority", "medium")
        self.original_text = task_data.get("original_text", "")
        self.document_metadata = task_data.get("document_metadata", {})
        self.extracted_data = task_data.get("extracted_data", {})
        self.critic_evaluation = task_data.get("critic_evaluation", {})
        self.highlighted_issues = task_data.get("highlighted_issues", [])
        self.review_questions = task_data.get("review_questions", [])
        self.status = task_data.get("status", "pending_review")
        self.created_at = task_data.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self.reviewed_at = task_data.get("reviewed_at")
        self.reviewer_notes = task_data.get("reviewer_notes", "")
        self.corrected_data = task_data.get("corrected_data", {})
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "task_id": self.task_id,
            "priority": self.priority,
            "original_text": self.original_text,
            "document_metadata": self.document_metadata,
            "extracted_data": self.extracted_data,
            "critic_evaluation": self.critic_evaluation,
            "highlighted_issues": self.highlighted_issues,
            "review_questions": self.review_questions,
            "status": self.status,
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
            "reviewer_notes": self.reviewer_notes,
            "corrected_data": self.corrected_data
        }
    
    def mark_as_reviewed(self, corrected_data: Dict, reviewer_notes: str):
        """
        Mark the task as reviewed
        
        Args:
            corrected_data: Corrected data from the reviewer
            reviewer_notes: Notes from the reviewer
        """
        self.status = "reviewed"
        self.reviewed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.reviewer_notes = reviewer_notes
        self.corrected_data = corrected_data

class ReviewManager:
    """Class for managing human review tasks"""
    
    def __init__(self, tasks_file: str, output_dir: str):
        """
        Initialize the review manager
        
        Args:
            tasks_file: Path to the review tasks file
            output_dir: Directory to save reviewed tasks
        """
        self.tasks_file = tasks_file
        self.output_dir = output_dir
        self.tasks = []
        
        # Load tasks
        self.load_tasks()
    
    def load_tasks(self):
        """Load tasks from the tasks file"""
        try:
            with open(self.tasks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Extract tasks from the data
                tasks_data = data.get("review_tasks", [])
                
                # Create ReviewTask objects
                self.tasks = [ReviewTask(task_data) for task_data in tasks_data]
                
                logger.info(f"Loaded {len(self.tasks)} review tasks from {self.tasks_file}")
                
        except FileNotFoundError:
            logger.warning(f"Tasks file not found: {self.tasks_file}")
            self.tasks = []
        except Exception as e:
            logger.error(f"Error loading review tasks: {str(e)}")
            self.tasks = []
    
    def save_tasks(self):
        """Save tasks to the tasks file"""
        try:
            # Convert tasks to dictionaries
            tasks_data = [task.to_dict() for task in self.tasks]
            
            # Create output directory if it doesn't exist
            os.makedirs(os.path.dirname(self.tasks_file), exist_ok=True)
            
            # Save to file
            with open(self.tasks_file, 'w', encoding='utf-8') as f:
                json.dump({"review_tasks": tasks_data}, f, indent=2)
                
            logger.info(f"Saved {len(self.tasks)} review tasks to {self.tasks_file}")
            
        except Exception as e:
            logger.error(f"Error saving review tasks: {str(e)}")
    
    def get_task(self, task_id: str) -> Optional[ReviewTask]:
        """
        Get a task by ID
        
        Args:
            task_id: Task ID
            
        Returns:
            ReviewTask object or None if not found
        """
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None
    
    def get_pending_tasks(self) -> List[ReviewTask]:
        """
        Get all pending review tasks
        
        Returns:
            List of pending ReviewTask objects
        """
        return [task for task in self.tasks if task.status == "pending_review"]
    
    def get_reviewed_tasks(self) -> List[ReviewTask]:
        """
        Get all reviewed tasks
        
        Returns:
            List of reviewed ReviewTask objects
        """
        return [task for task in self.tasks if task.status == "reviewed"]
    
    def update_task(self, task_id: str, corrected_data: Dict, reviewer_notes: str) -> bool:
        """
        Update a task with reviewer corrections
        
        Args:
            task_id: Task ID
            corrected_data: Corrected data from the reviewer
            reviewer_notes: Notes from the reviewer
            
        Returns:
            True if the task was updated, False otherwise
        """
        task = self.get_task(task_id)
        if task:
            task.mark_as_reviewed(corrected_data, reviewer_notes)
            self.save_tasks()
            
            # Save the corrected data to a separate file
            self.save_corrected_data(task)
            
            return True
        return False
    
    def save_corrected_data(self, task: ReviewTask):
        """
        Save corrected data to a separate file
        
        Args:
            task: ReviewTask object
        """
        try:
            # Create output directory if it doesn't exist
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Save to file
            output_path = os.path.join(self.output_dir, f"corrected_{task.task_id}.json")
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "task_id": task.task_id,
                    "corrected_data": task.corrected_data,
                    "reviewer_notes": task.reviewer_notes,
                    "original_data": task.extracted_data,
                    "original_text": task.original_text,
                    "document_metadata": task.document_metadata
                }, f, indent=2)
                
            logger.info(f"Saved corrected data to {output_path}")
            
        except Exception as e:
            logger.error(f"Error saving corrected data: {str(e)}")
    
    def export_all_corrected_data(self) -> str:
        """
        Export all corrected data to a single file
        
        Returns:
            Path to the exported file
        """
        try:
            # Get all reviewed tasks
            reviewed_tasks = self.get_reviewed_tasks()
            
            if not reviewed_tasks:
                logger.warning("No reviewed tasks to export")
                return ""
            
            # Create output directory if it doesn't exist
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Prepare data for export
            export_data = {
                "events": [],
                "actors": [],
                "concepts": [],
                "publications": [],
                "locations": [],
                "relationships": []
            }
            
            # Collect corrected data from all reviewed tasks
            for task in reviewed_tasks:
                # Extract entities
                entities = task.corrected_data.get("entities", {})
                for entity_type, entity_list in entities.items():
                    if entity_type in export_data:
                        export_data[entity_type].extend(entity_list)
                
                # Extract relationships
                relationships = task.corrected_data.get("relationships", [])
                export_data["relationships"].extend(relationships)
            
            # Save to file
            output_path = os.path.join(self.output_dir, "all_corrected_data.json")
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2)
                
            logger.info(f"Exported all corrected data to {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error exporting corrected data: {str(e)}")
            return ""

class ReviewServer(BaseHTTPRequestHandler):
    """HTTP server for human review interface"""
    
    # Class variable to store the review manager
    review_manager = None
    
    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)
        
        # Serve the main page
        if parsed_path.path == "/" or parsed_path.path == "/index.html":
            self.serve_index_page()
            
        # Serve the task list page
        elif parsed_path.path == "/tasks":
            self.serve_task_list()
            
        # Serve a specific task page
        elif parsed_path.path == "/task" and "id" in query_params:
            task_id = query_params["id"][0]
            self.serve_task_page(task_id)
            
        # Serve static files
        elif parsed_path.path.startswith("/static/"):
            self.serve_static_file(parsed_path.path[8:])
            
        # Serve API endpoints
        elif parsed_path.path.startswith("/api/"):
            self.serve_api_endpoint(parsed_path.path[5:], query_params)
            
        # 404 Not Found
        else:
            self.send_error(404, "Not Found")
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        # Parse JSON data
        try:
            data = json.loads(post_data)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return
        
        # Handle task update
        if self.path == "/api/update_task" and "task_id" in data:
            task_id = data["task_id"]
            corrected_data = data.get("corrected_data", {})
            reviewer_notes = data.get("reviewer_notes", "")
            
            # Update the task
            if self.review_manager.update_task(task_id, corrected_data, reviewer_notes):
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode())
            else:
                self.send_error(404, "Task not found")
        
        # 404 Not Found
        else:
            self.send_error(404, "Not Found")
    
    def serve_index_page(self):
        """Serve the main index page"""
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Planetary Health Knowledge Graph - Human Review</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background-color: #f8f9fa;
                    padding: 20px;
                }
                
                .container {
                    max-width: 1000px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 30px;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                
                h1 {
                    color: #2c3e50;
                    margin-bottom: 30px;
                    text-align: center;
                }
                
                .card {
                    margin-bottom: 20px;
                    border: none;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }
                
                .card-header {
                    background-color: #3498db;
                    color: white;
                    font-weight: bold;
                }
                
                .btn-primary {
                    background-color: #3498db;
                    border-color: #3498db;
                }
                
                .btn-primary:hover {
                    background-color: #2980b9;
                    border-color: #2980b9;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Planetary Health Knowledge Graph</h1>
                <h2>Human Review Interface</h2>
                
                <div class="row">
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">Review Tasks</div>
                            <div class="card-body">
                                <p>Review and correct extracted information that requires human judgment.</p>
                                <a href="/tasks" class="btn btn-primary">View Tasks</a>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">Export Data</div>
                            <div class="card-body">
                                <p>Export all corrected data to a single file.</p>
                                <a href="/api/export" class="btn btn-primary">Export Data</a>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="mt-4">
                    <h3>About Human Review</h3>
                    <p>
                        This interface allows human experts to review and correct information that was automatically
                        extracted from documents about planetary health. The review process helps ensure the accuracy
                        and quality of the knowledge graph.
                    </p>
                    <p>
                        Tasks are prioritized based on the confidence of the extraction and the severity of potential issues.
                        High-priority tasks should be reviewed first.
                    </p>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        </body>
        </html>
        """
        
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())
    
    def serve_task_list(self):
        """Serve the task list page"""
        # Get pending tasks
        pending_tasks = self.review_manager.get_pending_tasks()
        
        # Sort by priority (high, medium, low)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        pending_tasks.sort(key=lambda task: priority_order.get(task.priority, 3))
        
        # Generate task list HTML
        task_list_html = ""
        for task in pending_tasks:
            priority_class = {
                "high": "table-danger",
                "medium": "table-warning",
                "low": "table-info"
            }.get(task.priority, "")
            
            task_list_html += f"""
            <tr class="{priority_class}">
                <td>{task.task_id[:8]}...</td>
                <td>{task.priority.capitalize()}</td>
                <td>{task.document_metadata.get("section_title", "Unknown")}</td>
                <td>{len(task.highlighted_issues)}</td>
                <td>{task.created_at}</td>
                <td><a href="/task?id={task.task_id}" class="btn btn-sm btn-primary">Review</a></td>
            </tr>
            """
        
        # Get reviewed tasks
        reviewed_tasks = self.review_manager.get_reviewed_tasks()
        
        # Generate reviewed task list HTML
        reviewed_task_list_html = ""
        for task in reviewed_tasks:
            reviewed_task_list_html += f"""
            <tr>
                <td>{task.task_id[:8]}...</td>
                <td>{task.document_metadata.get("section_title", "Unknown")}</td>
                <td>{task.reviewed_at}</td>
                <td><a href="/task?id={task.task_id}" class="btn btn-sm btn-secondary">View</a></td>
            </tr>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Review Tasks - Planetary Health Knowledge Graph</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background-color: #f8f9fa;
                    padding: 20px;
                }}
                
                .container {{
                    max-width: 1000px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 30px;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                
                h1, h2 {{
                    color: #2c3e50;
                    margin-bottom: 20px;
                }}
                
                .table {{
                    margin-top: 20px;
                }}
                
                .btn-primary {{
                    background-color: #3498db;
                    border-color: #3498db;
                }}
                
                .btn-primary:hover {{
                    background-color: #2980b9;
                    border-color: #2980b9;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Review Tasks</h1>
                <a href="/" class="btn btn-secondary mb-4">Back to Home</a>
                
                <h2>Pending Tasks</h2>
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead>
                            <tr>
                                <th>Task ID</th>
                                <th>Priority</th>
                                <th>Section</th>
                                <th>Issues</th>
                                <th>Created</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {task_list_html if task_list_html else '<tr><td colspan="6" class="text-center">No pending tasks</td></tr>'}
                        </tbody>
                    </table>
                </div>
                
                <h2 class="mt-5">Reviewed Tasks</h2>
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead>
                            <tr>
                                <th>Task ID</th>
                                <th>Section</th>
                                <th>Reviewed</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {reviewed_task_list_html if reviewed_task_list_html else '<tr><td colspan="4" class="text-center">No reviewed tasks</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        </body>
        </html>
        """
        
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())
    
    def serve_task_page(self, task_id: str):
        """
        Serve a specific task page
        
        Args:
            task_id: Task ID
        """
        # Get the task
        task = self.review_manager.get_task(task_id)
        if not task:
            self.send_error(404, "Task not found")
            return
        
        # Format the original text
        original_text = task.original_text.replace("\n", "<br>")
        
        # Format the extracted data
        extracted_data_json = json.dumps(task.extracted_data, indent=2)
        
        # Format the highlighted issues
        issues_html = ""
        for issue in task.highlighted_issues:
            severity_class = {
                5: "text-danger",
                4: "text-danger",
                3: "text-warning",
                2: "text-info",
                1: "text-muted"
            }.get(issue.get("severity", 3), "")
            
            issues_html += f"""
            <div class="mb-2">
                <strong class="{severity_class}">{issue.get("issue_type", "Issue").capitalize()}:</strong>
                <span>{issue.get("description", "")}</span>
                {f'<br><small>Affects: {issue.get("entity_affected", "")}</small>' if issue.get("entity_affected") else ''}
            </div>
            """
        
        # Format the review questions
        questions_html = ""
        for question in task.review_questions:
            questions_html += f"<li>{question}</li>"
        
        # Determine if the task is editable
        is_editable = task.status == "pending_review"
        
        # Format the corrected data if available
        corrected_data_json = json.dumps(task.corrected_data, indent=2) if task.corrected_data else extracted_data_json
        
        # Create the reviewer notes section if the task is editable
        reviewer_notes_section = ""
        if is_editable:
            reviewer_notes_section = """
            <div class="mb-4">
                <label for="reviewer-notes" class="form-label">Reviewer Notes</label>
                <textarea id="reviewer-notes" class="form-control" rows="3" placeholder="Add your notes here..."></textarea>
            </div>
            
            <button id="save-button" class="btn btn-primary">Save Changes</button>
            """
        
        # Create the reviewer notes display if the task is already reviewed
        reviewer_notes_display = ""
        if task.status == "reviewed":
            reviewer_notes_display = f"""
            <h3>Reviewer Notes</h3>
            <div class="card mb-4">
                <div class="card-body">
                    <p>{task.reviewer_notes or "No notes provided"}</p>
                </div>
            </div>
            """
        
        # JavaScript for the save button
        save_button_js = ""
        if is_editable:
            save_button_js = f"""
            // Save changes
            document.getElementById("save-button").addEventListener("click", function() {{
                // Get corrected data
                const correctedDataText = document.getElementById("corrected-data").value;
                let correctedData;
                
                try {{
                    correctedData = JSON.parse(correctedDataText);
                }} catch (error) {{
                    alert("Invalid JSON in corrected data: " + error.message);
                    return;
                }}
                
                // Get reviewer notes
                const reviewerNotes = document.getElementById("reviewer-notes").value;
                
                // Send update request
                fetch("/api/update_task", {{
                    method: "POST",
                    headers: {{
                        "Content-Type": "application/json"
                    }},
                    body: JSON.stringify({{
                        task_id: "{task.task_id}",
                        corrected_data: correctedData,
                        reviewer_notes: reviewerNotes
                    }})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        alert("Task updated successfully");
                        window.location.href = "/tasks";
                    }} else {{
                        alert("Error updating task");
                    }}
                }})
                .catch(error => {{
                    alert("Error: " + error.message);
                }});
            }});
            """
        
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Review Task - Planetary Health Knowledge Graph</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background-color: #f8f9fa;
                    padding: 20px;
                }}
                
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 30px;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                
                h1, h2, h3 {{
                    color: #2c3e50;
                }}
                
                .original-text {{
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 4px;
                    margin-bottom: 20px;
                    max-height: 300px;
                    overflow-y: auto;
                }}
                
                .json-editor {{
                    font-family: monospace;
                    width: 100%;
                    height: 400px;
                    padding: 10px;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                }}
                
                .btn-primary {{
                    background-color: #3498db;
                    border-color: #3498db;
                }}
                
                .btn-primary:hover {{
                    background-color: #2980b9;
                    border-color: #2980b9;
                }}
                
                .priority-badge {{
                    display: inline-block;
                    padding: 5px 10px;
                    border-radius: 4px;
                    font-weight: bold;
                    text-transform: uppercase;
                    font-size: 12px;
                }}
                
                .priority-high {{
                    background-color: #f8d7da;
                    color: #721c24;
                }}
                
                .priority-medium {{
                    background-color: #fff3cd;
                    color: #856404;
                }}
                
                .priority-low {{
                    background-color: #d1ecf1;
                    color: #0c5460;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Review Task</h1>
                <a href="/tasks" class="btn btn-secondary mb-4">Back to Tasks</a>
                
                <div class="row mb-4">
                    <div class="col-md-6">
                        <h5>Task ID: <span class="text-muted">{task.task_id}</span></h5>
                        <h5>Priority: <span class="priority-badge priority-{task.priority}">{task.priority}</span></h5>
                        <h5>Status: <span class="badge bg-{task.status == 'reviewed' and 'success' or 'warning'}">{task.status.replace('_', ' ').title()}</span></h5>
                    </div>
                    <div class="col-md-6">
                        <h5>Section: <span class="text-muted">{task.document_metadata.get("section_title", "Unknown")}</span></h5>
                        <h5>Created: <span class="text-muted">{task.created_at}</span></h5>
                        {f'<h5>Reviewed: <span class="text-muted">{task.reviewed_at}</span></h5>' if task.reviewed_at else ''}
                    </div>
                </div>
                
                <div class="row">
                    <div class="col-md-6">
                        <h3>Original Text</h3>
                        <div class="original-text">
                            {original_text}
                        </div>
                        
                        <h3>Highlighted Issues</h3>
                        <div class="card mb-4">
                            <div class="card-body">
                                {issues_html if issues_html else '<p>No issues highlighted</p>'}
                            </div>
                        </div>
                        
                        <h3>Review Questions</h3>
                        <div class="card mb-4">
                            <div class="card-body">
                                <ul>
                                    {questions_html if questions_html else '<li>No specific questions</li>'}
                                </ul>
                            </div>
                        </div>
                        
                        {reviewer_notes_display}
                    </div>
                    
                    <div class="col-md-6">
                        <h3>Extracted Data</h3>
                        <div class="mb-4">
                            <textarea id="
