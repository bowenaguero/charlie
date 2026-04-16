from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from ..core.models import ComponentRef, ComponentType, MatchKind, MatchLocation, ScanResult

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS components (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL,
    type      TEXT    NOT NULL,
    file_path TEXT    NOT NULL,
    UNIQUE(name, type)
);

CREATE TABLE IF NOT EXISTS refs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    target_name TEXT    NOT NULL,
    target_type TEXT    NOT NULL,
    yaml_path   TEXT,
    line        INTEGER NOT NULL DEFAULT 0,
    match_kind  TEXT    NOT NULL,
    context     TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_refs_target ON refs(target_name, target_type);
CREATE INDEX IF NOT EXISTS idx_refs_source ON refs(source_id);
"""


@contextmanager
def _connect(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)


def query_refs(db_path: Path, target_name: str, target_type: ComponentType) -> ScanResult:
    result = ScanResult(target=target_name, target_type=target_type)

    with _connect(db_path) as conn:
        if target_type == ComponentType.INTEGRATION_COMMAND:
            # Match exact script value ("send-mail") or brand-prefixed form ("Gmail|||send-mail")
            rows = conn.execute(
                """SELECT c.name, c.type, c.file_path, r.yaml_path, r.line, r.match_kind, r.context
                   FROM refs r JOIN components c ON r.source_id = c.id
                   WHERE r.target_type = ?
                     AND (r.target_name = ? OR r.target_name LIKE '%|||' || ?)""",
                (target_type.value, target_name, target_name),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT c.name, c.type, c.file_path, r.yaml_path, r.line, r.match_kind, r.context
                   FROM refs r JOIN components c ON r.source_id = c.id
                   WHERE r.target_name = ? AND r.target_type = ?""",
                (target_name, target_type.value),
            ).fetchall()

        for row in rows:
            result.refs.append(
                ComponentRef(
                    source_name=row["name"],
                    source_type=ComponentType(row["type"]),
                    location=MatchLocation(
                        file=Path(row["file_path"]),
                        line=row["line"],
                        yaml_path=row["yaml_path"],
                    ),
                    context=row["context"],
                    match_kind=MatchKind(row["match_kind"]),
                )
            )

    return result


def list_components(
    db_path: Path,
    component_type: ComponentType | None = None,
) -> list[tuple[str, ComponentType]]:
    # components table holds sources (playbooks only); refs table holds all targets.
    # UNION gives the full set of known component names across both roles.
    with _connect(db_path) as conn:
        if component_type is not None:
            rows = conn.execute(
                """SELECT name, type FROM components WHERE type = ?
                   UNION
                   SELECT DISTINCT target_name AS name, target_type AS type FROM refs WHERE target_type = ?
                   ORDER BY name""",
                (component_type.value, component_type.value),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT name, type FROM components
                   UNION
                   SELECT DISTINCT target_name AS name, target_type AS type FROM refs
                   ORDER BY type, name"""
            ).fetchall()
    return [(row["name"], ComponentType(row["type"])) for row in rows]
