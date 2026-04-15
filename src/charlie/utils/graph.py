from __future__ import annotations

import networkx as nx

from ..core.models import ScanResult


def build_graph(result: ScanResult) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node(result.target, component_type=result.target_type.value, is_target=True)

    for ref in result.refs:
        if ref.source_name not in graph:
            graph.add_node(ref.source_name, component_type=ref.source_type.value, is_target=False)
        graph.add_edge(
            ref.source_name,
            result.target,
            file=str(ref.location.file),
            line=ref.location.line,
            match_kind=ref.match_kind.value,
            context=ref.context,
        )

    return graph
