import re
from pathlib import Path
from msbee import MsBee

def fake_tasks():
    # Returns a list of (task_text, location, task_id)
    return [
        ("Do the thing 🆔 abc123", Path("folder1/file1.md"), "abc123"),
        ("Write report 🆔 def456", Path("folder2/file2.md"), "def456"),
        ("Plan project 🆔 ghi789", Path("folder3/file3.md"), "ghi789"),
    ]

def test_query_generation_basic(monkeypatch):
    msbee = MsBee(vault_path='.')
    tasks = fake_tasks()
    roadmap = "- Do the thing\n- Write report\n- Plan project"

    # Simulate LLM response
    llm_response = '''
## 🌟 Focus Tasks
1. "Do the thing 🆔 abc123" in folder1/file1.md (ID: abc123) — Most urgent
2. "Write report 🆔 def456" in folder2/file2.md (ID: def456) — Due soon
3. "Plan project 🆔 ghi789" in folder3/file3.md (ID: ghi789) — Important for roadmap

## 🐝 Nudge
Keep going!

## 🔒 Lock Screen Quote
"You got this!"
'''

    # Patch the OpenAI client to return our fake response
    class FakeChoice:
        def __init__(self, content):
            self.message = type('msg', (), {'content': content})
    class FakeResponse:
        def __init__(self, content):
            self.choices = [FakeChoice(content)]
    def fake_create(*args, **kwargs):
        return FakeResponse(llm_response)
    monkeypatch.setattr(msbee.client.chat.completions, "create", fake_create)

    result = msbee.ask_msbee(tasks, roadmap)
    # The query should use all three IDs
    assert 'id includes abc123' in result
    assert 'id includes def456' in result
    assert 'id includes ghi789' in result
    # Should not mention problematic character warnings
    assert 'cannot be queried' not in result
    # Should have a single tasks code block
    assert result.count('```tasks') == 1
    # Should have all three tasks listed
    assert result.count('(ID: ') == 3


def test_query_generation_partial(monkeypatch):
    msbee = MsBee(vault_path='.')
    tasks = fake_tasks()
    roadmap = "- Do the thing\n- Write report\n- Plan project"

    # Simulate LLM response with only two tasks
    llm_response = '''
## 🌟 Focus Tasks
1. "Do the thing 🆔 abc123" in folder1/file1.md (ID: abc123) — Most urgent
2. "Plan project 🆔 ghi789" in folder3/file3.md (ID: ghi789) — Important for roadmap

## 🐝 Nudge
Keep going!

## 🔒 Lock Screen Quote
"You got this!"
'''
    class FakeChoice:
        def __init__(self, content):
            self.message = type('msg', (), {'content': content})
    class FakeResponse:
        def __init__(self, content):
            self.choices = [FakeChoice(content)]
    def fake_create(*args, **kwargs):
        return FakeResponse(llm_response)
    monkeypatch.setattr(msbee.client.chat.completions, "create", fake_create)

    result = msbee.ask_msbee(tasks, roadmap)
    assert 'id includes abc123' in result
    assert 'id includes ghi789' in result
    assert 'id includes def456' not in result
    assert result.count('```tasks') == 1
    assert result.count('(ID: ') == 2
    assert result.count('in folder') == 2 