# Smart Notes Aggregator

Local tool for aggregating raw Obsidian Inbox notes using a local LLM (Ollama). Scans `00_Inbox/`, lets you select notes, extracts structured information (summary, key points, topics, tasks), previews the output, then writes it safely to your vault.

## Stack

Plain Python + stdlib HTTP server, HTML/CSS/JS frontend, JSON state files, Ollama LLM.

## Quick start

```
cd interview_trainer
python server.py
```

Opens `http://127.0.0.1:8765` in your browser automatically.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally (`gemma4:e4b` model pulled)
- Obsidian vault at the path configured in `config/obsidian.json`

## Configuration

| File | Purpose |
|---|---|
| `config/obsidian.json` | Vault path and folder names |
| `config/models.json` | LLM model routing and Ollama URL |
| `config/app_config.json` | Limits and timeouts |

Edit `config/obsidian.json` to set `vault_path` and folder names for your vault.

## Workflow

1. **Scan Inbox** — lists all `.md` files in `00_Inbox/`, shows status (new / changed / processed)
2. **Select notes** — click to select one or more notes to aggregate
3. **Aggregate Selected** — sends notes to Ollama, extracts structured JSON (summary, key points, topics, tasks, connections, suggested target)
4. **Review result** — inspect the extraction in the result panel
5. **Preview** — verify where the block will be written before committing
6. **Approve & Write** — writes the AI block to the vault using safety markers; updates `data/processed_notes.json`

## Safety

- Raw source notes are **never modified**
- AI content is wrapped in `<!-- AI_AGGREGATED_START -->` … `<!-- AI_AGGREGATED_END -->` markers
- Source file hash is verified before every write; if the file changed since scan, the write is blocked
- Re-scan and re-aggregate after any source change

## Services

| Module | Role |
|---|---|
| `services/vault_scanner.py` | Scan inbox, compute hashes, diff against index |
| `services/note_parser.py` | Parse Markdown (frontmatter, headings, tasks) |
| `services/aggregator.py` | Call LLM, extract structured JSON result |
| `services/markdown_writer.py` | Write AI block with marker safety |
| `services/task_manager.py` | Format and store extracted tasks |
| `services/index_store.py` | Read/write JSON index files |
| `services/llm_router.py` | Route to correct model/provider |
| `services/ollama_client.py` | Ollama HTTP client |
| `services/openai_client.py` | OpenAI-compatible HTTP client |

## Data files

| File | Contents |
|---|---|
| `data/processed_notes.json` | Map of processed note paths → hash + targets |
| `data/topic_map.json` | Topic → source note mapping |
| `data/task_index.json` | All extracted tasks across notes |

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Ollama + vault connectivity |
| GET | `/api/config` | Read all configs |
| POST | `/api/config` | Update a config section |
| POST | `/api/scan` | Scan inbox, return note list |
| POST | `/api/aggregate` | Aggregate selected notes via LLM |
| POST | `/api/preview` | Preview what will be written |
| POST | `/api/write` | Write aggregation to vault |
| GET | `/api/index` | Read processed notes + tasks index |
