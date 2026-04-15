from pathlib import Path

import pytest

from charlie.core.models import ComponentRef, ComponentType, MatchKind, MatchLocation, ScanResult


def test_component_type_values():
    assert ComponentType.PLAYBOOK.value == "playbook"
    assert ComponentType.AUTOMATION.value == "automation"
    assert ComponentType.INTEGRATION_COMMAND.value == "integration-command"
    assert ComponentType.FIELD.value == "field"


def test_match_kind_values():
    assert MatchKind.YAML_STRUCTURED.value == "yaml_structured"
    assert MatchKind.RIPGREP_TEXT.value == "ripgrep_text"


def test_match_location_is_immutable():
    loc = MatchLocation(file=Path("/test.yml"), line=10)
    with pytest.raises((AttributeError, TypeError)):
        loc.line = 99  # type: ignore[misc]


def test_match_location_defaults():
    loc = MatchLocation(file=Path("/test.yml"), line=5)
    assert loc.yaml_path is None


def test_scan_result_defaults_to_empty_refs():
    result = ScanResult(target="MyScript", target_type=ComponentType.AUTOMATION)
    assert result.refs == []


def test_component_ref_fields():
    ref = ComponentRef(
        source_name="ParentPlaybook",
        source_type=ComponentType.PLAYBOOK,
        location=MatchLocation(file=Path("/pb.yml"), line=42, yaml_path="tasks.3.task.scriptName"),
        context="Run automation",
        match_kind=MatchKind.YAML_STRUCTURED,
    )
    assert ref.source_name == "ParentPlaybook"
    assert ref.location.line == 42
    assert ref.location.yaml_path == "tasks.3.task.scriptName"
