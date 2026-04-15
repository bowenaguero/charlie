import sqlite3
from pathlib import Path

import pytest

from charlie.services.db import init_db, query_refs
from charlie.core.models import ComponentType, MatchKind


@pytest.fixture()
def db_path(tmp_path):
    p = tmp_path / "test.db"
    init_db(p)
    return p


def _seed(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO components (name, type, file_path) VALUES ('TestPlaybook', 'playbook', '/repo/playbook-Test.yml')"
    )
    conn.execute(
        "INSERT INTO refs (source_id, target_name, target_type, yaml_path, line, match_kind, context)"
        " VALUES (1, 'MyAutomation', 'automation', 'tasks.1.task.script', 10, 'yaml_structured', 'Run it')"
    )
    conn.execute(
        "INSERT INTO refs (source_id, target_name, target_type, yaml_path, line, match_kind, context)"
        " VALUES (1, 'Gmail|||send-mail', 'integration-command', 'tasks.2.task.script', 20, 'yaml_structured', 'Send')"
    )
    conn.execute(
        "INSERT INTO refs (source_id, target_name, target_type, yaml_path, line, match_kind, context)"
        " VALUES (1, 'severity', 'field', 'tasks.3.scriptarguments.severity', 30, 'yaml_structured', 'Set field')"
    )
    conn.commit()
    conn.close()


def test_init_db_creates_tables(db_path):
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert {"components", "refs"} <= tables


def test_query_automation(db_path):
    _seed(db_path)
    result = query_refs(db_path, "MyAutomation", ComponentType.AUTOMATION)
    assert len(result.refs) == 1
    ref = result.refs[0]
    assert ref.source_name == "TestPlaybook"
    assert ref.source_type == ComponentType.PLAYBOOK
    assert ref.match_kind == MatchKind.YAML_STRUCTURED
    assert ref.location.yaml_path == "tasks.1.task.script"
    assert ref.location.line == 10


def test_query_integration_command_exact(db_path):
    _seed(db_path)
    result = query_refs(db_path, "Gmail|||send-mail", ComponentType.INTEGRATION_COMMAND)
    assert len(result.refs) == 1


def test_query_integration_command_name_only(db_path):
    # "send-mail" should match "Gmail|||send-mail" via the LIKE '%|||send-mail' clause
    _seed(db_path)
    result = query_refs(db_path, "send-mail", ComponentType.INTEGRATION_COMMAND)
    assert len(result.refs) == 1


def test_query_field(db_path):
    _seed(db_path)
    result = query_refs(db_path, "severity", ComponentType.FIELD)
    assert len(result.refs) == 1
    assert result.refs[0].location.yaml_path == "tasks.3.scriptarguments.severity"


def test_query_no_match(db_path):
    _seed(db_path)
    result = query_refs(db_path, "NonExistent", ComponentType.AUTOMATION)
    assert result.refs == []


def test_query_wrong_type_no_match(db_path):
    _seed(db_path)
    # "MyAutomation" exists as automation, not playbook
    result = query_refs(db_path, "MyAutomation", ComponentType.PLAYBOOK)
    assert result.refs == []
