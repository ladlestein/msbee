import os
import re
from datetime import date
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv
from openai import OpenAI
from task import Task

# === LOAD ENVIRONMENT VARIABLES ===
load_dotenv()

VAULT_PATH = Path(os.environ.get("MSBEE_VAULT_PATH", "."))
DAILY_NOTES_PATH = VAULT_PATH / os.environ.get("MSBEE_DAILY_PATH", "daily")
ROADMAP_PATH = VAULT_PATH / os.environ.get("MSBEE_ROADMAP_PATH", "msbee/roadmap.md")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY environment variable.")

client = OpenAI(api_key=OPENAI_API_KEY)

# === TASK + ROADMAP EXTRACTION ===

def clean_task_text(task_text):
    """Clean a task text by removing all metadata (emojis, dates, etc)."""
    clean_text = task_text.split(" ➕ ")[0] if " ➕ " in task_text else task_text
    clean_text = clean_text.split(" 📅 ")[0] if " 📅 " in clean_text else clean_text
    clean_text = clean_text.split(" ⏭️ ")[0] if " ⏭️ " in clean_text else clean_text
    clean_text = clean_text.split(" ⛔ ")[0] if " ⛔ " in clean_text else clean_text
    clean_text = clean_text.split(" 🆔 ")[0] if " 🆔 " in clean_text else clean_text
    return clean_text

def escape_task_query(text):
    """Escape special characters for Obsidian Tasks query syntax."""
    # Escape backslash first to avoid double-escaping
    escaped = text.replace("\\", "\\\\")
    # Then escape other special characters
    escaped = escaped.replace("(", "\\(").replace(")", "\\)")
    escaped = escaped.replace("[", "\\[").replace("]", "\\]")
    escaped = escaped.replace("{", "\\{").replace("}", "\\}")
    escaped = escaped.replace("+", "\\+").replace("*", "\\*")
    escaped = escaped.replace("?", "\\?").replace("|", "\\|")
    escaped = escaped.replace("^", "\\^").replace("$", "\\$")
    escaped = escaped.replace(".", "\\.")
    return escaped

def extract_tasks(vault_path=None, today=date.today()):
    task_objects = {}  # Map of clean task text to Task object
    completed_tasks = set()
    
    if vault_path is None:
        vault_path = VAULT_PATH
    
    # First pass: collect all tasks and create Task objects
    for md in Path(vault_path).rglob("*.md"):
        if "Templates" in str(md):
            continue
        with open(md, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Track completed tasks
            if line.startswith("- [x]"):
                task_text = line[6:].strip()  # Remove "- [x] "
                completed_tasks.add(clean_task_text(task_text))
                continue
                
            # Process uncompleted tasks
            if line.startswith("- [ ]"):
                task_text = line[6:].strip()  # Remove "- [ ] "
                clean_text = clean_task_text(task_text)
                
                # Check for start date
                start_date = None
                start_date_match = re.search(r'🛫 (\d{4}-\d{2}-\d{2})', task_text)
                if start_date_match:
                    start_date = date.fromisoformat(start_date_match.group(1))
                
                # Check for dependencies (⏭️)
                dependencies = set()
                dependency_match = re.search(r'⏭️ (.*?)(?=\s*$|\s*[#@])', task_text)
                if dependency_match:
                    dependency_text = dependency_match.group(1).strip()
                    dependencies.add(clean_task_text(dependency_text))
                
                # Create Task object
                task = Task(
                    text=task_text,
                    location=md,
                    start_date=start_date,
                    dependencies=dependencies
                )
                task_objects[clean_text] = task
    
    # Second pass: resolve dependencies to actual Task objects
    for task in task_objects.values():
        resolved_dependencies = set()
        for dep_text in task.dependencies:
            if dep_text in task_objects:
                resolved_dependencies.add(task_objects[dep_text])
        task.dependencies = resolved_dependencies
    
    # Third pass: mark completed tasks
    for clean_text in completed_tasks:
        if clean_text in task_objects:
            task_objects[clean_text].is_completed = True
    
    # Fourth pass: return only eligible tasks
    eligible_tasks = []
    for task in task_objects.values():
        if task.is_eligible(today):
            eligible_tasks.append((task.text, task.location))
    
    return eligible_tasks

def extract_roadmap():
    if not ROADMAP_PATH.exists():
        return "No roadmap found."
    with open(ROADMAP_PATH, "r", encoding="utf-8") as f:
        return f.read()

# === LLM QUERY ===

def has_problematic_query_chars(text):
    # Define problematic characters for Obsidian Tasks queries
    return any(c in text for c in '()[]{}+*?|^$\\')

def ask_msbee(tasks, roadmap):
    # Format tasks with their locations for the prompt
    task_descriptions = []
    for task_text, location in tasks:
        relative_path = location.relative_to(VAULT_PATH)
        task_descriptions.append(f"- [ ] {task_text} (in {relative_path})")
    
    # Generate the tasks query conditions
    task_conditions = []
    for task_text, location in tasks[:3]:  # Take first 3 tasks
        clean_text = clean_task_text(task_text)
        words = clean_text.split()
        if len(words) > 3:
            clean_text = " ".join(words[:3])
        if has_problematic_query_chars(clean_text):
            # Use only the path filter if problematic characters are present
            condition = f'(path includes {location.relative_to(VAULT_PATH)})'
        else:
            escaped_text = escape_task_query(clean_text)
            condition = f'(path includes {location.relative_to(VAULT_PATH)}) AND (description includes {escaped_text})'
        task_conditions.append(condition)
    tasks_query = " OR ".join(task_conditions)
    if len(task_conditions) > 1:
        tasks_query = f'({tasks_query})'
    
    prompt = f"""You are MsBee, a gentle but clever assistant. 
Here are some open tasks:
{chr(10).join(task_descriptions)}

And here's the user's high-level roadmap:
{roadmap}

Write a motivational nudge, and a fun one-liner that could go on a lock screen.
Respond in Markdown like this:

## 🐝 Nudge
Your message here

## 🔒 Lock Screen Quote
"Your one-liner here"
"""
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    
    # Combine the tasks query with GPT's response
    gpt_content = response.choices[0].message.content
    return f"""## 🌟 Focus Tasks
```tasks
{tasks_query}
```

{gpt_content}"""

# === DAILY NOTE UPDATE ===

def update_daily_note(content, note_date=date.today()):
    daily_note = DAILY_NOTES_PATH / f"{note_date.isoformat()}.md"
    if not daily_note.exists():
        print(f"Daily note not found: {daily_note}")
        return

    with open(daily_note, "r", encoding="utf-8") as f:
        text = f.read()

    # Replace or insert the MsBee section
    if "## 🐝 MsBee" in text:
        updated_text = re.sub(
            r"## 🐝 MsBee[\s\S]*?(?=\n## |\Z)",
            f"## 🐝 MsBee\n{content}",
            text,
            flags=re.MULTILINE
        )
    else:
        updated_text = text.strip() + "\n\n## 🐝 MsBee\n" + content

    with open(daily_note, "w", encoding="utf-8") as f:
        f.write(updated_text)

    print(f"MsBee section updated in: {daily_note}")

# === MAIN ===

if __name__ == "__main__":
    tasks = extract_tasks(today=date.today())
    roadmap = extract_roadmap()
    reply = ask_msbee(tasks, roadmap)
    update_daily_note(reply, note_date=date.today())
