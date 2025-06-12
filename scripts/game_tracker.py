import os 
import requests
import json
from datetime import datetime, timezone
import zoneinfo

# Configuration
GIST_ID = os.getenv("GH_GIST_ID")  # Create one gist, use forever
GITHUB_TOKEN = os.getenv("GH_GIST_PAT")
EASTERN_TZ = zoneinfo.ZoneInfo("America/New_York")


def get_points():
    """Fetch current points from Gist"""
    res = requests.get(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {GITHUB_TOKEN}"}
    )
    content = res.json()['files']['points.json']['content']
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
    else:
        print(f"\nPoint History: ")
        print(json_content["history"])

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