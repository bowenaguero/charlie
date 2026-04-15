from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Iterator

from ruamel.yaml import YAML

from ..core.models import ComponentRef, ComponentType, MatchKind, MatchLocation, ScanResult

_yaml = YAML()
_yaml.preserve_quotes = True

# Directory-name → type (nested / Packs-style repos)
_DIR_TO_TYPE: dict[str, ComponentType] = {
    "Playbooks": ComponentType.PLAYBOOK,
    "Scripts": ComponentType.AUTOMATION,
    "Automations": ComponentType.AUTOMATION,
    "Integrations": ComponentType.INTEGRATION_COMMAND,
}

# Filename prefix → type (flat repos where everything lives at root)
_PREFIX_TO_TYPE: dict[str, ComponentType] = {
    "playbook": ComponentType.PLAYBOOK,
    "automation": ComponentType.AUTOMATION,
    "script": ComponentType.AUTOMATION,
    "integration": ComponentType.INTEGRATION_COMMAND,
}

_TYPE_DIR_NAMES = {"Playbooks", "Scripts", "Automations", "Integrations", "IncidentFields", "IndicatorFields"}

_STEM_PREFIXES = (
    "playbook-", "playbook_",
    "script-", "script_",
    "automation-", "automation_",
    "integration-", "integration_",
    "incidentfield-", "indicatorfield-",
)

# Commands that write incident/indicator fields; the argument keys are field cliNames.
_FIELD_SETTERS = frozenset({
    "setIncident", "Builtin|||setIncident",
    "setIndicator", "Builtin|||setIndicator",
})


def scan(repo: Path, target: str, target_type: ComponentType, db_path: Path | None = None) -> ScanResult:
    if db_path is not None and db_path.exists():
        from ..services.db import query_refs
        result = query_refs(db_path, target, target_type)
    else:
        result = ScanResult(target=target, target_type=target_type)
        for file_path, yaml_data in _iter_playbook_yamls(repo):
            source_name = _source_name(file_path, yaml_data)
            result.refs.extend(_scan_playbook_yaml(file_path, yaml_data, target, target_type, source_name))

    # Ripgrep sweep for unstructured refs not already captured by structured parsing
    structured = {(r.location.file, r.location.line) for r in result.refs}
    for ref in _scan_ripgrep(repo, target):
        if (ref.location.file, ref.location.line) not in structured:
            result.refs.append(ref)

    return result


def _iter_playbook_yamls(repo: Path) -> Iterator[tuple[Path, dict]]:
    for path in repo.rglob("*.yml"):
        if not _is_playbook_file(path):
            continue
        try:
            data = _yaml.load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and "tasks" in data:
            yield path, data


def _is_playbook_file(path: Path) -> bool:
    if "Playbooks" in path.parts:
        return True
    stem = path.stem.lower()
    return stem.startswith("playbook-") or stem.startswith("playbook_")


def _scan_playbook_yaml(
    file_path: Path,
    yaml_data: dict,
    target: str,
    target_type: ComponentType,
    source_name: str,
) -> list[ComponentRef]:
    refs: list[ComponentRef] = []
    tasks = yaml_data.get("tasks", {})
    if not isinstance(tasks, dict):
        return refs

    for task_id, task_entry in tasks.items():
        if not isinstance(task_entry, dict):
            continue
        task_def = task_entry.get("task", {})
        if not isinstance(task_def, dict):
            continue

        refs.extend(
            _match_task(
                file_path,
                str(task_id),
                task_entry,
                task_def,
                task_entry.get("type", ""),
                target,
                target_type,
                source_name,
            )
        )

    return refs


def _match_task(
    file_path: Path,
    task_id: str,
    task_entry: dict,
    task_def: dict,
    task_type: str,
    target: str,
    target_type: ComponentType,
    source_name: str,
) -> list[ComponentRef]:
    match target_type:
        case ComponentType.PLAYBOOK:
            if task_type != "playbook":
                return []
            pb_id = task_def.get("playbookId", "")
            pb_name = task_def.get("playbookName", "")
            if pb_id == target:
                field = "playbookId"
            elif pb_name == target:
                field = "playbookName"
            else:
                return []
            return [_make_ref(
                file_path, source_name, ComponentType.PLAYBOOK,
                f"tasks.{task_id}.task.{field}",
                _key_line(task_def, field),
                task_def.get("name", ""),
            )]

        case ComponentType.AUTOMATION:
            if task_type != "regular" or task_def.get("iscommand", False):
                return []
            script = task_def.get("script") or task_def.get("scriptName", "")
            if script != target:
                return []
            field = "script" if "script" in task_def else "scriptName"
            return [_make_ref(
                file_path, source_name, ComponentType.PLAYBOOK,
                f"tasks.{task_id}.task.{field}",
                _key_line(task_def, field),
                task_def.get("name", ""),
            )]

        case ComponentType.INTEGRATION_COMMAND:
            if task_type != "regular" or not task_def.get("iscommand", False):
                return []
            script = task_def.get("script") or task_def.get("scriptName", "")
            if script != target and not script.endswith(f"|||{target}"):
                return []
            field = "script" if "script" in task_def else "scriptName"
            return [_make_ref(
                file_path, source_name, ComponentType.PLAYBOOK,
                f"tasks.{task_id}.task.{field}",
                _key_line(task_def, field),
                task_def.get("name", ""),
            )]

        case ComponentType.FIELD:
            return _match_field_task(file_path, task_id, task_entry, task_def, target, source_name)

    return []


def _match_field_task(
    file_path: Path,
    task_id: str,
    task_entry: dict,
    task_def: dict,
    target: str,
    source_name: str,
) -> list[ComponentRef]:
    script_args = task_entry.get("scriptarguments", {})
    if not isinstance(script_args, dict):
        return []

    refs: list[ComponentRef] = []
    script = task_def.get("script") or task_def.get("scriptName", "")
    task_name = task_def.get("name", "")

    # Write ref: target cliName is an argument key on a setIncident/setIndicator call
    if script in _FIELD_SETTERS or any(script.endswith(f"|||{s.split('|||')[-1]}") for s in _FIELD_SETTERS):
        if target in script_args:
            refs.append(_make_ref(
                file_path, source_name, ComponentType.PLAYBOOK,
                f"tasks.{task_id}.scriptarguments.{target}",
                _key_line(script_args, target),
                task_name,
            ))

    # Read ref: DQ expression ${incident.TARGET} or ${CustomFields.TARGET} in any arg value
    dq_patterns = (f"${{incident.{target}}}", f"${{CustomFields.{target}}}")
    for arg_key, arg_val in script_args.items():
        text = _extract_simple_value(arg_val)
        if text and any(p in text for p in dq_patterns):
            refs.append(_make_ref(
                file_path, source_name, ComponentType.PLAYBOOK,
                f"tasks.{task_id}.scriptarguments.{arg_key}",
                _key_line(script_args, arg_key),
                task_name,
            ))

    return refs


def _extract_simple_value(val: Any) -> str | None:
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        simple = val.get("simple")
        if isinstance(simple, str):
            return simple
    return None


def _make_ref(
    file_path: Path,
    source_name: str,
    source_type: ComponentType,
    yaml_path: str,
    line: int,
    context: str,
) -> ComponentRef:
    return ComponentRef(
        source_name=source_name,
        source_type=source_type,
        location=MatchLocation(file=file_path, line=line, yaml_path=yaml_path),
        context=context,
        match_kind=MatchKind.YAML_STRUCTURED,
    )


def _scan_ripgrep(repo: Path, target: str) -> list[ComponentRef]:
    try:
        proc = subprocess.run(
            ["rg", "--json", "--", target, str(repo)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return []
    except subprocess.TimeoutExpired:
        return []

    refs: list[ComponentRef] = []
    for raw in proc.stdout.splitlines():
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "match":
            continue

        data = event["data"]
        path = Path(data["path"]["text"])
        line_num: int = data["line_number"]
        text: str = data["lines"]["text"].rstrip("\n")

        refs.append(ComponentRef(
            source_name=_source_name_from_path(path),
            source_type=_source_type_from_path(path),
            location=MatchLocation(file=path, line=line_num),
            context=text.strip(),
            match_kind=MatchKind.RIPGREP_TEXT,
        ))

    return refs


def _source_type_from_path(path: Path) -> ComponentType:
    for part in path.parts:
        if part in _DIR_TO_TYPE:
            return _DIR_TO_TYPE[part]
    stem = path.stem.lower()
    for prefix, ct in _PREFIX_TO_TYPE.items():
        if stem.startswith(prefix + "-") or stem.startswith(prefix + "_"):
            return ct
    return ComponentType.PLAYBOOK


def _source_name_from_path(path: Path, yaml_data: dict | None = None) -> str:
    if yaml_data is not None and isinstance(yaml_data.get("name"), str):
        return yaml_data["name"]

    stem = path.stem
    for prefix in _STEM_PREFIXES:
        if stem.lower().startswith(prefix):
            return stem[len(prefix):]

    parent = path.parent.name
    if parent not in _TYPE_DIR_NAMES:
        return parent

    return stem


def _source_name(file_path: Path, yaml_data: dict) -> str:
    return _source_name_from_path(file_path, yaml_data)


def _key_line(yaml_map: Any, key: str) -> int:
    lc = getattr(yaml_map, "lc", None)
    if lc is not None and hasattr(lc, "data") and lc.data and key in lc.data:
        return lc.data[key][0] + 1
    return 0
