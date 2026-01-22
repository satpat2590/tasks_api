import requests
import json
import sys
from datetime import datetime
import zoneinfo
import os

# Configuration
WEB_SERVER_API = "https://tasks-api-71v5.onrender.com"
EASTERN_TZ = zoneinfo.ZoneInfo("America/New_York")
NTFY_CHANNEL = os.getenv("NTFY_CHANNEL", "satyam_tasks") # Default channel

def fetch_active_tasks():
    """Fetch active tasks with remainder from the API"""
    url = f"{WEB_SERVER_API}/api/tasks/remainder"
    try:
        print(f"[{datetime.now(EASTERN_TZ)}] - Fetching tasks from: {url}")
        response = requests.get(url, timeout=100)
        
        if response.status_code != 200:
            print(f"[ERROR] - API returned status code {response.status_code}")
            return None
            
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] - Request failed: {str(e)}")
        return None

def send_notification(topic, message, priority="default", tags=None):
    """Send a notification via ntfy.sh"""
    headers = {
        "Title": "Game of Life: Task Update",
        "Priority": priority
    }
    if tags:
        headers["Tags"] = tags
        
    try:
        url = f"https://ntfy.sh/{topic}"
        res = requests.post(url, data=message, headers=headers)
        if res.status_code == 200:
            print(f"[SUCCESS] - Sent notification to {topic}")
        else:
            print(f"[ERROR] - Failed to send notification: {res.status_code}")
    except Exception as e:
        print(f"[ERROR] - Notification error: {str(e)}")

def group_tasks(tasks):
    """Group tasks by their urgency level"""
    groups = {
        "OVERDUE": [],
        "IMMEDIATE ( < 3h )": [],
        "URGENT ( < 12h )": [],
        "SOON ( < 24h )": [],
        "LATER": []
    }
    
    for task in tasks:
        rem = task.get('time_remaining')
        
        if rem is None:
            groups["LATER"].append(task)
        elif rem < 0:
            groups["OVERDUE"].append(task)
        elif rem < 3:
            groups["IMMEDIATE ( < 3h )"].append(task)
        elif rem < 12:
            groups["URGENT ( < 12h )"].append(task)
        elif rem < 24:
            groups["SOON ( < 24h )"].append(task)
        else:
            groups["LATER"].append(task)
            
    return groups

def main():
    tasks = fetch_active_tasks()
    
    if tasks is None:
        print("[CRITICAL] - Could not retrieve tasks. Exiting.")
        sys.exit(1)
        
    grouped = group_tasks(tasks)
    
    for label, group_tasks_list in grouped.items():
        if not group_tasks_list:
            continue
            
        print(f"\nProcessing {label} group ({len(group_tasks_list)} tasks)")
        
        # Build message for ntfy
        msg_lines = [f"{label} Tasks:"]
        for t in group_tasks_list:
            rem = t.get('time_remaining')
            rem_str = f"{rem}h" if rem is not None else "N/A"
            msg_lines.append(f"- {t['title']} ({rem_str})")
        
        message = "\n".join(msg_lines)
        
        # Set priority and tags based on label
        priority = "default"
        tags = "memo"
        if label == "OVERDUE":
            priority = "urgent"
            tags = "warning,skull"
        elif label == "IMMEDIATE ( < 3h )":
            priority = "high"
            tags = "fire,clock1"
            
        send_notification(NTFY_CHANNEL, message, priority=priority, tags=tags)

if __name__ == "__main__":
    main()
