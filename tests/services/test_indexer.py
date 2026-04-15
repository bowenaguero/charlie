import sqlite3
from pathlib import Path

import pytest

from charlie.services.indexer import build_index
from charlie.core.models import ComponentType


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
