class Task:
    def __init__(self, text, location, start_date=None, dependencies=None):
        self.text = text
        self.location = location
        self.start_date = start_date
        self.dependencies = dependencies or set()
        self.is_completed = False

    def is_eligible(self, today):
        """Check if the task is eligible to be done."""
        # Task is not eligible if it's already completed
        if self.is_completed:
            return False
        
        # Task is not eligible if it has a future start date
        if self.start_date and self.start_date > today:
            return False
        
        # Task is not eligible if it has dependencies
        if len(self.dependencies) > 0:
            return False
        
        return True 