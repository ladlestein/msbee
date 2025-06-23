import unittest
from datetime import date
from pathlib import Path
from task import Task

class TestTask(unittest.TestCase):
    def setUp(self):
        self.today = date(2024, 1, 1)
        self.task = Task(
            text="Test task ➕ 2024-01-01 📅 2024-12-31 ⏭️ Dependency task",
            location=Path("test.md"),
            start_date=date(2024, 1, 1),
            dependencies={"Dependency task"}
        )

    def test_is_eligible(self):
        """Test if the task is eligible to be done."""
        # This test will be implemented later
        pass

    def test_is_eligible_no_dates_or_dependencies(self):
        """Test that a task with no dates or dependencies is eligible."""
        simple_task = Task(
            text="Simple task",
            location=Path("test.md")
        )
        self.assertTrue(simple_task.is_eligible(self.today))

    def test_is_eligible_completed_task(self):
        """Test that a completed task is not eligible."""
        completed_task = Task(
            text="Completed task",
            location=Path("test.md")
        )
        completed_task.is_completed = True
        self.assertFalse(completed_task.is_eligible(self.today))

    def test_is_eligible_with_uncompleted_dependency(self):
        """Test that a task with an uncompleted dependency is not eligible."""
        dependency_task = Task(
            text="Dependency task",
            location=Path("test.md")
        )
        # Dependency task is not completed (is_completed defaults to False)
        
        dependent_task = Task(
            text="Dependent task",
            location=Path("test.md"),
            dependencies={dependency_task}
        )
        
        self.assertFalse(dependent_task.is_eligible(self.today))

if __name__ == '__main__':
    unittest.main() 