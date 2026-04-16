import io
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from charlie.core.models import ComponentType, MatchKind
from charlie.services.scanner import (
    _scan_playbook_yaml,
    _source_name_from_path,
    _source_type_from_path,
    scan,
)

_yaml = YAML()


def _load(text: str) -> dict:
    return _yaml.load(io.StringIO(text))


# Mirrors the schema seen in cfacorp/demisto:
#   - sub-playbooks: task.playbookId or task.playbookName (both used in the wild)
#   - automations:   task.script + iscommand: false
#   - commands:      task.script ("Brand|||cmd") + iscommand: true
PLAYBOOK_YAML = """\
id: Test Playbook
name: Test Playbook
version: -1
tasks:
  '1':
    id: '1'
    taskid: abc-111
    type: regular
    task:
      id: abc-111
      name: Run automation
      script: TargetAutomation
      iscommand: false
      brand: ''
  '2':
    id: '2'
    taskid: def-222
    type: playbook
    task:
      id: def-222
      name: Sub playbook via playbookId
      playbookId: TargetPlaybook
      type: playbook
      iscommand: false
      brand: ''
  '3':
    id: '3'
    taskid: ghi-333
    type: playbook
    task:
      id: ghi-333
      name: Sub playbook via playbookName
      playbookName: TargetPlaybookByName
      type: playbook
      iscommand: false
      brand: ''
  '4':
    id: '4'
    taskid: jkl-444
    type: regular
    task:
      id: jkl-444
      name: Send mail
      script: Gmail|||send-mail
      iscommand: true
      brand: Gmail
  '5':
    id: '5'
    taskid: mno-555
    type: regular
    task:
      id: mno-555
      name: Direct command name
      script: send-mail
      iscommand: true
      brand: Gmail
  '6':
    id: '6'
    taskid: pqr-666
    type: title
    task:
      id: pqr-666
      name: Section header
      iscommand: false
      brand: ''
"""

# Older schema that uses scriptName instead of script
LEGACY_PLAYBOOK_YAML = """\
id: Legacy Playbook
name: Legacy Playbook
version: -1
tasks:
  '1':
    id: '1'
    taskid: legacy-111
    type: regular
    task:
      id: legacy-111
      name: Run legacy automation
      scriptName: LegacyAutomation
      iscommand: false
      brand: ''
"""

_FILE = Path("/repo/playbook-Test.yml")
_LEGACY_FILE = Path("/repo/playbook-Legacy.yml")


# --- automation matching ---


def test_automation_ref_found():
    refs = _scan_playbook_yaml(
        _FILE, _load(PLAYBOOK_YAML), "TargetAutomation", ComponentType.AUTOMATION, "Test Playbook"
    )
    assert len(refs) == 1
    ref = refs[0]
    assert ref.source_name == "Test Playbook"
    assert ref.source_type == ComponentType.PLAYBOOK
    assert ref.match_kind == MatchKind.YAML_STRUCTURED
    assert ref.location.yaml_path == "tasks.1.task.script"
    assert ref.context == "Run automation"


def test_automation_falls_back_to_scriptname_field():
    refs = _scan_playbook_yaml(
        _LEGACY_FILE, _load(LEGACY_PLAYBOOK_YAML), "LegacyAutomation", ComponentType.AUTOMATION, "Legacy Playbook"
    )
    assert len(refs) == 1
    assert refs[0].location.yaml_path == "tasks.1.task.scriptName"


def test_automation_not_matched_when_iscommand_true():
    refs = _scan_playbook_yaml(_FILE, _load(PLAYBOOK_YAML), "send-mail", ComponentType.AUTOMATION, "Test Playbook")
    assert refs == []


# --- playbook matching ---


def test_playbook_ref_found_via_playbookId():
    refs = _scan_playbook_yaml(_FILE, _load(PLAYBOOK_YAML), "TargetPlaybook", ComponentType.PLAYBOOK, "Test Playbook")
    assert len(refs) == 1
    assert refs[0].location.yaml_path == "tasks.2.task.playbookId"
    assert refs[0].context == "Sub playbook via playbookId"


def test_playbook_ref_found_via_playbookName():
    refs = _scan_playbook_yaml(
        _FILE, _load(PLAYBOOK_YAML), "TargetPlaybookByName", ComponentType.PLAYBOOK, "Test Playbook"
    )
    assert len(refs) == 1
    assert refs[0].location.yaml_path == "tasks.3.task.playbookName"


def test_playbook_not_matched_for_automation_task():
    refs = _scan_playbook_yaml(_FILE, _load(PLAYBOOK_YAML), "TargetAutomation", ComponentType.PLAYBOOK, "Test Playbook")
    assert refs == []


# --- integration-command matching ---


def test_integration_command_brand_prefix():
    refs = _scan_playbook_yaml(
        _FILE, _load(PLAYBOOK_YAML), "send-mail", ComponentType.INTEGRATION_COMMAND, "Test Playbook"
    )
    # matches both "Gmail|||send-mail" (task 4) and direct "send-mail" (task 5)
    assert len(refs) == 2
    yaml_paths = {r.location.yaml_path for r in refs}
    assert "tasks.4.task.script" in yaml_paths
    assert "tasks.5.task.script" in yaml_paths


def test_integration_command_not_matched_for_automation_task():
    refs = _scan_playbook_yaml(
        _FILE, _load(PLAYBOOK_YAML), "TargetAutomation", ComponentType.INTEGRATION_COMMAND, "Test Playbook"
    )
    assert refs == []


# --- field scanning ---

FIELD_PLAYBOOK_YAML = """\
id: Field Test Playbook
name: Field Test Playbook
version: -1
tasks:
  '1':
    id: '1'
    taskid: set-111
    type: regular
    scriptarguments:
      severity:
        simple: low
      owner:
        simple: admin
    task:
      id: set-111
      name: Set severity low
      script: Builtin|||setIncident
      iscommand: true
      brand: Builtin
  '2':
    id: '2'
    taskid: set-222
    type: regular
    scriptarguments:
      status:
        simple: closed
    task:
      id: set-222
      name: Close incident
      script: Builtin|||setIncident
      iscommand: true
      brand: Builtin
  '3':
    id: '3'
    taskid: read-333
    type: regular
    scriptarguments:
      message:
        simple: "Incident owned by ${incident.severity} user"
      subject:
        simple: "Alert for ${CustomFields.severity}"
    task:
      id: read-333
      name: Send notification
      script: SendEmail
      iscommand: false
      brand: ''
  '4':
    id: '4'
    taskid: non-setter-444
    type: regular
    scriptarguments:
      severity:
        simple: high
    task:
      id: non-setter-444
      name: Non-setter with field key
      script: SomeOtherScript
      iscommand: false
      brand: ''
  '5':
    id: '5'
    taskid: ind-555
    type: regular
    scriptarguments:
      severity:
        simple: high
    task:
      id: ind-555
      name: Set indicator severity
      script: Builtin|||setIndicator
      iscommand: true
      brand: Builtin
"""

_FIELD_FILE = Path("/repo/playbook-FieldTest.yml")


def test_field_write_ref_setincident():
    refs = _scan_playbook_yaml(
        _FIELD_FILE, _load(FIELD_PLAYBOOK_YAML), "severity", ComponentType.FIELD, "Field Test Playbook"
    )
    write_refs = [r for r in refs if r.location.yaml_path == "tasks.1.scriptarguments.severity"]
    assert len(write_refs) == 1
    assert write_refs[0].match_kind == MatchKind.YAML_STRUCTURED
    assert write_refs[0].context == "Set severity low"


def test_field_write_ref_setindicator():
    refs = _scan_playbook_yaml(
        _FIELD_FILE, _load(FIELD_PLAYBOOK_YAML), "severity", ComponentType.FIELD, "Field Test Playbook"
    )
    indicator_refs = [r for r in refs if r.location.yaml_path == "tasks.5.scriptarguments.severity"]
    assert len(indicator_refs) == 1


def test_field_no_match_wrong_key_in_setter():
    refs = _scan_playbook_yaml(
        _FIELD_FILE, _load(FIELD_PLAYBOOK_YAML), "nonexistent", ComponentType.FIELD, "Field Test Playbook"
    )
    structured = [r for r in refs if r.match_kind == MatchKind.YAML_STRUCTURED]
    assert structured == []


def test_field_no_write_match_in_non_setter():
    # task 4 has 'severity' as a scriptarguments key but calls a non-setter script
    refs = _scan_playbook_yaml(
        _FIELD_FILE, _load(FIELD_PLAYBOOK_YAML), "severity", ComponentType.FIELD, "Field Test Playbook"
    )
    non_setter_refs = [r for r in refs if "tasks.4" in (r.location.yaml_path or "")]
    assert non_setter_refs == []


def test_field_read_ref_incident_dq():
    refs = _scan_playbook_yaml(
        _FIELD_FILE, _load(FIELD_PLAYBOOK_YAML), "severity", ComponentType.FIELD, "Field Test Playbook"
    )
    dq_refs = [r for r in refs if r.location.yaml_path == "tasks.3.scriptarguments.message"]
    assert len(dq_refs) == 1
    assert dq_refs[0].context == "Send notification"


def test_field_read_ref_customfields_dq():
    refs = _scan_playbook_yaml(
        _FIELD_FILE, _load(FIELD_PLAYBOOK_YAML), "severity", ComponentType.FIELD, "Field Test Playbook"
    )
    dq_refs = [r for r in refs if r.location.yaml_path == "tasks.3.scriptarguments.subject"]
    assert len(dq_refs) == 1


def test_field_total_refs_for_severity():
    # task1 (setter key) + task5 (indicator setter key) + task3 message (incident DQ) + task3 subject (CustomFields DQ)
    refs = _scan_playbook_yaml(
        _FIELD_FILE, _load(FIELD_PLAYBOOK_YAML), "severity", ComponentType.FIELD, "Field Test Playbook"
    )
    structured = [r for r in refs if r.match_kind == MatchKind.YAML_STRUCTURED]
    assert len(structured) == 4


def test_title_task_is_ignored():
    for ct in [ComponentType.PLAYBOOK, ComponentType.AUTOMATION, ComponentType.INTEGRATION_COMMAND]:
        refs = _scan_playbook_yaml(_FILE, _load(PLAYBOOK_YAML), "Section header", ct, "Test Playbook")
        assert refs == [], f"Unexpected match for type {ct}"


def test_no_tasks_returns_empty():
    data = _load("id: X\nname: X\nversion: -1\n")
    assert _scan_playbook_yaml(_FILE, data, "anything", ComponentType.AUTOMATION, "X") == []


# --- source type detection ---


@pytest.mark.parametrize(
    "path,expected",
    [
        # nested / Packs-style (directory-based)
        (Path("/repo/Pack/Playbooks/playbook-Test.yml"), ComponentType.PLAYBOOK),
        (Path("/repo/Pack/Scripts/MyScript/MyScript.py"), ComponentType.AUTOMATION),
        (Path("/repo/Pack/Automations/MyAuto/MyAuto.yml"), ComponentType.AUTOMATION),
        (Path("/repo/Pack/Integrations/MyInt/MyInt.yml"), ComponentType.INTEGRATION),
        (Path("/repo/Pack/Layouts/layout-MyLayout.json"), ComponentType.LAYOUT),
        (Path("/repo/Pack/Lists/list-MyList.json"), ComponentType.LIST),
        (Path("/repo/Pack/Classifiers/classifier-Triage.json"), ComponentType.CLASSIFIER),
        (Path("/repo/Pack/IncidentTypes/incidenttype-Alert.json"), ComponentType.INCIDENT_TYPE),
        # flat repo (prefix-based)
        (Path("/repo/playbook-Something.yml"), ComponentType.PLAYBOOK),
        (Path("/repo/automation-Something.yml"), ComponentType.AUTOMATION),
        (Path("/repo/integration-Something.yml"), ComponentType.INTEGRATION),
        (Path("/repo/layout-MyLayout.json"), ComponentType.LAYOUT),
        (Path("/repo/list-MyList.json"), ComponentType.LIST),
        (Path("/repo/classifier-Triage.json"), ComponentType.CLASSIFIER),
        (Path("/repo/incidenttype-Alert.json"), ComponentType.INCIDENT_TYPE),
        # fallback
        (Path("/repo/README.md"), ComponentType.PLAYBOOK),
    ],
)
def test_source_type_from_path(path, expected):
    assert _source_type_from_path(path) == expected


# --- source name extraction ---


@pytest.mark.parametrize(
    "path,expected",
    [
        # flat repo
        (Path("/repo/playbook-SomeName.yml"), "SomeName"),
        (Path("/repo/playbook_OtherName.yml"), "OtherName"),
        (Path("/repo/automation-MyScript.yml"), "MyScript"),
        (Path("/repo/integration-MyInteg.yml"), "MyInteg"),
        (Path("/repo/incidentfield-MyField.json"), "MyField"),
        (Path("/repo/layout-MyLayout.json"), "MyLayout"),
        (Path("/repo/list-MyList.json"), "MyList"),
        (Path("/repo/classifier-Triage.json"), "Triage"),
        (Path("/repo/incidenttype-Alert.json"), "Alert"),
        # nested / Packs-style
        (Path("/repo/Pack/Playbooks/playbook-SomeName.yml"), "SomeName"),
        (Path("/repo/Pack/Scripts/MyScript/MyScript.py"), "MyScript"),
    ],
)
def test_source_name_from_path(path, expected):
    assert _source_name_from_path(path) == expected


def test_source_name_prefers_yaml_name_field():
    path = Path("/repo/playbook-Irrelevant.yml")
    assert _source_name_from_path(path, {"name": "The Real Name"}) == "The Real Name"


# --- ripgrep source filtering ---


def test_ripgrep_hit_from_invalid_source_is_excluded(tmp_path):
    # A list file contains the target name in its own id/name fields — should be noise.
    (tmp_path / "list-agent-mail-rule-analyst.json").write_text(
        '{"id": "agent-mail-rule-analyst", "name": "agent-mail-rule-analyst"}'
    )
    result = scan(tmp_path, "agent-mail-rule-analyst", ComponentType.LIST)
    # Only valid source for LIST is PLAYBOOK/AUTOMATION; hits from list files must be dropped.
    assert all(r.source_type != ComponentType.LIST for r in result.refs)


def test_ripgrep_hit_from_valid_source_is_included(tmp_path):
    # An incidenttype file references a layout by name — a valid relationship.
    (tmp_path / "incidenttype-Alert.json").write_text('{"layout": "My Layout", "name": "Alert"}')
    result = scan(tmp_path, "My Layout", ComponentType.LAYOUT)
    assert any(r.source_type == ComponentType.INCIDENT_TYPE for r in result.refs)
