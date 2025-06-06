import os
import json
import requests
import sys
from datetime import datetime, timedelta, timezone
import zoneinfo
from pathlib import Path

# Configuration
WEB_SERVER_API = "https://tasks-api-71v5.onrender.com"
SENT_FILE = Path(__file__).parent.parent / "data" / "points.json"
GIST_ID = os.getenv("GITHUB_GIST_ID")  # Create one gist, use forever
GITHUB_TOKEN = os.getenv("GITHUB_GIST_PAT")
EASTERN_TZ = zoneinfo.ZoneInfo("America/New_York")

def get_points():
    """Fetch current points from Gist"""
    res = requests.get(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {GITHUB_TOKEN}"}
    )
    content = res.json()['files']['points.json']['content']
    print(f"Printing out the content from Github Gist:\n")
    json_content = json.loads(content)
    if not json_content:
        print(f"The JSON object returned from GH Gist is empty. Setting up template now...")
        json_content["total"] = 0
        json_content["categories"] = {
            'mental': 0,
            'physical': 0,
            'social': 0,
            'financial': 0
        }
        json_content["last_deductions"] = {}
        json_content["history"] = []
        print(f"Created JSON. Analyzing tasks now...")

    return json_content

def save_points(data):
    """Save points back to Gist"""
    requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        json={
            "files": {
                "points.json": {"content": json.dumps(data, indent=2)}
            }
        },
        headers={"Authorization": f"token {GITHUB_TOKEN}"}
    )

def calculate_points(task, points_data):
    """Update points for completed task"""
    base = task['priority'] * 10
    
    # Recurring penalty
    if task['is_recurring'] and 'daily' in task.get('recurrence_pattern', '').lower():
        base = int(base * 0.3)
    
    points_data['total'] += base
    points_data['history'].append({
        "task": task['title'],
        "points": base,
        "date": datetime.now(timezone.utc).isoformat()
    })
    
    return base

def should_deduct(task, points_data):
    """Check if already deducted today"""
    key = f"{task['id']}_{task['due_date'][:10]}"

    return key not in points_data['last_deductions']

def penalize_overdue(task, points_data):
    """Deduct once per task per due date"""
    if not should_deduct(task, points_data):
        return 0
    
    penalty = task['priority'] * 5
    category = task['category']
    
 # Update totals and category specific points trackers
    points_data['total'] -= penalty
    points_data["categories"][category] -= penalty

    print(f"Category '{category}' is now at {points_data['categories'][category]} points")
    
 # Mark as deducted
    key = f"{task['id']}_{task['due_date'][:10]}"
    points_data['last_deductions'][key] = datetime.now(EASTERN_TZ).isoformat()
    
 # Log it
    points_data['history'].append({
        "task_id": task['id'],
        "task": task['title'],
        "category": category,
        "points": -penalty,
        "type": "overdue",
        "date": datetime.now(EASTERN_TZ).isoformat()
    })
    
 # Trim history to last 100
    points_data['history'] = points_data['history'][-100:]
    
    return penalty

def get_tasks():
    """Get active tasks from API with error handling"""
    try:
        print(f"Requesting tasks from: {WEB_SERVER_API}/api/tasks")
        res = requests.get(f"{WEB_SERVER_API}/api/tasks", timeout=70)
        print(f"API response status: {res.status_code}")
        
        # Check for successful response
        if res.status_code != 200:
            print(f"[ERROR] - API Error: Received status {res.status_code}")
            print(f"Response content: {res.text[:200]}")  # First 200 characters
            return None
            
        # Attempt to parse JSON
        try:
            return res.json()
        except json.JSONDecodeError:
            print(f"[ERROR] - JSON Decode Error. Response content: {res.text[:200]}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] - Request failed: {str(e)}")
        return None

def sort_tasks(tasks):
    """Sort into overdue and due_soon buckets"""
    if tasks is None:
        print("No tasks to process")
        return [], []
        
    now = datetime.now(EASTERN_TZ)
    print(f"[T-MANAGER] - Current time is: {now}")
    overdue = []
    due_soon = []
    
    for task in tasks:
        if not task.get('due_date'):
            continue
            
        try:
            # Handle date formatting safely
            due_date = task['due_date'].replace('Z', '+00:00')
            due_raw = datetime.fromisoformat(due_date)
            due = due_raw.astimezone(EASTERN_TZ)
            print(f"'{task['title']}' - Due at {due}\n")
            diff = due - now
            
            if diff < timedelta(0):
                overdue.append(task)
            elif diff < timedelta(hours=3):
                due_soon.append(task)
        except (KeyError, ValueError) as e:
            print(f"[ERROR] - Error processing task {task.get('id')}: {str(e)}")
    
    return overdue, due_soon

def load_sent_log():
    """Load previously sent notifications with error handling"""
    try:
        if not SENT_FILE.exists():
            SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
            return {}
        
        with open(SENT_FILE, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"[ERROR] - Error loading sent log: {str(e)}")
        return {}

def save_sent_log(log):
    """Save notification log with error handling"""
    try:
        with open(SENT_FILE, 'w') as f:
            json.dump(log, f, indent=2)
    except IOError as e:
        print(f"[ERROR] - Error saving sent log: {str(e)}")

def should_notify(task_id, notification_type, sent_log):
    """Check if we should send notification"""
    key = f"{task_id}_{notification_type}"
    if key not in sent_log:
        return True
    
    try:
        last_sent = datetime.fromisoformat(sent_log[key])
        elapsed = datetime.now(timezone.utc) - last_sent
        
        if notification_type == "overdue":
            return elapsed > timedelta(hours=24)
        else:  # reminder
            return elapsed > timedelta(hours=6)
    except (KeyError, ValueError) as e:
        print(f"[ERROR] - Error checking notification status: {str(e)}")
        return True

def notifier(overdue, due_soon):
    """Send notifications for tasks"""
    if not overdue and not due_soon:
        print("[T-MANAGER] - No tasks to notify about")
        return 0
        
    sent_log = load_sent_log()
    messages = []
    
    # Process overdue tasks
    for task in overdue:
        try:
            task_id = task['id']
            if should_notify(task_id, 'overdue', sent_log):
                msg = f"OVERDUE: {task['title']} - Category: {task.get('category', 'UNKNOWN').upper()}"
                messages.append(msg)
                sent_log[f"{task_id}_overdue"] = datetime.now(timezone.utc).isoformat()
        except KeyError as e:
            print(f"[ERROR] - Error processing overdue task: {str(e)}")

    # Process due soon tasks
    for task in due_soon:
        try:
            task_id = task['id']
            if should_notify(task_id, 'reminder', sent_log):
                due = datetime.fromisoformat(task['due_date'].replace('Z', '+00:00'))
                hours_left = (due - datetime.now(timezone.utc)).total_seconds() / 3600
                msg = f"DUE IN {hours_left:.1f}H: {task['title']}"
                messages.append(msg)
                sent_log[f"{task_id}_reminder"] = datetime.now(timezone.utc).isoformat()
        except (KeyError, ValueError) as e:
            print(f"[ERROR] - Error processing due soon task: {str(e)}")

    # Send to Twitter/X
    for msg in messages:
        print(f"POSTING: {msg}")
        # TODO: Uncomment when ready
        # twitter_client.post_tweet(msg)
    
    save_sent_log(sent_log)
    return len(messages)



if __name__ == "__main__":
    try:
        print("=== Starting 'Notifier' ===")
        
     # Get all active tasks
        tasks = get_tasks()
        
        if tasks is None:
            print("[ERROR] - Critical error fetching tasks. Exiting.")
            sys.exit(1)

     # Sort all active tasks into those which are overdue OR due soon        
        print(f"\nRetrieved {len(tasks)} tasks")
        overdue, due_soon = sort_tasks(tasks)
        print(f"Overdue: {len(overdue)}")
        print(f"Due Soon: {len(due_soon)}")
     
     # Send out notifications to alert you of impending tasks
        sent_count = notifier(overdue, due_soon)
        print(f"Sent {sent_count} notifications\n")
        print("=== Completed ===")
        print("=== Starting 'Game State Updater' ===")

     # Update the points system
        point_sys = get_points()
        for task in overdue:
            penalty = penalize_overdue(task, point_sys)
        save_points(point_sys)
        
        print("=== Completed ===")
        
    except Exception as e:
        print(f"Unhandled exception: {str(e)}")
        sys.exit(1)