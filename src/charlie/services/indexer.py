from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.models import ComponentType, MatchKind
from .db import init_db
from .scanner import _iter_playbook_yamls, _source_name

_DQ_PATTERN = re.compile(r"\$\{(?:incident|CustomFields)\.([^}]+)\}")

_FIELD_SETTERS = frozenset({
    "setIncident",
    "Builtin|||setIncident",
    "setIndicator",
    "Builtin|||setIndicator",
})


@dataclass
class IndexStats:
    files_indexed: int
    refs_found: int
    duration_s: float


def build_index(repo: Path, db_path: Path) -> IndexStats:
    init_db(db_path)
    start = time.monotonic()
    files_indexed = 0
    refs_found = 0

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("DELETE FROM refs")
        conn.execute("DELETE FROM components")

        for file_path, yaml_data in _iter_playbook_yamls(repo):
            source_name = _source_name(file_path, yaml_data)

            cursor = conn.execute(
                "INSERT OR IGNORE INTO components (name, type, file_path) VALUES (?, ?, ?)",
                (source_name, ComponentType.PLAYBOOK.value, str(file_path)),
            )
            if cursor.lastrowid:
                source_id = cursor.lastrowid
            else:
                source_id = conn.execute(
                    "SELECT id FROM components WHERE name = ? AND type = ?",
                    (source_name, ComponentType.PLAYBOOK.value),
                ).fetchone()[0]

            raw_refs = _extract_all_refs(yaml_data)
            if raw_refs:
                conn.executemany(
                    """INSERT INTO refs
                       (source_id, target_name, target_type, yaml_path, line, match_kind, context)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            source_id,
                            r["target_name"],
                            r["target_type"],
                            r["yaml_path"],
                            r["line"],
                            r["match_kind"],
                            r["context"],
                        )
                        for r in raw_refs
                    ],
                )
            files_indexed += 1
            refs_found += len(raw_refs)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return IndexStats(
        files_indexed=files_indexed,
        refs_found=refs_found,
        duration_s=time.monotonic() - start,
    )


def _extract_all_refs(yaml_data: dict) -> list[dict]:
    refs: list[dict] = []
    tasks = yaml_data.get("tasks", {})
    if not isinstance(tasks, dict):
        return refs

    for task_id, task_entry in tasks.items():
        if not isinstance(task_entry, dict):
            continue
        task_def = task_entry.get("task", {})
        if not isinstance(task_def, dict):
            continue
        refs.extend(_refs_from_task(str(task_id), task_entry, task_def, task_entry.get("type", "")))

    return refs


def _refs_from_task(task_id: str, task_entry: dict, task_def: dict, task_type: str) -> list[dict]:
    refs: list[dict] = []
    task_name = task_def.get("name", "")

    if task_type == "playbook":
        pb_id = task_def.get("playbookId", "")
        pb_name = task_def.get("playbookName", "")
        name = pb_id or pb_name
        field = "playbookId" if pb_id else ("playbookName" if pb_name else None)
        if name and field:
            refs.append(
                _raw_ref(
                    target_name=name,
                    target_type=ComponentType.PLAYBOOK,
                    yaml_path=f"tasks.{task_id}.task.{field}",
                    line=_key_line(task_def, field),
                    context=task_name,
                )
            )

    elif task_type == "regular":
        script = task_def.get("script") or task_def.get("scriptName", "")
        if script:
            field = "script" if "script" in task_def else "scriptName"
            is_cmd = bool(task_def.get("iscommand", False))
            refs.append(
                _raw_ref(
                    target_name=script,
                    target_type=ComponentType.INTEGRATION_COMMAND if is_cmd else ComponentType.AUTOMATION,
                    yaml_path=f"tasks.{task_id}.task.{field}",
                    line=_key_line(task_def, field),
                    context=task_name,
                )
            )

    refs.extend(_field_refs_from_scriptargs(task_id, task_entry, task_def, task_name))
    return refs


def _field_refs_from_scriptargs(
    task_id: str,
    task_entry: dict,
    task_def: dict,
    task_name: str,
) -> list[dict]:
    refs: list[dict] = []
    script_args = task_entry.get("scriptarguments", {})
    if not isinstance(script_args, dict):
        return refs

    script = task_def.get("script") or task_def.get("scriptName", "")
    is_setter = script in _FIELD_SETTERS or any(script.endswith(f"|||{s.split('|||')[-1]}") for s in _FIELD_SETTERS)

    # Write refs: argument keys on field-setter commands
    if is_setter:
        for arg_key in script_args:
            refs.append(
                _raw_ref(
                    target_name=arg_key,
                    target_type=ComponentType.FIELD,
                    yaml_path=f"tasks.{task_id}.scriptarguments.{arg_key}",
                    line=_key_line(script_args, arg_key),
                    context=task_name,
                )
            )

    # Read refs: ${incident.X} / ${CustomFields.X} expressions in argument values
    for arg_key, arg_val in script_args.items():
        text = _simple_value(arg_val)
        if not text:
            continue
        for m in _DQ_PATTERN.finditer(text):
            refs.append(
                _raw_ref(
                    target_name=m.group(1),
                    target_type=ComponentType.FIELD,
                    yaml_path=f"tasks.{task_id}.scriptarguments.{arg_key}",
                    line=_key_line(script_args, arg_key),
                    context=task_name,
                )
            )

    return refs


def _raw_ref(target_name: str, target_type: ComponentType, yaml_path: str, line: int, context: str) -> dict:
    return {
        "target_name": target_name,
        "target_type": target_type.value,
        "yaml_path": yaml_path,
        "line": line,
        "match_kind": MatchKind.YAML_STRUCTURED.value,
        "context": context,
    }


def _key_line(yaml_map: Any, key: str) -> int:
    lc = getattr(yaml_map, "lc", None)
    if lc is not None and hasattr(lc, "data") and lc.data and key in lc.data:
        return lc.data[key][0] + 1
    return 0


def _simple_value(val: Any) -> str | None:
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        s = val.get("simple")
        if isinstance(s, str):
            return s
    return None
