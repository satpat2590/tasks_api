import asyncio, os, json, re
from utils.db import supabase
from openai import OpenAI
from typing import List


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



def _parse_suggested_paths(response_text):
    """Robustly extract a list of tag paths from an LLM response text"""
    if not response_text:
        return []

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    cleaned = re.sub(r"```(?:json)?", "", response_text).strip()

    # Try to extract a JSON array of paths
    json_match = re.search(r'\[.*?\]', cleaned, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                paths = [str(p).strip() for p in parsed if str(p).strip()]
                if paths:
                    return paths
        except (json.JSONDecodeError, ValueError):
            pass

    # Last resort: parse '- A/B/C' bullet lines into paths
    paths = []
    for line in cleaned.splitlines():
        bullet = re.match(r'^\s*[-*]\s+(.+?)\s*$', line)
        if bullet:
            path = bullet.group(1).strip('"\'').strip()
            if '/' in path:
                paths.append(path)
    return paths


def _query_openrouter(prompt):
    """Provider 1: OpenRouter moonshotai/kimi-k3 via the OpenAI client"""
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )
    response = client.chat.completions.create(
        model="moonshotai/kimi-k3",  # Fast & cheap
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content


def _query_deepseek(prompt):
    """Provider 2: DeepSeek deepseek-chat via the OpenAI client"""
    client = OpenAI(
        base_url="https://api.deepseek.com",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
    )
    response = client.chat.completions.create(
        model="deepseek-chat",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content


def _query_anthropic(prompt):
    """Provider 3: Anthropic claude-sonnet-4-5 via the anthropic SDK"""
    import anthropic  # lazy import so module loads even if anthropic isn't installed
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


# Ordered provider fallback chain for auto_tag_task
TAGGING_PROVIDERS = [
    ("OpenRouter moonshotai/kimi-k3", _query_openrouter),
    ("DeepSeek deepseek-chat", _query_deepseek),
    ("Anthropic claude-sonnet-4-5", _query_anthropic),
]


async def auto_tag_task(task_data) -> List[str]:
    """
    Given an input task, figure out what tags should be associated with it, and return it as a List of strings where each entry is a tag in hierarchical order

    :param task_data: The task which is to be created by the backend
    :return tag_list: The list of tags in hierarchial order
    """
 # Get existing tags for context
    existing_tags = supabase.table('tags').select("*").eq('category', task_data['category']).execute().data
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

        Example response: ["Computer Science/Web Development/Frontend Development/React Components"], ["Computer Science/Web Development/Frontend Development/Vite"]
    """
 # What say you, Mr. Claude?
 # Try each provider in order; on exception or unparseable/empty result, try the next
    suggested_paths = []
    for provider_name, query_fn in TAGGING_PROVIDERS:
        try:
            # Provider calls are sync (blocking network I/O). Offload to a
            # worker thread so we never stall the event loop on the fallback chain.
            response_text = await asyncio.to_thread(query_fn, prompt)
            suggested_paths = _parse_suggested_paths(response_text)
            if suggested_paths:
                print(f"auto_tag_task: provider '{provider_name}' succeeded with {len(suggested_paths)} suggested path(s)")
                break
            print(f"auto_tag_task: provider '{provider_name}' returned an unparseable/empty result, trying next provider")
        except Exception as e:
            print(f"auto_tag_task: provider '{provider_name}' failed ({e}), trying next provider")

    if not suggested_paths:
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
