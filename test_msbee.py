import unittest
from datetime import date
from pathlib import Path
import tempfile
import os
import shutil
from msbee import extract_tasks, clean_task_text, update_daily_note, escape_task_query
from unittest.mock import patch

class TestMsBee(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for our test vault
        self.test_dir = tempfile.TemporaryDirectory()
        self.vault_path = Path(self.test_dir.name)
        
        # Create a test vault structure
        self.daily_path = self.vault_path / "daily"
        self.daily_path.mkdir()
        
        # Set environment variables for the test vault
        self.old_vault_path = os.environ.get("MSBEE_VAULT_PATH")
        self.old_daily_path = os.environ.get("MSBEE_DAILY_PATH")
        os.environ["MSBEE_VAULT_PATH"] = str(self.vault_path)
        os.environ["MSBEE_DAILY_PATH"] = "daily"
        
        # Create a test file with some tasks
        self.test_file = self.vault_path / "test_tasks.md"
        with open(self.test_file, "w") as f:
            f.write("""# Test Tasks


- [ ] Uncompleted dependency
- [ ] Task without metadata
- [ ] Task with due date 📅 2024-12-31
- [ ] Task with dependency ⏭️ Uncompleted dependency
- [ ] Task with future start date 🛫 2025-01-01
- [x] Completed task
- [x] Completed task with metadata ➕ 2024-01-01
- [ ] Task with multiple metadata ➕ 2024-01-01 📅 2024-12-31 ⏭️ Uncompleted dependency
""")

    def tearDown(self):
        # Restore environment variables
        if self.old_vault_path:
            os.environ["MSBEE_VAULT_PATH"] = self.old_vault_path
        else:
            del os.environ["MSBEE_VAULT_PATH"]
            
        if self.old_daily_path:
            os.environ["MSBEE_DAILY_PATH"] = self.old_daily_path
        else:
            del os.environ["MSBEE_DAILY_PATH"]
            
        # Clean up the temporary directory
        self.test_dir.cleanup()

    def test_clean_task_text(self):
        """Test the task text cleaning function."""
        test_cases = [
            ("Simple task", "Simple task"),
            ("Task with due date 📅 2024-12-31", "Task with due date"),
            ("Task with dependency ⏭️ Wait for dependency", "Task with dependency"),
            ("Task with multiple ➕ 2024-01-01 📅 2024-12-31 ⏭️ Wait", "Task with multiple"),
            ("Task with all metadata ➕ 2024-01-01 📅 2024-12-31 ⏭️ Wait ⛔ abc123 🆔 xyz789", "Task with all metadata"),
        ]
        
        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                self.assertEqual(clean_task_text(input_text), expected)

    def test_extract_tasks_basic(self):
        """Test basic task extraction without dependencies."""
        tasks = extract_tasks(vault_path=self.vault_path, today=date(2024, 1, 1))
        
        # Should find all eligible tasks
        self.assertEqual(len(tasks), 3)
        
        # Check that completed tasks are not included
        task_texts = [task[0] for task in tasks]
        self.assertNotIn("Completed task", task_texts)
        self.assertNotIn("Completed task with metadata ➕ 2024-01-01", task_texts)

    def test_extract_tasks_future_date(self):
        """Test that tasks with future start dates are excluded."""
        tasks = extract_tasks(vault_path=self.vault_path, today=date(2024, 1, 1))
        
        # Check that the task with future start date is not included
        task_texts = [task[0] for task in tasks]
        self.assertNotIn("Task with future start date 🛫 2025-01-01", task_texts)

    def test_extract_tasks_dependencies(self):
        """Test task extraction with dependencies."""
        # Create a file with a dependency chain
        with open(self.test_file, "w") as f:
            f.write("""# Test Tasks

- [ ] Task A ⏭️ Task B
- [ ] Task B ⏭️ Task C
- [ ] Task C
""")
        
        tasks = extract_tasks(vault_path=self.vault_path, today=date(2024, 1, 1))
        
        # Only Task C should be included since it has no dependencies
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0][0], "Task C")

    def test_extract_tasks_completed_dependency(self):
        """Test that a task with a completed dependency is extracted."""
        # Create a file with a task that depends on a completed task
        with open(self.test_file, "w") as f:
            f.write("""# Test Tasks

- [x] Completed dependency task
- [ ] Task with completed dependency ⏭️ Completed dependency task
""")
        
        tasks = extract_tasks(vault_path=self.vault_path, today=date(2024, 1, 1))
        
        # The task with a completed dependency should be included
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0][0], "Task with completed dependency ⏭️ Completed dependency task")

    def test_extract_tasks_uncompleted_dependency(self):
        """Test that a task with an uncompleted dependency is not extracted."""
        # Create a file with a task that depends on an uncompleted task
        with open(self.test_file, "w") as f:
            f.write("""# Test Tasks

- [ ] Uncompleted dependency task
- [ ] Task with uncompleted dependency ⏭️ Uncompleted dependency task
""")
        
        tasks = extract_tasks(vault_path=self.vault_path, today=date(2024, 1, 1))
        
        # The dependency task should be included since it has no dependencies
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0][0], "Uncompleted dependency task")

    def test_update_daily_note_replaces_section(self):
        """Test that update_daily_note replaces an existing MsBee section."""
        today = date(2024, 1, 1)
        daily_note = self.daily_path / f"{today.isoformat()}.md"
        original_content = """# Daily Note

Some content here.

## 🐝 MsBee
Old content to be replaced.

## Another Section
More content.
"""
        with open(daily_note, "w") as f:
            f.write(original_content)
        
        new_content = "## 🌟 Focus Tasks\nNew MsBee content!"
        with patch("msbee.DAILY_NOTES_PATH", self.daily_path):
            update_daily_note(new_content, note_date=today)
        
        with open(daily_note, "r") as f:
            updated = f.read()
        self.assertIn(new_content, updated)
        self.assertNotIn("Old content to be replaced.", updated)
        self.assertIn("## Another Section", updated)

    def test_update_daily_note_inserts_section(self):
        """Test that update_daily_note inserts a MsBee section if not present."""
        today = date(2024, 1, 1)
        daily_note = self.daily_path / f"{today.isoformat()}.md"
        original_content = """# Daily Note

Some content here.

## Another Section
More content.
"""
        with open(daily_note, "w") as f:
            f.write(original_content)
        
        new_content = "## 🌟 Focus Tasks\nInserted MsBee content!"
        with patch("msbee.DAILY_NOTES_PATH", self.daily_path):
            update_daily_note(new_content, note_date=today)
        
        with open(daily_note, "r") as f:
            updated = f.read()
        self.assertIn(new_content, updated)
        self.assertIn("## Another Section", updated)
        self.assertTrue(updated.strip().endswith(new_content) or "## 🐝 MsBee" in updated)

    def test_escape_task_query(self):
        """Test the task query escaping function."""
        test_cases = [
            ("Simple task", "Simple task"),
            ("Task (important)", "Task \\(important\\)"),
            ("Task [urgent]", "Task \\[urgent\\]"),
            ("Task {critical}", "Task \\{critical\\}"),
            ("Task + bonus", "Task \\+ bonus"),
            ("Task * priority", "Task \\* priority"),
            ("Task? maybe", "Task\\? maybe"),
            ("Task | or", "Task \\| or"),
            ("Task ^ high", "Task \\^ high"),
            ("Task $ expensive", "Task \\$ expensive"),
            ("Task. period", "Task\\. period"),
            ("Task \\ backslash", "Task \\\\ backslash"),
            ("Task (with [multiple] {special} chars)", "Task \\(with \\[multiple\\] \\{special\\} chars\\)"),
        ]
        
        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                self.assertEqual(escape_task_query(input_text), expected)

if __name__ == '__main__':
    unittest.main() 