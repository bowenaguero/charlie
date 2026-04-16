from __future__ import annotations

import json
import re
import sqlite3
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from ..core.models import ComponentType, MatchKind
from .db import init_db
from .scanner import _is_playbook_file, _source_name_from_path, _source_type_from_path

_yaml = YAML()
_yaml.preserve_quotes = True

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

        # Pass 1: insert all recognized components as nodes
        component_rows: list[tuple[str, str, str]] = []
        for file_path, _ct, name, data in _iter_all_component_files(repo):
            component_rows.append((name, _ct.value, str(file_path)))
            files_indexed += 1
            if _ct == ComponentType.INTEGRATION:
                # Commands are sub-entities of the integration file, not standalone files
                component_rows.extend(_integration_command_rows(data, file_path))

        conn.executemany(
            "INSERT OR IGNORE INTO components (name, type, file_path) VALUES (?, ?, ?)",
            component_rows,
        )

        # Pass 2: extract and insert edges
        for _file_path, ct, name, data in _iter_all_component_files(repo):
            source_id_row = conn.execute(
                "SELECT id FROM components WHERE name = ? AND type = ?",
                (name, ct.value),
            ).fetchone()
            if source_id_row is None:
                continue
            source_id = source_id_row[0]

            raw_refs = _extract_refs_for_source(ct, data, name)
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


def _iter_all_component_files(repo: Path) -> Iterator[tuple[Path, ComponentType, str, dict]]:
    for path in (*repo.rglob("*.yml"), *repo.rglob("*.json")):
        ct = _source_type_from_path(path)

        # The fallback for unrecognized paths is PLAYBOOK. Only accept that if the
        # file is actually a playbook — otherwise random YAMLs pollute the index.
        if ct == ComponentType.PLAYBOOK and not _is_playbook_file(path):
            continue

        try:
            if path.suffix == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
            else:
                data = _yaml.load(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: S112
            continue

        if not isinstance(data, dict):
            continue

        name = _source_name_from_path(path, data)
        if not name:
            continue

        yield path, ct, name, data


def _extract_refs_for_source(source_type: ComponentType, data: dict, source_name: str) -> list[dict]:
    match source_type:
        case ComponentType.PLAYBOOK:
            return _extract_all_refs(data)
        case ComponentType.INCIDENT_TYPE:
            return _refs_from_incident_type(data, source_name)
        case ComponentType.INTEGRATION:
            return _refs_from_integration(data, source_name)
        case ComponentType.CLASSIFIER:
            return _refs_from_classifier(data, source_name)
        case ComponentType.LAYOUT:
            return _refs_from_layout(data, source_name)
        case ComponentType.FIELD:
            return _refs_from_field(data, source_name)
        case ComponentType.AUTOMATION | ComponentType.INTEGRATION_COMMAND | ComponentType.LIST:
            return []  # script code only; ripgrep handles these at scan time
    return []


def _refs_from_incident_type(data: dict, source_name: str) -> list[dict]:
    refs = []
    for field_name in ("playbookId", "playbookName"):
        val = data.get(field_name)
        if isinstance(val, str) and val.strip():
            refs.append(
                _raw_ref(
                    target_name=val.strip(),
                    target_type=ComponentType.PLAYBOOK,
                    yaml_path=field_name,
                    line=0,
                    context=f"incidenttype:{source_name}",
                )
            )
            break  # playbookId takes precedence; don't double-emit

    layout_val = data.get("layout")
    if isinstance(layout_val, str) and layout_val.strip():
        refs.append(
            _raw_ref(
                target_name=layout_val.strip(),
                target_type=ComponentType.LAYOUT,
                yaml_path="layout",
                line=0,
                context=f"incidenttype:{source_name}",
            )
        )

    return refs


def _refs_from_integration(data: dict, source_name: str) -> list[dict]:
    val = data.get("defaultclassifier") or data.get("defaultClassifier")
    if not isinstance(val, str) or not val.strip():
        return []
    return [
        _raw_ref(
            target_name=val.strip(),
            target_type=ComponentType.CLASSIFIER,
            yaml_path="defaultclassifier",
            line=_key_line(data, "defaultclassifier") or _key_line(data, "defaultClassifier"),
            context=f"integration:{source_name}",
        )
    ]


def _integration_command_rows(data: dict, file_path: Path) -> list[tuple[str, str, str]]:
    script = data.get("script")
    if not isinstance(script, dict):
        return []
    commands = script.get("commands")
    if not isinstance(commands, list):
        return []
    return [
        (cmd["name"].strip(), ComponentType.INTEGRATION_COMMAND.value, str(file_path))
        for cmd in commands
        if isinstance(cmd, dict) and isinstance(cmd.get("name"), str) and cmd["name"].strip()
    ]


def _refs_from_classifier(data: dict, source_name: str) -> list[dict]:
    refs = []
    default = data.get("defaultIncidentType")
    if isinstance(default, str) and default.strip():
        refs.append(
            _raw_ref(
                target_name=default.strip(),
                target_type=ComponentType.INCIDENT_TYPE,
                yaml_path="defaultIncidentType",
                line=0,
                context=f"classifier:{source_name}",
            )
        )

    key_type_map = data.get("keyTypeMap")
    if isinstance(key_type_map, dict):
        for incident_type_name in key_type_map.values():
            if isinstance(incident_type_name, str) and incident_type_name.strip():
                refs.append(
                    _raw_ref(
                        target_name=incident_type_name.strip(),
                        target_type=ComponentType.INCIDENT_TYPE,
                        yaml_path="keyTypeMap",
                        line=0,
                        context=f"classifier:{source_name}",
                    )
                )

    return refs


def _field_ids_from_sections(sections: Any) -> list[str]:
    if not isinstance(sections, list):
        return []
    field_ids = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        items = section.get("items") or section.get("fields") or []
        for item in items:
            if isinstance(item, dict):
                field_id = item.get("fieldId")
                if isinstance(field_id, str) and field_id.strip():
                    field_ids.append(field_id.strip())
    return field_ids


def _refs_from_layout(data: dict, source_name: str) -> list[dict]:
    layout_obj = data.get("layout")
    if not isinstance(layout_obj, dict):
        return []

    field_ids: list[str] = []
    field_ids.extend(_field_ids_from_sections(layout_obj.get("sections", [])))
    tabs = layout_obj.get("tabs")
    if isinstance(tabs, list):
        for tab in tabs:
            if isinstance(tab, dict):
                field_ids.extend(_field_ids_from_sections(tab.get("sections", [])))

    return [
        _raw_ref(
            target_name=fid,
            target_type=ComponentType.FIELD,
            yaml_path="layout.sections.items.fieldId",
            line=0,
            context=f"layout:{source_name}",
        )
        for fid in field_ids
    ]


def _refs_from_field(data: dict, source_name: str) -> list[dict]:
    associated = data.get("associatedTypes")
    if not isinstance(associated, list):
        return []
    return [
        _raw_ref(
            target_name=type_name.strip(),
            target_type=ComponentType.INCIDENT_TYPE,
            yaml_path="associatedTypes",
            line=0,
            context=f"field:{source_name}",
        )
        for type_name in associated
        if isinstance(type_name, str) and type_name.strip()
    ]


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
