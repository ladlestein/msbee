import os
import re
from datetime import date
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv
from openai import OpenAI
from task import Task
from task_ids import add_task_ids_to_vault

# === LOAD ENVIRONMENT VARIABLES ===
load_dotenv()

class MsBee:
    def __init__(self, vault_path=None, daily_notes_path=None, roadmap_path=None, openai_api_key=None):
        self.vault_path = Path(vault_path or os.environ.get("MSBEE_VAULT_PATH", "."))
        self.daily_notes_path = Path(daily_notes_path) if daily_notes_path else self.vault_path / os.environ.get("MSBEE_DAILY_PATH", "daily")
        self.roadmap_path = Path(roadmap_path) if roadmap_path else self.vault_path / os.environ.get("MSBEE_ROADMAP_PATH", "msbee/roadmap.md")
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("Missing OPENAI_API_KEY environment variable.")
        self.client = OpenAI(api_key=self.openai_api_key)

    @staticmethod
    def clean_task_text(task_text):
        """Clean a task text by removing all metadata (emojis, dates, etc)."""
        clean_text = task_text.split(" ➕ ")[0] if " ➕ " in task_text else task_text
        clean_text = clean_text.split(" 📅 ")[0] if " 📅 " in clean_text else clean_text
        clean_text = clean_text.split(" ⏭️ ")[0] if " ⏭️ " in clean_text else clean_text
        clean_text = clean_text.split(" ⛔ ")[0] if " ⛔ " in clean_text else clean_text
        clean_text = clean_text.split(" 🆔 ")[0] if " 🆔 " in clean_text else clean_text
        return clean_text

    def extract_tasks(self, today=date.today()):
        task_objects = {}  # Map of clean task text to Task object
        completed_tasks = set()
 
        # First pass: collect all tasks and create Task objects
        for md in self.vault_path.rglob("*.md"):
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
                    completed_tasks.add(self.clean_task_text(task_text))
                    continue
                
                # Process uncompleted tasks
                if line.startswith("- [ ]"):
                    task_text = line[6:].strip()  # Remove "- [ ] "
                    clean_text = self.clean_task_text(task_text)
                    
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
                        dependencies.add(self.clean_task_text(dependency_text))
                    
                    # Extract task ID
                    task_id = None
                    id_match = re.search(r'🆔 ([a-zA-Z0-9]{6})', task_text)
                    if id_match:
                        task_id = id_match.group(1)
                    
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
        
        # Fourth pass: return only eligible tasks with their IDs
        eligible_tasks = []
        for task in task_objects.values():
            if task.is_eligible(today):
                # Extract task ID from the task text
                task_id = None
                id_match = re.search(r'🆔 ([a-zA-Z0-9]{6})', task.text)
                if id_match:
                    task_id = id_match.group(1)
                eligible_tasks.append((task.text, task.location, task_id))
        
        return eligible_tasks

    def extract_roadmap(self):
        if not self.roadmap_path.exists():
            return "No roadmap found."
        with open(self.roadmap_path, "r", encoding="utf-8") as f:
            return f.read()

    def ask_msbee(self, tasks, roadmap):
        # Format tasks with their locations and IDs for the prompt
        task_descriptions = []
        task_id_map = {}  # Map of (desc, path) to task_id
        
        for i, (task_text, location, task_id) in enumerate(tasks, 1):
            relative_path = location.relative_to(self.vault_path)
            clean_desc = self.clean_task_text(task_text)
            task_descriptions.append(f'{i}. "{task_text}" in {relative_path} (ID: {task_id})')
            task_id_map[(clean_desc, str(relative_path))] = task_id

        # Prompt the LLM to select 3 tasks and explain why, returning the ID for each
        prompt = f"""
You are MsBee, a gentle but clever assistant.

Here are your open tasks:
{chr(10).join(task_descriptions)}

And here's the user's high-level roadmap:
{roadmap}

Pick the three most important tasks for today, based on the roadmap and context. For each, copy the description, the full relative file path, and the ID exactly as shown above (not just the folder), and explain in 1-2 sentences why you picked it. Respond in Markdown like this:

## 🌟 Focus Tasks
1. "Task description" in path/to/file.md (ID: abc123) — reason
2. "Task description" in path/to/file.md (ID: def456) — reason
3. "Task description" in path/to/file.md (ID: ghi789) — reason

## 🐝 Nudge
Your motivational message here

## 🔒 Lock Screen Quote
"Your one-liner here"
"""
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        gpt_content = response.choices[0].message.content

        # Parse the LLM's response to extract the 3 chosen tasks (with ID)
        chosen_tasks = []
        reasons = []
        focus_section = re.search(r"## 🌟 Focus Tasks(.+?)(## |$)", gpt_content, re.DOTALL)
        if focus_section:
            lines = focus_section.group(1).strip().splitlines()
            for line in lines:
                m = re.match(r'\d+\.\s*"(.+?)" in ([^\s]+) \(ID: ([a-zA-Z0-9]{6})\)\s*[—-]\s*(.+)', line)
                if m:
                    desc, path, task_id, reason = m.groups()
                    chosen_tasks.append((desc, path, task_id))
                    reasons.append(reason)
                else:
                    # fallback: try to match without reason
                    m = re.match(r'\d+\.\s*"(.+?)" in ([^\s]+) \(ID: ([a-zA-Z0-9]{6})\)', line)
                    if m:
                        desc, path, task_id = m.groups()
                        chosen_tasks.append((desc, path, task_id))
                        reasons.append("")

        # Generate the tasks query using task IDs
        task_conditions = []
        for desc, path, task_id in chosen_tasks:
            if task_id:
                condition = f'(id includes {task_id})'
                task_conditions.append(condition)
        
        # Create the query
        if task_conditions:
            tasks_query = " OR ".join(task_conditions)
            if len(task_conditions) > 1:
                tasks_query = f'({tasks_query})'
        else:
            tasks_query = ""

        # Reconstruct the Focus Tasks section with reasons
        focus_md = ""
        if tasks_query:
            focus_md += f"```tasks\n{tasks_query}\n```\n"
        
        for i, (desc, path, task_id) in enumerate(chosen_tasks, 1):
            focus_md += f'{i}. "{desc}" in {path} (ID: {task_id})'
            if reasons[i-1]:
                focus_md += f' — {reasons[i-1]}'
            focus_md += '\n'

        # Reconstruct the rest of the LLM's response (nudge, quote)
        nudge_section = re.search(r'## 🐝 Nudge(.+?)(## |$)', gpt_content, re.DOTALL)
        nudge_md = nudge_section.group(0).strip() if nudge_section else ''
        quote_section = re.search(r'## 🔒 Lock Screen Quote(.+)', gpt_content, re.DOTALL)
        quote_md = quote_section.group(0).strip() if quote_section else ''

        return f"""## 🌟 Focus Tasks
{focus_md}
{nudge_md}\n\n{quote_md}"""

    def update_daily_note(self, content, note_date=date.today()):
        daily_note = self.daily_notes_path / f"{note_date.isoformat()}.md"
        if not daily_note.exists():
            print(f"Daily note not found: {daily_note}")
            return

        with open(daily_note, "r", encoding="utf-8") as f:
            text = f.read()

        # Look for the task markers
        start_marker = "<!-- START tasks -->"
        end_marker = "<!-- END tasks -->"
        
        if start_marker in text and end_marker in text:
            # Replace content between markers
            pattern = f"{start_marker}.*?{end_marker}"
            replacement = f"{start_marker}\n{content}\n{end_marker}"
            updated_text = re.sub(pattern, replacement, text, flags=re.DOTALL)
        else:
            # If markers don't exist, append the content with markers
            updated_text = text.strip() + f"\n\n{start_marker}\n{content}\n{end_marker}"

        with open(daily_note, "w", encoding="utf-8") as f:
            f.write(updated_text)

        print(f"MsBee section updated in: {daily_note}")

# === MAIN ===

if __name__ == "__main__":
    msbee = MsBee()
    print("Ensuring all open tasks have unique IDs...")
    add_task_ids_to_vault(msbee.vault_path)
    tasks = msbee.extract_tasks(today=date.today())
    roadmap = msbee.extract_roadmap()
    reply = msbee.ask_msbee(tasks, roadmap)
    msbee.update_daily_note(reply, note_date=date.today())
