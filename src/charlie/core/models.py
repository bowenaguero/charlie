from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ComponentType(str, Enum):
    PLAYBOOK = "playbook"
    AUTOMATION = "automation"
    INTEGRATION_COMMAND = "integration-command"
    FIELD = "field"
    LAYOUT = "layout"
    LIST = "list"
    CLASSIFIER = "classifier"
    INCIDENT_TYPE = "incidenttype"
    INTEGRATION = "integration"


class MatchKind(str, Enum):
    YAML_STRUCTURED = "yaml_structured"
    RIPGREP_TEXT = "ripgrep_text"


@dataclass(frozen=True)
class MatchLocation:
    file: Path
    line: int
    yaml_path: str | None = None


@dataclass
class ComponentRef:
    source_name: str
    source_type: ComponentType
    location: MatchLocation
    context: str
    match_kind: MatchKind


@dataclass
class ScanResult:
    target: str
    target_type: ComponentType
    refs: list[ComponentRef] = field(default_factory=list)
