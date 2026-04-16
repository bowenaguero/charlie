import json
import sqlite3

import pytest

from charlie.core.models import ComponentType
from charlie.services.indexer import build_index

PLAYBOOK_YAML = """\
id: Index Test Playbook
name: Index Test Playbook
version: -1
tasks:
  '1':
    id: '1'
    taskid: a-111
    type: regular
    scriptarguments: {}
    task:
      id: a-111
      name: Run automation
      script: MyAutomation
      iscommand: false
      brand: ''
  '2':
    id: '2'
    taskid: b-222
    type: playbook
    task:
      id: b-222
      name: Call sub-playbook
      playbookId: SubPlaybook
      type: playbook
      iscommand: false
      brand: ''
  '3':
    id: '3'
    taskid: c-333
    type: regular
    scriptarguments:
      severity:
        simple: high
    task:
      id: c-333
      name: Set severity
      script: Builtin|||setIncident
      iscommand: true
      brand: Builtin
  '4':
    id: '4'
    taskid: d-444
    type: regular
    scriptarguments:
      message:
        simple: "Owner is ${incident.owner}"
    task:
      id: d-444
      name: Send alert
      script: SendEmail
      iscommand: false
      brand: ''
"""


@pytest.fixture()
def repo_dir(tmp_path):
    (tmp_path / "playbook-IndexTest.yml").write_text(PLAYBOOK_YAML)
    return tmp_path


@pytest.fixture()
def indexed_db(repo_dir, tmp_path):
    db = tmp_path / "index.db"
    build_index(repo_dir, db)
    return db


def test_stats(repo_dir, tmp_path):
    db = tmp_path / "index.db"
    stats = build_index(repo_dir, db)
    assert stats.files_indexed == 1
    assert stats.duration_s >= 0
    # task1: automation, task2: playbook, task3: integration-command + field(severity),
    # task4: automation(SendEmail) + field(owner DQ read ref)
    assert stats.refs_found == 6


def test_automation_ref_indexed(indexed_db):
    conn = sqlite3.connect(indexed_db)
    rows = conn.execute(
        "SELECT * FROM refs WHERE target_name=? AND target_type=?",
        ("MyAutomation", ComponentType.AUTOMATION.value),
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_playbook_ref_indexed(indexed_db):
    conn = sqlite3.connect(indexed_db)
    rows = conn.execute(
        "SELECT * FROM refs WHERE target_name=? AND target_type=?",
        ("SubPlaybook", ComponentType.PLAYBOOK.value),
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_integration_command_ref_indexed(indexed_db):
    conn = sqlite3.connect(indexed_db)
    rows = conn.execute(
        "SELECT * FROM refs WHERE target_name=? AND target_type=?",
        ("Builtin|||setIncident", ComponentType.INTEGRATION_COMMAND.value),
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_field_write_ref_indexed(indexed_db):
    conn = sqlite3.connect(indexed_db)
    rows = conn.execute(
        "SELECT * FROM refs WHERE target_name=? AND target_type=?",
        ("severity", ComponentType.FIELD.value),
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_field_dq_read_ref_indexed(indexed_db):
    conn = sqlite3.connect(indexed_db)
    rows = conn.execute(
        "SELECT * FROM refs WHERE target_name=? AND target_type=?",
        ("owner", ComponentType.FIELD.value),
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_source_component_recorded(indexed_db):
    conn = sqlite3.connect(indexed_db)
    row = conn.execute("SELECT name, type FROM components").fetchone()
    conn.close()
    assert row[0] == "Index Test Playbook"
    assert row[1] == ComponentType.PLAYBOOK.value


def test_build_index_is_idempotent(repo_dir, tmp_path):
    db = tmp_path / "index.db"
    build_index(repo_dir, db)
    build_index(repo_dir, db)
    conn = sqlite3.connect(db)
    ref_count = conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
    comp_count = conn.execute("SELECT COUNT(*) FROM components").fetchone()[0]
    conn.close()
    assert ref_count == 6
    assert comp_count == 1


def test_multiple_playbooks_indexed(tmp_path):
    second_yaml = """\
id: Second Playbook
name: Second Playbook
version: -1
tasks:
  '1':
    id: '1'
    taskid: e-111
    type: regular
    task:
      id: e-111
      name: Also run automation
      script: MyAutomation
      iscommand: false
      brand: ''
"""
    (tmp_path / "playbook-IndexTest.yml").write_text(PLAYBOOK_YAML)
    (tmp_path / "playbook-Second.yml").write_text(second_yaml)
    db = tmp_path / "index.db"
    stats = build_index(tmp_path, db)
    assert stats.files_indexed == 2

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT * FROM refs WHERE target_name=? AND target_type=?",
        ("MyAutomation", ComponentType.AUTOMATION.value),
    ).fetchall()
    conn.close()
    assert len(rows) == 2  # referenced by both playbooks


# ── INCIDENT_TYPE ────────────────────────────────────────────────────────────

INCIDENT_TYPE_JSON = json.dumps({
    "id": "Alert",
    "name": "Alert",
    "playbookId": "Alert Triage Playbook",
    "layout": "Alert Layout",
})


@pytest.fixture()
def repo_with_incident_type(tmp_path):
    d = tmp_path / "Packs" / "MyPack" / "IncidentTypes"
    d.mkdir(parents=True)
    (d / "incidenttype-Alert.json").write_text(INCIDENT_TYPE_JSON)
    return tmp_path


@pytest.fixture()
def indexed_incident_type_db(repo_with_incident_type, tmp_path):
    db = tmp_path / "index.db"
    build_index(repo_with_incident_type, db)
    return db


def test_incident_type_component_recorded(indexed_incident_type_db):
    conn = sqlite3.connect(indexed_incident_type_db)
    row = conn.execute(
        "SELECT name, type FROM components WHERE name=? AND type=?",
        ("Alert", ComponentType.INCIDENT_TYPE.value),
    ).fetchone()
    conn.close()
    assert row is not None


def test_incident_type_playbook_ref(indexed_incident_type_db):
    conn = sqlite3.connect(indexed_incident_type_db)
    rows = conn.execute(
        "SELECT * FROM refs WHERE target_name=? AND target_type=?",
        ("Alert Triage Playbook", ComponentType.PLAYBOOK.value),
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_incident_type_layout_ref(indexed_incident_type_db):
    conn = sqlite3.connect(indexed_incident_type_db)
    rows = conn.execute(
        "SELECT * FROM refs WHERE target_name=? AND target_type=?",
        ("Alert Layout", ComponentType.LAYOUT.value),
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_incident_type_prefers_playbookid_over_playbookname(tmp_path):
    d = tmp_path / "IncidentTypes"
    d.mkdir()
    (d / "incidenttype-X.json").write_text(
        json.dumps({
            "name": "X",
            "playbookId": "ByID",
            "playbookName": "ByName",
        })
    )
    db = tmp_path / "index.db"
    build_index(tmp_path, db)
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT target_name FROM refs WHERE target_type=?",
        (ComponentType.PLAYBOOK.value,),
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "ByID"


# ── INTEGRATION ──────────────────────────────────────────────────────────────

INTEGRATION_YAML = """\
name: Gmail
commonfields:
  id: Gmail
defaultclassifier: Gmail Classifier
"""


@pytest.fixture()
def repo_with_integration(tmp_path):
    d = tmp_path / "Packs" / "MyPack" / "Integrations" / "Gmail"
    d.mkdir(parents=True)
    (d / "Gmail.yml").write_text(INTEGRATION_YAML)
    return tmp_path


@pytest.fixture()
def indexed_integration_db(repo_with_integration, tmp_path):
    db = tmp_path / "index.db"
    build_index(repo_with_integration, db)
    return db


def test_integration_component_recorded(indexed_integration_db):
    conn = sqlite3.connect(indexed_integration_db)
    row = conn.execute(
        "SELECT name, type FROM components WHERE name=? AND type=?",
        ("Gmail", ComponentType.INTEGRATION.value),
    ).fetchone()
    conn.close()
    assert row is not None


def test_integration_classifier_ref(indexed_integration_db):
    conn = sqlite3.connect(indexed_integration_db)
    rows = conn.execute(
        "SELECT * FROM refs WHERE target_name=? AND target_type=?",
        ("Gmail Classifier", ComponentType.CLASSIFIER.value),
    ).fetchall()
    conn.close()
    assert len(rows) == 1


# ── CLASSIFIER ───────────────────────────────────────────────────────────────

CLASSIFIER_JSON = json.dumps({
    "id": "Gmail Classifier",
    "name": "Gmail Classifier",
    "defaultIncidentType": "Phishing",
    "keyTypeMap": {
        "alert": "Alert",
        "incident": "Generic Incident",
    },
})


@pytest.fixture()
def repo_with_classifier(tmp_path):
    d = tmp_path / "Packs" / "MyPack" / "Classifiers"
    d.mkdir(parents=True)
    (d / "classifier-Gmail.json").write_text(CLASSIFIER_JSON)
    return tmp_path


@pytest.fixture()
def indexed_classifier_db(repo_with_classifier, tmp_path):
    db = tmp_path / "index.db"
    build_index(repo_with_classifier, db)
    return db


def test_classifier_component_recorded(indexed_classifier_db):
    conn = sqlite3.connect(indexed_classifier_db)
    row = conn.execute(
        "SELECT name, type FROM components WHERE name=? AND type=?",
        ("Gmail Classifier", ComponentType.CLASSIFIER.value),
    ).fetchone()
    conn.close()
    assert row is not None


def test_classifier_default_incident_type_ref(indexed_classifier_db):
    conn = sqlite3.connect(indexed_classifier_db)
    rows = conn.execute(
        "SELECT * FROM refs WHERE target_name=? AND target_type=?",
        ("Phishing", ComponentType.INCIDENT_TYPE.value),
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_classifier_key_type_map_refs(indexed_classifier_db):
    conn = sqlite3.connect(indexed_classifier_db)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT target_name FROM refs WHERE target_type=?",
            (ComponentType.INCIDENT_TYPE.value,),
        ).fetchall()
    }
    conn.close()
    assert names == {"Phishing", "Alert", "Generic Incident"}


# ── LAYOUT ───────────────────────────────────────────────────────────────────

LAYOUT_JSON_FLAT = json.dumps({
    "id": "Alert Layout",
    "name": "Alert Layout",
    "layout": {"sections": [{"items": [{"fieldId": "severity"}, {"fieldId": "owner"}]}]},
})

LAYOUT_JSON_TABBED = json.dumps({
    "id": "Tabbed Layout",
    "name": "Tabbed Layout",
    "layout": {"tabs": [{"sections": [{"items": [{"fieldId": "status"}]}]}]},
})


@pytest.fixture()
def repo_with_layout(tmp_path):
    d = tmp_path / "Packs" / "MyPack" / "Layouts"
    d.mkdir(parents=True)
    (d / "layout-Alert.json").write_text(LAYOUT_JSON_FLAT)
    (d / "layout-Tabbed.json").write_text(LAYOUT_JSON_TABBED)
    return tmp_path


@pytest.fixture()
def indexed_layout_db(repo_with_layout, tmp_path):
    db = tmp_path / "index.db"
    build_index(repo_with_layout, db)
    return db


def test_layout_components_recorded(indexed_layout_db):
    conn = sqlite3.connect(indexed_layout_db)
    count = conn.execute(
        "SELECT COUNT(*) FROM components WHERE type=?",
        (ComponentType.LAYOUT.value,),
    ).fetchone()[0]
    conn.close()
    assert count == 2


def test_layout_flat_field_refs(indexed_layout_db):
    conn = sqlite3.connect(indexed_layout_db)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT target_name FROM refs WHERE target_type=? AND context LIKE 'layout:Alert Layout'",
            (ComponentType.FIELD.value,),
        ).fetchall()
    }
    conn.close()
    assert names == {"severity", "owner"}


def test_layout_tabbed_field_ref(indexed_layout_db):
    conn = sqlite3.connect(indexed_layout_db)
    rows = conn.execute(
        "SELECT * FROM refs WHERE target_name=? AND target_type=?",
        ("status", ComponentType.FIELD.value),
    ).fetchall()
    conn.close()
    assert len(rows) == 1


# ── FIELD ────────────────────────────────────────────────────────────────────

FIELD_JSON = json.dumps({
    "id": "severity",
    "name": "Severity",
    "cliName": "severity",
    "associatedTypes": ["Alert", "Phishing"],
})


@pytest.fixture()
def repo_with_field(tmp_path):
    d = tmp_path / "Packs" / "MyPack" / "IncidentFields"
    d.mkdir(parents=True)
    (d / "incidentfield-severity.json").write_text(FIELD_JSON)
    return tmp_path


@pytest.fixture()
def indexed_field_db(repo_with_field, tmp_path):
    db = tmp_path / "index.db"
    build_index(repo_with_field, db)
    return db


def test_field_component_recorded(indexed_field_db):
    conn = sqlite3.connect(indexed_field_db)
    row = conn.execute(
        "SELECT name, type FROM components WHERE type=?",
        (ComponentType.FIELD.value,),
    ).fetchone()
    conn.close()
    assert row is not None


def test_field_associated_type_refs(indexed_field_db):
    conn = sqlite3.connect(indexed_field_db)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT target_name FROM refs WHERE target_type=?",
            (ComponentType.INCIDENT_TYPE.value,),
        ).fetchall()
    }
    conn.close()
    assert names == {"Alert", "Phishing"}


# ── IDEMPOTENCY (multi-type) ─────────────────────────────────────────────────


def test_build_index_multi_type_is_idempotent(tmp_path):
    d = tmp_path / "Packs" / "P" / "IncidentTypes"
    d.mkdir(parents=True)
    (d / "incidenttype-X.json").write_text(
        json.dumps({
            "id": "X",
            "name": "X",
            "playbookId": "SomePlaybook",
        })
    )
    db = tmp_path / "index.db"
    build_index(tmp_path, db)
    build_index(tmp_path, db)
    conn = sqlite3.connect(db)
    ref_count = conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
    comp_count = conn.execute("SELECT COUNT(*) FROM components").fetchone()[0]
    conn.close()
    assert comp_count == 1
    assert ref_count == 1
