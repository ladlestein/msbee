#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_LINE_RE = re.compile(
    r'^(?P<indent>\s*)(?P<bullet>[-*+])\s+\[(?P<status>.?)\]\s+(?P<body>.*)$'
)

TAG_RE = re.compile(r'(?<!\w)#([a-zA-Z0-9_/\-]+)')
DATE_RE = r'(\d{4}-\d{2}-\d{2})'

FIELD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("due", re.compile(rf'📅\s*{DATE_RE}')),
    ("scheduled", re.compile(rf'⏳\s*{DATE_RE}')),
    ("start", re.compile(rf'🛫\s*{DATE_RE}')),
    ("created", re.compile(rf'➕\s*{DATE_RE}')),
    ("done", re.compile(rf'✅\s*{DATE_RE}')),
    ("cancelled", re.compile(rf'❌\s*{DATE_RE}')),
    ("time", re.compile(r'⏰\s*([0-2]\d:[0-5]\d)')),
    ("recurrence", re.compile(r'🔁\s*([^📅⏳🛫➕✅❌⏰⛔🆔]*?)(?=\s*(?:📅|⏳|🛫|➕|✅|❌|⏰|⛔|🆔|$))')),
    ("id", re.compile(r'🆔\s*([^\s]+)')),
    ("depends_on", re.compile(r'⛔\s*([^\s]+)')),
]

PRIORITY_MAP = {
    "🔺": "highest",
    "⏫": "high",
    "🔼": "medium",
    "🔽": "low",
    "⏬": "lowest",
    "⏬️": "lowest",
}

STATUS_MAP = {
    " ": {"status_type": "todo", "status_name": "todo", "completed": False, "cancelled": False},
    "x": {"status_type": "done", "status_name": "done", "completed": True, "cancelled": False},
    "X": {"status_type": "done", "status_name": "done", "completed": True, "cancelled": False},
    "/": {"status_type": "in_progress", "status_name": "in progress", "completed": False, "cancelled": False},
    "-": {"status_type": "cancelled", "status_name": "cancelled", "completed": False, "cancelled": True},
}

IGNORED_DIRS = {
    ".obsidian",
    ".git",
    ".trash",
    ".DS_Store",
    "node_modules",
    ".smart-env",
}


@dataclass
class TaskRecord:
    id: str
    text: str
    raw_line: str
    status_symbol: str
    status_type: str
    status_name: str
    completed: bool
    cancelled: bool
    priority: str | None
    due: str | None
    scheduled: str | None
    start: str | None
    created: str | None
    done: str | None
    cancelled_date: str | None
    time: str | None
    recurrence: str | None
    task_id: str | None
    depends_on: str | None
    tags: list[str]
    path: str
    line_number: int
    indent: int
    parent_path: str | None


def log(message: str, *, flush: bool = True) -> None:
    print(message, file=sys.stderr, flush=flush)


def stable_task_id(path: str, line_number: int, raw_line: str) -> str:
    digest = hashlib.sha1(f"{path}:{line_number}:{raw_line}".encode("utf-8")).hexdigest()[:16]
    return f"task_{digest}"


def parse_status(symbol: str) -> dict[str, Any]:
    return STATUS_MAP.get(
        symbol,
        {
            "status_type": "custom",
            "status_name": f"custom:{symbol or 'blank'}",
            "completed": False,
            "cancelled": False,
        },
    )


def extract_priority(text: str) -> tuple[str, str | None]:
    priority = None
    for emoji, value in PRIORITY_MAP.items():
        if emoji in text:
            priority = value
            text = text.replace(emoji, " ")
    return normalize_spaces(text), priority


def extract_fields(text: str) -> tuple[str, dict[str, str | None]]:
    fields: dict[str, str | None] = {
        "due": None,
        "scheduled": None,
        "start": None,
        "created": None,
        "done": None,
        "cancelled": None,
        "time": None,
        "recurrence": None,
        "id": None,
        "depends_on": None,
    }

    for field_name, pattern in FIELD_PATTERNS:
        match = pattern.search(text)
        if match:
            fields[field_name] = match.group(1).strip()
            text = text[:match.start()] + " " + text[match.end():]

    return normalize_spaces(text), fields


def extract_tags(text: str) -> list[str]:
    return sorted(set(m.group(1) for m in TAG_RE.finditer(text)))


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def should_skip(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def walk_markdown_files(vault_root: Path) -> list[Path]:
    files = []
    for p in vault_root.rglob("*.md"):
        if p.is_file() and not should_skip(p.relative_to(vault_root)):
            files.append(p)
    return sorted(files)


def parse_tasks_from_file(vault_root: Path, file_path: Path) -> list[TaskRecord]:
    rel_path = file_path.relative_to(vault_root).as_posix()
    tasks: list[TaskRecord] = []
    parent_stack: list[tuple[int, str]] = []

    with file_path.open("r", encoding="utf-8") as f:
        for i, raw in enumerate(f, start=1):
            line = raw.rstrip("\n")
            match = TASK_LINE_RE.match(line)
            if not match:
                continue

            indent_spaces = len(match.group("indent"))
            status_symbol = match.group("status")
            body = match.group("body")

            status = parse_status(status_symbol)
            body, priority = extract_priority(body)
            body, fields = extract_fields(body)
            text = normalize_spaces(body)
            tags = extract_tags(text)

            while parent_stack and parent_stack[-1][0] >= indent_spaces:
                parent_stack.pop()

            parent_path = parent_stack[-1][1] if parent_stack else None

            task = TaskRecord(
                id=stable_task_id(rel_path, i, line),
                text=text,
                raw_line=line,
                status_symbol=status_symbol,
                status_type=status["status_type"],
                status_name=status["status_name"],
                completed=status["completed"],
                cancelled=status["cancelled"],
                priority=priority,
                due=fields["due"],
                scheduled=fields["scheduled"],
                start=fields["start"],
                created=fields["created"],
                done=fields["done"],
                cancelled_date=fields["cancelled"],
                time=fields["time"],
                recurrence=fields["recurrence"],
                task_id=fields["id"],
                depends_on=fields["depends_on"],
                tags=tags,
                path=rel_path,
                line_number=i,
                indent=indent_spaces,
                parent_path=parent_path,
            )
            tasks.append(task)
            parent_stack.append((indent_spaces, task.id))

    return tasks


def build_output(vault_root: Path, tasks: list[TaskRecord]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).astimezone().isoformat()

    undone_tasks = [t for t in tasks if (not t.completed) and (not t.cancelled)]

    by_status: dict[str, int] = {}
    by_tag: dict[str, int] = {}

    for task in undone_tasks:
        by_status[task.status_type] = by_status.get(task.status_type, 0) + 1
        for tag in task.tags:
            by_tag[tag] = by_tag.get(tag, 0) + 1

    return {
        "generated_at": now,
        "vault_root": str(vault_root),
        "task_count": len(undone_tasks),
        "summary": {
            "open_count": len(undone_tasks),
            "done_count": 0,
            "cancelled_count": 0,
            "by_status": dict(sorted(by_status.items())),
            "top_tags": [
                {"tag": tag, "count": count}
                for tag, count in sorted(by_tag.items(), key=lambda kv: (-kv[1], kv[0]))[:50]
            ],
        },
        "tasks": [asdict(task) for task in undone_tasks],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="export obsidian markdown tasks into one canonical json file"
    )
    parser.add_argument("vault", type=Path, help="path to obsidian vault")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("all_tasks.json"),
        help="output json file path",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="pretty-print json",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=100,
        help="print progress every n files (default: 100)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print every file as it is scanned",
    )
    args = parser.parse_args()

    start_time = time.monotonic()

    vault_root = args.vault.expanduser().resolve()
    output_path = args.output.expanduser().resolve()

    if not vault_root.exists() or not vault_root.is_dir():
        raise SystemExit(f"vault path does not exist or is not a directory: {vault_root}")

    log(f"scanning vault: {vault_root}")
    log("building markdown file list...")

    markdown_files = walk_markdown_files(vault_root)
    total_files = len(markdown_files)

    log(f"found {total_files} markdown files")
    if total_files == 0:
        log("no markdown files found; writing empty output anyway")

    all_tasks: list[TaskRecord] = []
    files_with_tasks = 0

    for idx, md_file in enumerate(markdown_files, start=1):
        rel_path = md_file.relative_to(vault_root).as_posix()

        if args.verbose:
            log(f"[{idx}/{total_files}] scanning {rel_path}")

        file_tasks = parse_tasks_from_file(vault_root, md_file)
        undone_file_tasks = [t for t in file_tasks if (not t.completed) and (not t.cancelled)]
        if undone_file_tasks:
            files_with_tasks += 1
            all_tasks.extend(undone_file_tasks)

        if (not args.verbose) and (
            idx == 1
            or idx == total_files
            or idx % max(args.progress_every, 1) == 0
        ):
            elapsed = time.monotonic() - start_time
            log(
                f"[{idx}/{total_files}] files scanned, "
                f"{files_with_tasks} files with tasks, "
                f"{len(all_tasks)} tasks found, "
                f"{elapsed:.1f}s elapsed"
            )

    log("building json payload...")
    payload = build_output(vault_root, all_tasks)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    log(f"writing output: {output_path}")
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2 if args.pretty else None, ensure_ascii=False)

    elapsed = time.monotonic() - start_time
    log(
        f"done. wrote {len(all_tasks)} tasks from {files_with_tasks} files "
        f"to {output_path} in {elapsed:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
