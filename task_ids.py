import re
import random
import string
from pathlib import Path

def generate_short_id():
    """Generate a short, unique ID for tasks."""
    # Use base62 characters (0-9, a-z, A-Z) for 6-character IDs
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(6))

def add_task_ids_to_lines(lines):
    """Add IDs to task lines that don't already have them."""
    updated_lines = []
    
    for line in lines:
        # Only process open task lines
        if line.startswith("- [ ]"):
            # Check if task already has an ID
            if "🆔 " in line:
                # Task already has an ID, leave unchanged
                updated_lines.append(line)
            else:
                # Task needs an ID
                # Find where to insert the ID (before any metadata)
                metadata_pattern = r'(\s*[➕📅⏭️⛔🆔]\s+\S+)'
                match = re.search(metadata_pattern, line)
                
                if match:
                    # Insert ID before the first metadata
                    insert_pos = match.start()
                    id_part = f" 🆔 {generate_short_id()}"
                    updated_line = line[:insert_pos] + id_part + line[insert_pos:]
                else:
                    # No metadata, append ID at the end
                    updated_line = line.rstrip() + f" 🆔 {generate_short_id()}"
                
                updated_lines.append(updated_line)
        else:
            # Not a task line, leave unchanged
            updated_lines.append(line)
    
    return updated_lines

def add_task_ids_to_vault(vault_path):
    """Update all .md files in the vault, adding IDs to open tasks that don't have them."""
    vault_path = Path(vault_path)
    for md_file in vault_path.rglob("*.md"):
        with open(md_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        updated_lines = add_task_ids_to_lines([line.rstrip("\n") for line in lines])
        # Only write if changes were made
        if updated_lines != [line.rstrip("\n") for line in lines]:
            with open(md_file, "w", encoding="utf-8") as f:
                f.write("\n".join(updated_lines) + "\n")
            print(f"Updated: {md_file}") 