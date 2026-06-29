# second-brain-autopilot

Local autopilot for your Obsidian second brain. Scans daily notes, uses a local LLM (Ollama) to restructure them into permanent knowledge notes, and tracks habits + tasks — all without leaving your machine.

## What it does

- **Restructures daily notes** — splits mixed content by topic, writes clean permanent notes into your vault
- **Habit tracker** — reads `habit:: 0/1` fields from daily notes, shows last 7 days per habit, click today's dot to toggle
- **Task tracker** — extracts tasks from notes, shows open ones in a sidebar, click to mark done
- **AI habit detection** — LLM reads note content and auto-sets which habits were done that day
- **Grammar correction** — AI fixes spelling and grammar while preserving all content
- **Duplicate prevention** — re-processing a note rewrites the existing block, never duplicates

## AI System Builder

The **Create System** screen turns a goal prompt into a validated configuration
for dynamic tables, habits, and weekly metrics. The user reviews the JSON before
it is saved in SQLite. The LLM never generates SQL or writes directly to the
database.

Workflow:

1. Describe the goal, constraints, horizon, and tracking needs.
2. Generate and review the system config.
3. Approve the config to save the whole system in one transaction.
4. Add type-checked records through generated forms.
5. Preview and approve the Markdown export to Obsidian.

## Stack

Plain Python + stdlib HTTP server · Vanilla JS/CSS frontend · Ollama local LLM · JSON state files

No npm, no pip dependencies, no cloud.

## Quick start

1. Install [Ollama](https://ollama.com) and pull the model:
   ```
   ollama pull gemma4:e4b
   ```

2. Copy config templates and fill in your vault path:
   ```
   copy second_brain_autopilot\config\obsidian.example.json second_brain_autopilot\config\obsidian.json
   copy second_brain_autopilot\config\models.example.json second_brain_autopilot\config\models.json
   ```
   Edit `obsidian.json` → set `vault_path` to your Obsidian vault folder.

3. Start:
   ```
   start.bat
   ```
   Opens `http://127.0.0.1:8765` automatically.

## Requirements

- Python 3.10+
- Ollama running locally (`gemma4:e4b` or any model)
- Obsidian vault with daily notes named `YYYY-MM-DD.md`

## Configuration

| File | Purpose |
|---|---|
| `config/obsidian.json` | Vault path and folder names (gitignored) |
| `config/models.json` | LLM model routing and Ollama URL (gitignored) |
| `config/app_config.json` | Limits and timeouts |

## Workflow

1. **Scan Daily Notes** — lists notes from your daily folder, shows status: new / changed / processed
2. **Select a note** — click to select; already-processed notes show a green banner with targets
3. **Restructure Note** — sends note to Ollama, extracts structured JSON (segments, tasks, habits)
4. **Review** — inspect segments, change folder/filename per segment if needed
5. **Preview Write Plan** — verify where each file will be written before committing
6. **Approve & Write** — writes notes to vault, logs tasks, updates habit fields in source note

## Habit fields

Add these to your daily note template:

```markdown
## Habits
english:: 0
3d:: 0
learning:: 0
reading:: 0
walking:: 0
training:: 0
```

The AI auto-detects which habits were done from the note content and updates the fields.

## Safety

- Source daily notes are **never deleted or overwritten** (only habit fields are updated)
- AI content in knowledge notes is wrapped in `<!-- AI_AGGREGATED_START:source=...:date=... -->` markers
- Re-processing a note replaces only its own block in target files
- Source file hash is verified before every write; changed files are blocked until re-scanned

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Ollama + vault status |
| GET | `/api/habits` | Habit history from daily notes |
| POST | `/api/habits/toggle` | Toggle today's habit directly |
| POST | `/api/scan` | Scan daily folder |
| POST | `/api/aggregate` | Restructure note via LLM |
| POST | `/api/preview` | Preview write plan |
| POST | `/api/write` | Write to vault |
| GET | `/api/index` | Processed notes + task index |
| POST | `/api/tasks/toggle` | Mark task done/undone |
| POST | `/api/systems/generate` | Generate and validate an unsaved system config |
| GET/POST | `/api/systems` | List or create systems |
| GET/DELETE | `/api/systems/{id}` | Read or delete a system |
| GET/POST | `/api/entities/{id}/records` | List or create dynamic records |
| PATCH/DELETE | `/api/records/{id}` | Update or delete a record |
| POST | `/api/systems/{id}/export` | Preview or write an Obsidian export |
