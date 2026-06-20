from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from services import (
    aggregator,
    config,
    index_store,
    markdown_writer,
    ollama_client,
    task_manager,
    vault_scanner,
)

_ROOT = Path(__file__).resolve().parent
_STATIC = _ROOT / "static"
_CONFIG_DIR = _ROOT / "config"

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".ico": "image/x-icon",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: ARG002
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = 400) -> None:
        self._send_json({"error": message}, status)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _serve_static(self, path: str) -> None:
        if path == "/" or path == "":
            path = "/index.html"
        file_path = _STATIC / path.lstrip("/")
        if not file_path.exists() or not file_path.is_file():
            self.send_response(404)
            self.end_headers()
            return
        suffix = file_path.suffix
        mime = _MIME.get(suffix, "application/octet-stream")
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/health":
            self._handle_health()
        elif path == "/api/config":
            self._handle_get_config()
        elif path == "/api/index":
            self._handle_get_index()
        elif path == "/api/habits":
            self._handle_get_habits()
        else:
            self._serve_static(path)

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        handlers = {
            "/api/config": self._handle_post_config,
            "/api/scan": self._handle_scan,
            "/api/aggregate": self._handle_aggregate,
            "/api/preview": self._handle_preview,
            "/api/write": self._handle_write,
            "/api/tasks/toggle": self._handle_toggle_task,
            "/api/habits/toggle": self._handle_habit_toggle,
        }
        handler = handlers.get(path)
        if handler:
            handler()
        else:
            self._send_error("Not found", 404)

    def _handle_health(self) -> None:
        obs = config.get_obsidian()
        models = config.get_models()
        base_url = models.get("ollama_base_url", "http://127.0.0.1:11434")
        timeout = config.get_app().get("health_check_timeout", 2)

        ollama_ok = False
        ollama_models: list[str] = []
        try:
            ollama_models = ollama_client.list_models(base_url=base_url, timeout=timeout)
            ollama_ok = True
        except Exception:
            pass

        vault_path = obs.get("vault_path", "")
        vault_ok = Path(vault_path).exists() if vault_path else False
        daily_ok = False
        if vault_ok:
            daily_ok = (Path(vault_path) / obs.get("daily_folder", "01_Daily")).exists()

        self._send_json({
            "ollama": ollama_ok,
            "ollama_models": ollama_models,
            "vault_exists": vault_ok,
            "daily_exists": daily_ok,
            "vault_path": vault_path,
        })

    def _handle_get_config(self) -> None:
        self._send_json({
            "app": config.get_app(),
            "obsidian": config.get_obsidian(),
            "models": config.get_models(),
        })

    def _handle_post_config(self) -> None:
        body = self._read_body()
        target = body.get("target")
        updates = body.get("updates", {})
        config_map = {
            "obsidian": _CONFIG_DIR / "obsidian.json",
            "models": _CONFIG_DIR / "models.json",
            "app": _CONFIG_DIR / "app_config.json",
        }
        if target not in config_map:
            self._send_error(f"Unknown config target: {target}")
            return
        path = config_map[target]
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
            current.update(updates)
            path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
            config.invalidate(target)
            self._send_json({"ok": True, "config": current})
        except Exception as exc:
            self._send_error(str(exc), 500)

    def _handle_scan(self) -> None:
        try:
            notes = vault_scanner.scan_daily_notes()
            self._send_json({"notes": notes, "count": len(notes)})
        except Exception as exc:
            self._send_error(str(exc), 500)

    def _handle_aggregate(self) -> None:
        body = self._read_body()
        rel_paths = body.get("rel_paths", [])
        if not rel_paths:
            self._send_error("rel_paths is required")
            return
        provider = body.get("provider", "ollama")
        api_key = body.get("apiKey", "") or os.environ.get("OPENAI_API_KEY", "")
        user_model = body.get("model") or None
        base_url = (body.get("baseUrl") or "").rstrip("/") or None
        try:
            existing_files = vault_scanner.list_knowledge_files()
            result = aggregator.aggregate(
                rel_paths,
                provider=provider,
                api_key=api_key,
                user_model=user_model,
                base_url=base_url,
                existing_files=existing_files,
            )
            if not result["result"].get("parse_error"):
                for rel in rel_paths:
                    task_manager.store_tasks_from_aggregation(rel, result["result"])
            self._send_json(result)
        except Exception as exc:
            self._send_error(str(exc), 500)

    def _handle_preview(self) -> None:
        body = self._read_body()
        source_rel = body.get("source_rel", "")
        segments = body.get("segments", [])
        if not source_rel or not segments:
            self._send_error("source_rel and segments are required")
            return
        try:
            previews = [
                markdown_writer.preview_write(
                    source_rel,
                    seg.get("folder_key", "knowledge_folder"),
                    seg.get("filename", "Note.md"),
                    seg.get("content", ""),
                    seg.get("connections") or [],
                )
                for seg in segments
            ]
            self._send_json({"previews": previews})
        except Exception as exc:
            self._send_error(str(exc), 500)

    @staticmethod
    def _set_note_field(note_path: Path, key: str, value: int) -> bool:
        """Write key:: value to a note file. Returns True if the file changed."""
        text = note_path.read_text(encoding="utf-8", errors="ignore")
        pattern = re.compile(rf"^{re.escape(key)}::\s*\d+(?:\.\d+)?", re.MULTILINE)
        new_line = f"{key}:: {value}"
        if pattern.search(text):
            new_text = pattern.sub(new_line, text)
        else:
            new_text = text.rstrip() + f"\n{new_line}\n"
        if new_text == text:
            return False
        note_path.write_text(new_text, encoding="utf-8")
        return True

    def _sync_hash(self, note_path: Path, source_rel: str) -> None:
        new_hash = hashlib.sha256(note_path.read_bytes()).hexdigest()
        index_store.update_note_hash(source_rel, new_hash)

    def _write_habits_to_note(self, source_rel: str, habits: dict) -> bool:
        obs = config.get_obsidian()
        note_path = Path(obs.get("vault_path", "")) / source_rel
        if not note_path.exists():
            return False
        text = note_path.read_text(encoding="utf-8", errors="ignore")
        changed = False
        for key, raw_val in habits.items():
            if not raw_val:
                continue
            pattern = re.compile(rf"^{re.escape(key)}::\s*(\d+(?:\.\d+)?)", re.MULTILINE)
            m = pattern.search(text)
            existing = float(m.group(1)) if m else 0.0
            new_val = int(max(existing, float(raw_val)))
            if new_val == int(existing):
                continue
            new_line = f"{key}:: {new_val}"
            text = pattern.sub(new_line, text) if m else text.rstrip() + f"\n{new_line}\n"
            changed = True
        if changed:
            note_path.write_text(text, encoding="utf-8")
        return changed

    def _handle_write(self) -> None:
        body = self._read_body()
        source_rel = body.get("source_rel", "")
        segments = body.get("segments", [])
        tasks = body.get("tasks", [])
        habits = body.get("habits", {})
        scan_hash = body.get("scan_hash", "")

        # ── Input validation (fail before any writes) ─────────────────────
        if not source_rel:
            self._send_error("source_rel is required")
            return
        if not segments:
            self._send_error("segments is required and must be non-empty")
            return
        valid_folder_keys = {
            "knowledge_folder", "areas_folder", "projects_folder",
            "tracking_folder", "archive_folder",
        }
        for i, seg in enumerate(segments):
            folder_key = seg.get("folder_key", "")
            filename = (seg.get("filename") or "").strip()
            if folder_key not in valid_folder_keys:
                self._send_error(f"segment[{i}]: unknown folder_key '{folder_key}'")
                return
            if not filename or not filename.endswith(".md"):
                self._send_error(f"segment[{i}]: filename must be a non-empty .md name, got '{filename}'")
                return
        if not scan_hash:
            self._send_error("scan_hash is required")
            return

        try:
            results = []
            for seg in segments:
                r = markdown_writer.write_aggregation(
                    source_rel,
                    seg.get("folder_key", "knowledge_folder"),
                    seg.get("filename", "Note.md"),
                    seg.get("content", ""),
                    seg.get("connections") or [],
                    scan_hash=scan_hash,
                )
                if not r["success"]:
                    self._send_error(r["error"], 409)
                    return
                results.append(r)

            # Update index once, with all targets, deduplicated
            all_targets = list(dict.fromkeys(r["target_path"] for r in results))
            source_hash = results[0]["source_hash"]
            index_store.mark_processed(source_rel, source_hash, all_targets)

            tasks_result = {}
            if tasks:
                tasks_result = task_manager.write_tasks_to_vault(tasks, source_rel)
            habits_written = self._write_habits_to_note(source_rel, habits) if habits else False
            if habits_written:
                obs = config.get_obsidian()
                note_path = Path(obs.get("vault_path", "")) / source_rel
                if note_path.exists():
                    self._sync_hash(note_path, source_rel)
            self._send_json({"written": results, "tasks_written": tasks_result, "habits_written": habits_written})
        except Exception as exc:
            self._send_error(str(exc), 500)

    def _handle_toggle_task(self) -> None:
        body = self._read_body()
        text = body.get("text", "")
        source = body.get("source", "")
        if not text:
            self._send_error("text is required")
            return
        task = index_store.toggle_task(text, source)
        if task is None:
            self._send_error("task not found", 404)
            return
        # Sync done status to Task Inbox.md in vault
        obs = config.get_obsidian()
        vault = Path(obs.get("vault_path", ""))
        tasks_path_str = obs.get("tasks_file", "06 Tracking/Task Inbox.md")
        tasks_file = vault / tasks_path_str
        if tasks_file.exists():
            content = tasks_file.read_text(encoding="utf-8", errors="ignore")
            new_mark = "x" if task["done"] else " "
            old_mark = " " if task["done"] else "x"
            escaped = re.escape(text)
            content = re.sub(
                rf"^- \[{old_mark}\] {escaped}",
                f"- [{new_mark}] {text}",
                content, flags=re.MULTILINE,
            )
            tasks_file.write_text(content, encoding="utf-8")
        self._send_json({"ok": True, "done": task["done"]})

    def _handle_habit_toggle(self) -> None:
        body = self._read_body()
        key = body.get("key", "")
        value = body.get("value")  # 0 or 1 from frontend, None = auto-toggle
        _valid = tuple(config.get_app().get("habit_keys", ["english", "3d", "learning", "reading", "walking", "training"]))
        if key not in _valid:
            self._send_error(f"invalid habit key: {key}")
            return
        obs = config.get_obsidian()
        vault = Path(obs.get("vault_path", ""))
        daily_folder = obs.get("daily_folder", "02 Daily")
        today = datetime.date.today().isoformat()
        note_path = vault / daily_folder / f"{today}.md"
        if not note_path.exists():
            self._send_error(f"Today's note not found: {today}.md", 404)
            return
        if value is None:
            text = note_path.read_text(encoding="utf-8", errors="ignore")
            m = re.search(rf"^{re.escape(key)}::\s*(\d+(?:\.\d+)?)", text, re.MULTILINE)
            current = float(m.group(1)) if m else 0.0
            value = 0 if current >= 1 else 1
        rel_path = f"{daily_folder}/{today}.md"
        self._set_note_field(note_path, key, int(value))
        self._sync_hash(note_path, rel_path)
        self._send_json({"ok": True, "key": key, "value": value, "date": today})

    def _handle_get_habits(self) -> None:
        obs = config.get_obsidian()
        vault = Path(obs.get("vault_path", ""))
        daily_folder = obs.get("daily_folder", "02 Daily")
        daily_path = vault / daily_folder

        habit_keys = config.get_app().get("habit_keys", ["english", "3d", "learning", "reading", "walking", "training"])
        keys_pattern = "|".join(re.escape(k) for k in habit_keys)
        field_re = re.compile(
            rf"^({keys_pattern})::\s*(\d+(?:\.\d+)?)",
            re.MULTILINE,
        )

        records: list[dict] = []
        if daily_path.exists():
            for f in sorted(daily_path.glob("*.md")):
                try:
                    datetime.date.fromisoformat(f.stem)
                except ValueError:
                    continue
                text = f.read_text(encoding="utf-8", errors="ignore")
                rec: dict = {"date": f.stem, **{k: 0 for k in habit_keys}}
                for m in field_re.finditer(text):
                    rec[m.group(1)] = float(m.group(2))
                records.append(rec)

        self._send_json({"habits": records})

    def _handle_get_index(self) -> None:
        self._send_json({
            "processed": index_store.get_processed(),
            "tasks": index_store.get_tasks(),
        })


def main() -> None:
    port = int(os.environ.get("PORT", 8765))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Smart Notes Aggregator → {url}")
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
