import os
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Configuration
WEB_SERVER_API = "https://tasks-api-71v5.onrender.com"
SENT_FILE = Path(__file__).parent.parent / "data" / "sent.json"

def get_tasks():
    """Get active tasks from API"""
    res = requests.get(f"{WEB_SERVER_API}/api/tasks")
    return res.json()

def sort_tasks(tasks):
    """Sort into overdue and due_soon buckets"""
    now = datetime.now(timezone.utc)
    overdue = []
    due_soon = []
    
    for task in tasks:
        if not task['due_date']:
            continue
            
        due = datetime.fromisoformat(task['due_date'].replace('Z', '+00:00'))
        diff = due - now
        
        if diff < timedelta(0):
            overdue.append(task)
        elif diff < timedelta(hours=3):
            due_soon.append(task)
    
    return overdue, due_soon

def load_sent_log():
    """Load previously sent notifications"""
    if not SENT_FILE.exists():
        SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        return {}
    
    with open(SENT_FILE, 'r') as f:
        return json.load(f)

def save_sent_log(log):
    """Save notification log"""
    with open(SENT_FILE, 'w') as f:
        json.dump(log, f, indent=2)

def should_notify(task_id, notification_type, sent_log):
    """Check if we should send notification"""
    key = f"{task_id}_{notification_type}"
    if key not in sent_log:
        return True
    
 # Re-notify after 24 hours for overdue, 6 hours for reminders
    last_sent = datetime.fromisoformat(sent_log[key])
    elapsed = datetime.now(timezone.utc) - last_sent # How much time has passed since last notification/punishment?
    
    if notification_type == "overdue":
        return elapsed > timedelta(hours=24)
    else:  # reminder
        return elapsed > timedelta(hours=6)

def dish_out_punishments(overdue, due_soon):
    """Send notifications for tasks"""
 # Load the already sent notifs/punishments for tasks
    sent_log = load_sent_log()
    messages = [] # Store all outbound messages into this array
    
 # Process overdue tasks
    for task in overdue:
        if should_notify(task['id'], 'overdue', sent_log):
            msg = f"OVERDUE: {task['title']} - Category: {task['category'].upper()}"
            messages.append(msg)
            sent_log[f"{task['id']}_overdue"] = datetime.now(timezone.utc).isoformat()
    
    # Process due soon tasks
    for task in due_soon:
        if should_notify(task['id'], 'reminder', sent_log):
            due = datetime.fromisoformat(task['due_date'].replace('Z', '+00:00'))
            hours_left = (due - datetime.now(timezone.utc)).total_seconds() / 3600
            msg = f"DUE IN {hours_left:.1f}H: {task['title']}"
            messages.append(msg)
            sent_log[f"{task['id']}_reminder"] = datetime.now(timezone.utc).isoformat()
    
    # Send to Twitter/X (placeholder)
    for msg in messages:
        print(f"POSTING: {msg}")
        # TODO: Add your Twitter API call here
        # twitter_client.post_tweet(msg)
    
    save_sent_log(sent_log)
    return len(messages)

if __name__ == "__main__":
    tasks = get_tasks()
    overdue, due_soon = sort_tasks(tasks)
    
    print(f"Overdue: {len(overdue)}")
    print(f"Due Soon: {len(due_soon)}")
    
    sent_count = dish_out_punishments(overdue, due_soon)
    print(f"Sent {sent_count} notifications")