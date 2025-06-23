#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

// parse lines like '- [ ] task' or '- [x] done'
// if same line or next line has 'start: yyyy-mm-dd', store that.
function parseTasksFromMarkdown(text) {
  const lines = text.split('\n');
  const tasks = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const match = line.match(/^\s*[-*]\s*\[(x| |X)?\]\s+(.*)$/);
    if (match) {
      const isDone = match[1] && match[1].toLowerCase() === 'x';
      const taskText = match[2].trim();
      let startDate = null;

      // check same line
      const sameLineStartMatch = taskText.match(/start:\s*(\d{4}-\d{2}-\d{2})/);
      if (sameLineStartMatch) {
        startDate = sameLineStartMatch[1];
      } else {
        // next line
        const nextLine = lines[i + 1];
        if (nextLine) {
          const nextLineMatch = nextLine.trim().match(/^start:\s*(\d{4}-\d{2}-\d{2})$/);
          if (nextLineMatch) {
            startDate = nextLineMatch[1];
          }
        }
      }

      tasks.push({
        text: taskText,
        done: isDone,
        start: startDate,
      });
    }
  }

  return tasks;
}

function collectMdFilesRecursively(dirPath) {
  let mdFiles = [];
  try {
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dirPath, entry.name);
      if (entry.isFile() && entry.name.endsWith('.md')) {
        mdFiles.push(fullPath);
      } else if (entry.isDirectory()) {
        mdFiles = mdFiles.concat(collectMdFilesRecursively(fullPath));
      }
    }
  } catch (err) {
    console.error(`error reading directory: ${dirPath}`, err);
  }
  return mdFiles;
}

const vaultPath = "/Users/LEdelstein/Library/CloudStorage/OneDrive-PERFORCESOFTWARE,INC/Documents/Caravan";

function fetchVaultTasks() {
  let collectedTasks = [];
  const mdFiles = collectMdFilesRecursively(vaultPath);

  for (const filePath of mdFiles) {
    try {
      const fileContent = fs.readFileSync(filePath, 'utf8');
      const fileTasks = parseTasksFromMarkdown(fileContent);
      collectedTasks = collectedTasks.concat(fileTasks);
    } catch (err) {
      console.error('error reading file:', filePath, err);
    }
  }

  return collectedTasks;
}

// tasks that are not done, and their start date is either not set or < tomorrow
function isAvailable(startDate) {
  if (!startDate) return true; // no start date => show
  const d = new Date(startDate);
  const now = new Date();
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  return d < tomorrow;
}

const allTasks = fetchVaultTasks();
const filteredTasks = allTasks.filter(t => !t.done && isAvailable(t.start));

console.log(`found ${filteredTasks.length} tasks that are not done and not scheduled for later:`);
filteredTasks.forEach(t => {
  console.log(`- [ ] ${t.text} (start: ${t.start || 'no date'})`);
});
