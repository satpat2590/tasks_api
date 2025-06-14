import os
import json
import requests
import sys
from datetime import datetime, timedelta, timezone
import zoneinfo
from pathlib import Path
from .game_tracker import get_points, save_points, penalize_overdue

# Configuration
WEB_SERVER_API = "https://tasks-api-71v5.onrender.com"
SENT_FILE = Path(__file__).parent.parent / "data" / "sent.json"
EASTERN_TZ = zoneinfo.ZoneInfo("America/New_York")


def get_tasks():
    """Get active tasks from API with error handling"""
    try:
        print(f"Requesting tasks from: {WEB_SERVER_API}/api/tasks")
        res = requests.get(f"{WEB_SERVER_API}/api/tasks", timeout=100)
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
######## NOTIFICATION ALERTER
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

######## POINTS SYSTEM
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