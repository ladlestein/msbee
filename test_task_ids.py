import unittest
import re
import tempfile
import os
from pathlib import Path
from task_ids import add_task_ids_to_lines, generate_short_id, add_task_ids_to_vault

class TestTaskIds(unittest.TestCase):
    def test_generate_short_id(self):
        """Test that short IDs are generated correctly."""
        id1 = generate_short_id()
        id2 = generate_short_id()
        
        # IDs should be 6 characters long
        self.assertEqual(len(id1), 6)
        self.assertEqual(len(id2), 6)
        
        # IDs should be different
        self.assertNotEqual(id1, id2)
        
        # IDs should be alphanumeric (base62-like)
        self.assertTrue(id1.isalnum())
        self.assertTrue(id2.isalnum())

    def test_add_id_to_task_without_id(self):
        """Test adding ID to a task that doesn't have one."""
        lines = [
            "- [ ] Simple task",
            "- [ ] Another task with metadata ➕ 2025-06-30",
            "- [ ] Task with multiple metadata ➕ 2025-06-30 📅 2025-07-01"
        ]
        
        updated_lines = add_task_ids_to_lines(lines)
        
        # All tasks should now have IDs
        for line in updated_lines:
            if line.startswith("- [ ]"):
                self.assertIn("🆔 ", line)
                # ID should be before other metadata
                id_match = re.search(r'🆔 ([a-zA-Z0-9]{6})', line)
                self.assertIsNotNone(id_match)

    def test_preserve_existing_id(self):
        """Test that tasks with existing IDs are unchanged."""
        lines = [
            "- [ ] Task with existing ID 🆔 abc123",
            "- [ ] Task with ID and metadata 🆔 def456 ➕ 2025-06-30"
        ]
        
        updated_lines = add_task_ids_to_lines(lines)
        
        # Lines should be unchanged
        self.assertEqual(updated_lines[0], lines[0])
        self.assertEqual(updated_lines[1], lines[1])

    def test_id_placement(self):
        """Test that IDs are placed in the correct position."""
        lines = [
            "- [ ] Task with metadata ➕ 2025-06-30 📅 2025-07-01"
        ]
        
        updated_lines = add_task_ids_to_lines(lines)
        updated_line = updated_lines[0]
        
        # ID should be after the task description but before other metadata
        parts = updated_line.split()
        id_index = None
        plus_index = None
        
        for i, part in enumerate(parts):
            if part == "🆔":
                id_index = i
            elif part == "➕":
                plus_index = i
        
        self.assertIsNotNone(id_index)
        self.assertIsNotNone(plus_index)
        self.assertLess(id_index, plus_index)

    def test_non_task_lines_unchanged(self):
        """Test that non-task lines are not modified."""
        lines = [
            "# Header",
            "Some text",
            "- [x] Completed task",
            "- [ ] Task that needs ID",
            "More text"
        ]
        
        updated_lines = add_task_ids_to_lines(lines)
        
        # Non-task lines should be unchanged
        self.assertEqual(updated_lines[0], "# Header")
        self.assertEqual(updated_lines[1], "Some text")
        self.assertEqual(updated_lines[4], "More text")
        
        # Only the open task should get an ID
        self.assertIn("🆔 ", updated_lines[3])
        self.assertNotIn("🆔 ", updated_lines[2])  # Completed task

    def test_completed_tasks_unchanged(self):
        """Test that completed tasks are not modified."""
        lines = [
            "- [x] Completed task",
            "- [x] Completed task with ID 🆔 xyz789",
            "- [ ] Open task that needs ID"
        ]
        
        updated_lines = add_task_ids_to_lines(lines)
        
        # Completed tasks should be unchanged
        self.assertEqual(updated_lines[0], lines[0])
        self.assertEqual(updated_lines[1], lines[1])
        
        # Only open task should get an ID
        self.assertIn("🆔 ", updated_lines[2])

    def test_multiple_tasks_in_file(self):
        """Test handling multiple tasks in a file."""
        lines = [
            "# Daily Note",
            "",
            "- [ ] First task",
            "- [ ] Second task ➕ 2025-06-30",
            "- [ ] Third task with existing ID 🆔 abc123",
            "- [ ] Fourth task 📅 2025-07-01"
        ]
        
        updated_lines = add_task_ids_to_lines(lines)
        
        # Check that tasks without IDs got new ones
        self.assertIn("🆔 ", updated_lines[2])  # First task
        self.assertIn("🆔 ", updated_lines[3])  # Second task
        self.assertIn("🆔 ", updated_lines[5])  # Fourth task
        
        # Check that task with existing ID is unchanged
        self.assertEqual(updated_lines[4], lines[4])  # Third task unchanged

    def test_file_only_updated_if_changed(self):
        """Test that files are only updated if something changed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            test_file = tmpdir / "test.md"
            # Case 1: All tasks already have IDs
            lines_with_ids = [
                "- [ ] Task one 🆔 abc123",
                "- [ ] Task two 🆔 def456"
            ]
            test_file.write_text("\n".join(lines_with_ids) + "\n", encoding="utf-8")
            mtime_before = test_file.stat().st_mtime
            add_task_ids_to_vault(tmpdir)
            mtime_after = test_file.stat().st_mtime
            self.assertEqual(mtime_before, mtime_after, "File should not be modified if all tasks have IDs")

            # Case 2: At least one task missing an ID
            lines_missing_id = [
                "- [ ] Task one 🆔 abc123",
                "- [ ] Task two"
            ]
            test_file.write_text("\n".join(lines_missing_id) + "\n", encoding="utf-8")
            mtime_before = test_file.stat().st_mtime
            add_task_ids_to_vault(tmpdir)
            mtime_after = test_file.stat().st_mtime
            self.assertNotEqual(mtime_before, mtime_after, "File should be modified if a task is missing an ID")
            # Confirm the new line has an ID
            updated_lines = test_file.read_text(encoding="utf-8").splitlines()
            self.assertIn("🆔 ", updated_lines[1])

if __name__ == '__main__':
    unittest.main() 