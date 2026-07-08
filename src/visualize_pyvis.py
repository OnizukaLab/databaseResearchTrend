from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd
from pyvis.network import Network


CATEGORY_COLORS = {
    "AI for Data Systems": "#e76f51",
    "Applications": "#f4a261",
    "Data Models": "#2a9d8f",
    "Data Processing": "#457b9d",
    "Query Processing": "#264653",
    "Specialized Data": "#8ab17d",
    "Storage & Access": "#6d597a",
    "Systems": "#1d3557",
    "Trust": "#b56576",
}


def build_network(nodes_df: pd.DataFrame, edges_df: pd.DataFrame) -> Network:
    net = Network(height="1900px", width="100%", bgcolor="#ffffff", font_color="#222222")
    net.force_atlas_2based(
        gravity=-320,
        central_gravity=0.001,
        spring_length=520,
        spring_strength=0.004,
        damping=0.97,
        overlap=1.5,
    )

    max_count = float(nodes_df["Count"].max()) if not nodes_df.empty else 1.0

    for row in nodes_df.to_dict("records"):
        normalized = math.sqrt(float(row["Count"]) / max_count) if max_count > 0 else 0.0
        size = 12 + 24 * normalized
        net.add_node(
            row["Id"],
            label=row["Label"],
            title=f"{row['Label']}<br>{row['Category']}<br>count={row['Count']}",
            size=size,
            color=CATEGORY_COLORS.get(row["Category"], "#577590"),
        )

    for row in edges_df.to_dict("records"):
        net.add_edge(
            row["Source"],
            row["Target"],
            value=float(row["Weight"]),
            title=f"co-occurrence={row['Weight']}",
            width=1 + float(row["Weight"]),
        )

    options = {
        "interaction": {"hover": True, "navigationButtons": True},
        "physics": {
            "stabilization": {"iterations": 1000},
            "minVelocity": 0.25,
            "solver": "forceAtlas2Based",
        },
        "edges": {"smooth": {"type": "dynamic"}, "scaling": {"min": 1, "max": 5}},
    }
    net.set_options(json.dumps(options))
    return net


def render_period_html(nodes_path: Path, edges_path: Path, output_path: Path, min_edge_weight: int) -> None:
    nodes_df = pd.read_csv(nodes_path)
    edges_df = pd.read_csv(edges_path)
    if not edges_df.empty:
        edges_df = edges_df[edges_df["Weight"] >= min_edge_weight].copy()
    network = build_network(nodes_df, edges_df)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    network.write_html(str(output_path), notebook=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", required=True)
    parser.add_argument("--edges", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-edge-weight", type=int, default=1)
    args = parser.parse_args()
    render_period_html(Path(args.nodes), Path(args.edges), Path(args.output), args.min_edge_weight)


if __name__ == "__main__":
    main()
