# Smart Notes Aggregator

Local tool for processing Obsidian **Daily Notes** with a local LLM (Ollama).
Scans `02 Daily/`, lets you select one note at a time, extracts structured
knowledge (segments, tasks, habits), previews the output, then writes it
safely to your vault.

## Stack

Plain Python 3.10+ · stdlib HTTP server · HTML/CSS/JS frontend ·
JSON state files · Ollama LLM (OpenAI-compatible API also supported via config)

## Quick start

```
cd interview_trainer
python server.py
```

Opens `http://127.0.0.1:8765` automatically.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally with a model pulled (default: `gemma4:e4b`)
- Obsidian vault path set in `config/obsidian.json`

## Configuration

| File | Purpose |
|---|---|
| `config/obsidian.json` | Vault path, folder names, tasks file location |
| `config/models.json` | LLM routing, Ollama URL, timeout |
| `config/app_config.json` | Limits, scan extensions, habit keys |

Copy `config/obsidian.example.json` → `config/obsidian.json` and set `vault_path`.

## Workflow

1. **Scan Daily Notes** — lists `.md` files in `daily_folder`, shows status: new / changed / processed
2. **Select a note** — click to select **one** note (single-note contract; batch mode is in Etapa 9)
3. **Restructure Note** — sends the note to the LLM, extracts structured JSON (segments, tasks, habits)
4. **Edit segments** — adjust folder, filename, or content in the editable card before writing
5. **Preview Write Plan** — see exactly what will be written where, without touching the vault
6. **Approve & Write** — writes all segments atomically; updates index, Task Inbox, and habit fields

## Important behaviours

### Source note modification

The source daily note is modified **only** for habit fields (e.g. `english:: 1`).
All other content — including the AI block — goes to separate target files.
The UI shows a notice when habits will be written back to the source note.

### Safety

- Writes use a temp file + `Path.replace()` — no half-written files on crash
- Source file SHA-256 is verified at write time; stale `scan_hash` → 409 Conflict
- All vault paths are resolved and checked against the vault root (no `../` escapes)
- Re-scan and re-aggregate after any change to the source note

### Backup / recovery

The AI block is wrapped in markers:

```
<!-- AI_AGGREGATED_START:source=02 Daily/2025-06-01.md:date=2025-06-01 -->
…content…
<!-- AI_AGGREGATED_END -->
```

Re-processing the same source replaces only its block; other blocks in the
same target file are untouched. The block can be deleted manually at any time.

## Module map

```
server.py                  HTTP transport + routing
api/handlers.py            one function per endpoint
services/
  pipeline.py              aggregate → preview → write lifecycle
  aggregator.py            LLM call, JSON repair, segment/task validation
  habits.py                habit read / write / toggle
  validation.py            input validation helpers (ValueError on bad input)
  storage.py               safe_resolve, atomic_write, require_md
  markdown_writer.py       AI block build + hash-guarded write
  task_manager.py          task formatting + vault write
  vault_scanner.py         scan daily folder, hash diff
  index_store.py           processed notes + task index JSON
  llm_router.py            route to Ollama or OpenAI-compatible model
  note_parser.py           strip frontmatter and HTML comments
  config.py                cached config loader
```

## API response format

Every endpoint returns:

```json
{ "ok": true, "data": { … } }
```

On error:

```json
{ "ok": false, "error": { "code": "CONFLICT", "message": "Source file changed since scan" } }
```

Error codes: `BAD_REQUEST` · `NOT_FOUND` · `CONFLICT` · `INTERNAL_ERROR` ·
`LLM_UNAVAILABLE` · `LLM_TIMEOUT`

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Ollama + vault connectivity check |
| GET | `/api/config` | Read all config sections |
| POST | `/api/config` | Update one config section (`target` + `updates`) |
| POST | `/api/scan` | Scan daily folder, return note list with status |
| POST | `/api/aggregate` | Aggregate one note via LLM |
| POST | `/api/preview` | Preview write plan (no vault changes) |
| POST | `/api/write` | Write segments, tasks, habits atomically |
| POST | `/api/tasks/toggle` | Toggle task done/undone |
| POST | `/api/habits/toggle` | Toggle habit field in today's daily note |
| GET | `/api/habits` | Read all daily habit records |
| GET | `/api/index` | Read processed notes index + task list |

## Data files

| File | Contents |
|---|---|
| `data/processed_notes.json` | `{rel_path: {hash, processed_at, targets[]}}` |
| `data/task_index.json` | `[{text, source, due, priority, done}]` |

## Running tests

```
python -m pytest tests/ -v
```

All tests run in isolated temporary vaults — no real Obsidian files are read or written.
