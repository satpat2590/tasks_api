import os, json, re
from supabase import Client, create_client
from anthropic import Anthropic
from typing import List

# Make the connection to Supabase instance
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

def build_hierarchy_string(tags):
    """Convert flat tag list into readable hierarchy paths"""
    # Build parent-child relationships
    tag_dict = {tag['id']: tag for tag in tags}
    
    def get_path(tag_id):
        tag = tag_dict.get(tag_id)
        if not tag:
            return ""
        
        path_parts = [tag['name']]
        parent_id = tag.get('parent_tag_id')
        
        while parent_id:
            parent = tag_dict.get(parent_id)
            if parent:
                path_parts.insert(0, parent['name'])
                parent_id = parent.get('parent_tag_id')
            else:
                break
        
        return "/".join(path_parts)
    
    # Group by category
    hierarchy = {}
    for tag in tags:
        category = tag['category']
        if category not in hierarchy:
            hierarchy[category] = []
        
        # Only add if it's a leaf node (no children)
        is_leaf = not any(t.get('parent_tag_id') == tag['id'] for t in tags)
        if is_leaf:
            full_path = get_path(tag['id'])
            hierarchy[category].append(full_path)
    
    # Format for prompt
    result = []
    for category, paths in hierarchy.items():
        result.append(f"{category.upper()}:")
        for path in sorted(paths):
            result.append(f"  - {path}")
    
    return "\n".join(result)



async def auto_tag_task(task_data) -> List[str]:
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # Get existing tags for context
    existing_tags = supabase.table('tags').select("*").execute().data
    tags_hierarchy = build_hierarchy_string(existing_tags)
    
    prompt = f"""
        Task: "{task_data['title']}"
        Description: "{task_data.get('description', '')}"
        Category: {task_data['category']}
        
        Current tag hierarchy:
        {tags_hierarchy}
        
        Suggest specific tags for this task. Return as JSON array of tag paths.
        If tags don't exist, suggest new ones following the hierarchy pattern.
        Be specific - use the deepest appropriate level. Please don't include the {{Category}} into the list of tags.
        
        Example response: ["Computer Science/Web Development/Frontend Development/React Components"]
        ["Computer Science/Web Development/Backend Development/Express]
    """
 # What say you, Mr. Claude?
    response = client.messages.create(
        model="claude-sonnet-4-20250514",  # Fast & cheap
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = response.content[0].text 
    json_match = re.search(r'\[.*?\]', response_text, re.DOTALL)

 # If there exists a response from the AI which matches the regex (sub-topics in list format)
    if json_match:
        suggested_paths = json.loads(json_match.group())
    else:
        return []

 # Parse AI response and create/match tags
    print(suggested_paths)
    tag_ids = []

 # For each sub-topic in the list, ensure it exists in the DB, create if not
    for path in suggested_paths:
        print(f"\n\nAnalyzing the following sub-topic: {path}")
        tag_id = ensure_tag_exists(path, task_data['category'])
        tag_ids.append(tag_id) 
    
    return tag_ids

def ensure_tag_exists(path, category):
    """Create tag hierarchy if it doesn't exist"""
    parts = path.split('/')
    parent_id = None  # Use None for root tags, not 0
    
    for i, part in enumerate(parts):
        # Check if tag exists with this specific parent
        print(f"\nChecking if '{part}' exists with parent_id={parent_id}...")
        
        if parent_id is None:
            # Root level tag
            existing = supabase.table('tags').select("*").eq(
                'name', part
            ).is_('parent_tag_id', 'null').eq(
                'category', category
            ).execute()
        else:
            # Child tag
            existing = supabase.table('tags').select("*").eq(
                'name', part
            ).eq('parent_tag_id', parent_id).execute()
        
        if existing.data:
            print(f"\n'{part}' exists! Using id={existing.data[0]['id']}")
            parent_id = existing.data[0]['id']
        else:
            print(f"\n'{part}' doesn't exist. Creating with parent_id={parent_id}")
            # Create new tag
            new_tag = supabase.table('tags').insert({
                'name': part,
                'parent_tag_id': parent_id,  # None for root, or parent's ID
                'category': category
            }).execute()
            parent_id = new_tag.data[0]['id']
            print(f"\nCreated '{part}' with id={parent_id}")
    
    # Return the leaf tag ID
    return parent_id


def get_tag_by_id(tag_id):
    tag = supabase.table('tags').select("*").eq(
        'id', tag_id
    ).execute()

    if tag.data:
        return tag.data[0]

    return None

def get_tag_path(tag_id):
    """Build full path for a tag by traversing up the hierarchy"""
    path_parts = []
    current_tag_id = tag_id
    
    while current_tag_id:
        tag = get_tag_by_id(current_tag_id)
        if not tag:
            break
            
        path_parts.insert(0, tag['name'])  # Insert at beginning
        current_tag_id = tag.get('parent_tag_id')
    
    return "/".join(path_parts)



if __name__=="__main__":
    task = supabase.table("tasks").select("*").eq(
        "id", 20
    ).execute()

    if task.data:
        tags = auto_tag_task(task.data[0])
        print(tags)