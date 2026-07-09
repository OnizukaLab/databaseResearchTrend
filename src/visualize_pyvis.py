from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import pandas as pd
from pyvis.network import Network


CATEGORY_COLORS = {
    "AI for Data Systems": "#e76f51",
    "Applications": "#f4a261",
    "AI for Science": "#90be6d",
    "Core ML": "#277da1",
    "Data Models": "#2a9d8f",
    "Data Processing": "#457b9d",
    "Decision Making": "#f94144",
    "Foundation Learning": "#43aa8b",
    "Generative AI": "#f3722c",
    "Perception": "#577590",
    "Query Processing": "#264653",
    "Scientific ML": "#4d908e",
    "Specialized Data": "#8ab17d",
    "Storage & Access": "#6d597a",
    "Structured Learning": "#7b2cbf",
    "Systems": "#1d3557",
    "Systems for ML": "#577590",
    "Trust": "#b56576",
    "Trustworthy AI": "#bc4749",
}


def build_network(nodes_df: pd.DataFrame, edges_df: pd.DataFrame) -> Network:
    net = Network(height="720px", width="100%", bgcolor="#ffffff", font_color="#222222")
    net.force_atlas_2based(
        gravity=-320,
        central_gravity=0.006,
        spring_length=280,
        spring_strength=0.006,
        damping=0.92,
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
            "stabilization": {"iterations": 1200},
            "minVelocity": 0.15,
            "solver": "forceAtlas2Based",
        },
        "edges": {"smooth": {"type": "dynamic"}, "scaling": {"min": 1, "max": 5}},
    }
    net.set_options(json.dumps(options))
    return net


def expand_network_view(output_path: Path) -> None:
    html = output_path.read_text(encoding="utf-8")
    html = re.sub(
        r"<link\s+href=\"https://cdn\.jsdelivr\.net/npm/bootstrap@5\.0\.0-beta3/dist/css/bootstrap\.min\.css\"[\s\S]*?crossorigin=\"anonymous\"\s*/>\s*"
        r"<script\s+src=\"https://cdn\.jsdelivr\.net/npm/bootstrap@5\.0\.0-beta3/dist/js/bootstrap\.bundle\.min\.js\"[\s\S]*?</script>",
        "",
        html,
        count=1,
    )
    html = re.sub(
        r"<center>\s*<h1></h1>\s*</center>",
        "",
        html,
    )
    html = re.sub(
        r"<style type=\"text/css\">[\s\S]*?</style>",
        """<style type="text/css">
             html, body {
                 width: 100%;
                 height: 100%;
                 margin: 0;
                 padding: 0;
                 overflow: hidden;
                 background-color: #ffffff;
             }

             #mynetwork {
                 width: 100vw;
                 height: 720px;
                 margin: 0;
                 padding: 0;
                 background-color: #ffffff;
                 border: none;
                 position: relative;
                 display: block;
             }
        </style>""",
        html,
        count=1,
    )
    html = re.sub(
        r"<body>\s*<div class=\"card\" style=\"width: 100%\">[\s\S]*?<div id=\"mynetwork\" class=\"card-body\"></div>[\s\S]*?</div>",
        "<body>\n        <div id=\"mynetwork\"></div>",
        html,
        count=1,
    )
    fit_script = """
              network.once("stabilizationIterationsDone", function () {
                  network.setOptions({physics: false});
                  network.fit({animation: false});
                  network.moveTo({scale: 1.45});
              });
    """
    html = html.replace("              return network;", fit_script + "\n              return network;", 1)
    output_path.write_text(html, encoding="utf-8")


def render_period_html(nodes_path: Path, edges_path: Path, output_path: Path, min_edge_weight: int) -> None:
    nodes_df = pd.read_csv(nodes_path)
    edges_df = pd.read_csv(edges_path)
    if not edges_df.empty:
        edges_df = edges_df[edges_df["Weight"] >= min_edge_weight].copy()
    network = build_network(nodes_df, edges_df)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    network.write_html(str(output_path), notebook=False)
    expand_network_view(output_path)


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
