from pathlib import Path

from charlie.utils.graph import build_graph
from charlie.core.models import ComponentRef, ComponentType, MatchKind, MatchLocation, ScanResult


def _ref(source: str, source_type: ComponentType = ComponentType.PLAYBOOK) -> ComponentRef:
    return ComponentRef(
        source_name=source,
        source_type=source_type,
        location=MatchLocation(file=Path("/test.yml"), line=10, yaml_path="tasks.1.task.scriptName"),
        context="Run script",
        match_kind=MatchKind.YAML_STRUCTURED,
    )


def test_target_node_present_with_no_refs():
    graph = build_graph(ScanResult(target="Orphan", target_type=ComponentType.FIELD))
    assert "Orphan" in graph.nodes
    assert graph.nodes["Orphan"]["is_target"] is True
    assert len(graph.edges) == 0


def test_single_ref_produces_edge_to_target():
    result = ScanResult(
        target="MyScript",
        target_type=ComponentType.AUTOMATION,
        refs=[_ref("PlaybookA")],
    )
    graph = build_graph(result)
    assert graph.has_edge("PlaybookA", "MyScript")


def test_multiple_sources():
    result = ScanResult(
        target="MyScript",
        target_type=ComponentType.AUTOMATION,
        refs=[_ref("PlaybookA"), _ref("PlaybookB")],
    )
    graph = build_graph(result)
    assert graph.has_edge("PlaybookA", "MyScript")
    assert graph.has_edge("PlaybookB", "MyScript")
    assert len(graph.nodes) == 3


def test_duplicate_source_produces_one_node():
    result = ScanResult(
        target="MyScript",
        target_type=ComponentType.AUTOMATION,
        refs=[_ref("PlaybookA"), _ref("PlaybookA")],
    )
    graph = build_graph(result)
    assert len(graph.nodes) == 2  # PlaybookA + MyScript


def test_edge_carries_metadata():
    ref = ComponentRef(
        source_name="PB",
        source_type=ComponentType.PLAYBOOK,
        location=MatchLocation(file=Path("/some/file.yml"), line=42, yaml_path="tasks.3.task.scriptName"),
        context="Call it",
        match_kind=MatchKind.YAML_STRUCTURED,
    )
    graph = build_graph(ScanResult(target="T", target_type=ComponentType.AUTOMATION, refs=[ref]))
    attrs = graph.edges["PB", "T"]
    assert attrs["line"] == 42
    assert attrs["match_kind"] == MatchKind.YAML_STRUCTURED.value
    assert attrs["context"] == "Call it"


def test_source_node_not_marked_as_target():
    result = ScanResult(
        target="T",
        target_type=ComponentType.AUTOMATION,
        refs=[_ref("Source")],
    )
    graph = build_graph(result)
    assert graph.nodes["Source"]["is_target"] is False
    assert graph.nodes["T"]["is_target"] is True
