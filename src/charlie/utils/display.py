from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import networkx as nx
from rich.console import Console
from rich.tree import Tree

from ..core.models import ComponentRef, ComponentType, MatchKind, ScanResult

_TYPE_COLORS: dict[ComponentType, str] = {
    ComponentType.PLAYBOOK: "cyan",
    ComponentType.AUTOMATION: "green",
    ComponentType.INTEGRATION_COMMAND: "yellow",
    ComponentType.FIELD: "magenta",
}

# pyvis/DOT node fill colors keyed by component type value
_NODE_FILL: dict[str, str] = {
    ComponentType.PLAYBOOK.value: "#97C2FC",
    ComponentType.AUTOMATION.value: "#90EE90",
    ComponentType.INTEGRATION_COMMAND.value: "#FFFF99",
    ComponentType.FIELD.value: "#FFB6C1",
}


def render_tree(result: ScanResult, console: Console | None = None) -> None:
    if console is None:
        console = Console()

    target_color = _TYPE_COLORS.get(result.target_type, "white")
    root_label = f"[bold {target_color}]{result.target}[/bold {target_color}] [dim]({result.target_type.value})[/dim]"
    tree = Tree(root_label)

    grouped: dict[str, list[ComponentRef]] = defaultdict(list)
    for ref in result.refs:
        grouped[ref.source_name].append(ref)

    for source_name, refs in grouped.items():
        source_type = refs[0].source_type
        color = _TYPE_COLORS.get(source_type, "white")
        source_label = f"[{color}]{source_name}[/{color}] [dim]({source_type.value})[/dim]"
        source_branch = tree.add(source_label)

        for ref in refs:
            loc = ref.location
            yaml_part = f"[green]{loc.yaml_path}[/green] " if loc.yaml_path else ""
            line_part = f"[dim]: line {loc.line}[/dim]" if loc.line else ""
            kind_part = f" [dim italic][{ref.match_kind.value}][/dim italic]"
            ref_node = source_branch.add(f"{yaml_part}{line_part}{kind_part}")
            if ref.context:
                ref_node.add(f"[dim]{ref.context[:120]}[/dim]")

    console.print(tree)
    total = len(result.refs)
    sources = len(grouped)
    console.print(f"\n[bold]{total}[/bold] reference(s) across [bold]{sources}[/bold] component(s)")


def render_html(graph: nx.DiGraph, output_path: Path) -> None:
    try:
        from pyvis.network import Network
    except ImportError as exc:
        raise ImportError("pyvis is required for HTML output: pip install pyvis") from exc  # noqa: TRY003

    net = Network(
        height="750px",
        width="100%",
        directed=True,
        bgcolor="#1a1a2e",
        font_color="#eeeeee",
    )
    net.set_options(
        """{
          "physics": {
            "barnesHut": {"gravitationalConstant": -8000, "springLength": 160},
            "stabilization": {"iterations": 200}
          }
        }"""
    )

    for node, attrs in graph.nodes(data=True):
        ct_value: str = attrs.get("component_type", ComponentType.PLAYBOOK.value)
        is_target: bool = attrs.get("is_target", False)
        fill = _NODE_FILL.get(ct_value, "#dddddd")
        net.add_node(
            node,
            label=node,
            color=fill,
            title=f"{node} ({ct_value})",
            shape="star" if is_target else "dot",
            size=30 if is_target else 15,
            borderWidth=3 if is_target else 1,
        )

    for src, dst, edge_attrs in graph.edges(data=True):
        is_structured = edge_attrs.get("match_kind") == MatchKind.YAML_STRUCTURED.value
        edge_color = "#ff6b6b" if is_structured else "#888888"
        title = f"{edge_attrs.get('file', '')}:{edge_attrs.get('line', '')}"
        net.add_edge(src, dst, color=edge_color, title=title)

    net.write_html(str(output_path))


def export_dot(graph: nx.DiGraph, output_path: Path) -> None:
    lines = ["digraph charlie {", '  rankdir="LR";', '  node [fontname="Arial"];']

    for node, attrs in graph.nodes(data=True):
        ct_value = attrs.get("component_type", "")
        is_target = attrs.get("is_target", False)
        label = node.replace('"', '\\"')
        fill = "red" if is_target else "lightblue"
        shape = "doublecircle" if is_target else "box"
        lines.append(f'  "{label}" [label="{label}\\n({ct_value})" style=filled fillcolor="{fill}" shape="{shape}"];')

    for src, dst, attrs in graph.edges(data=True):
        s = src.replace('"', '\\"')
        d = dst.replace('"', '\\"')
        is_structured = attrs.get("match_kind") == MatchKind.YAML_STRUCTURED.value
        style = "solid" if is_structured else "dashed"
        lines.append(f'  "{s}" -> "{d}" [style="{style}"];')

    lines.append("}")
    output_path.write_text("\n".join(lines), encoding="utf-8")
