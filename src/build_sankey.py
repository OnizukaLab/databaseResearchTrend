from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from periods import DEFAULT_PERIOD_END, DEFAULT_PERIOD_SIZE, DEFAULT_PERIOD_START, build_periods, period_bounds


def _period_axis_artifacts(
    period_order: dict[str, int],
    x_start: float,
    x_end: float,
    y_axis: float,
    y_label: float,
    label_prefix: str = "",
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not period_order:
        return [], []

    denom = max(len(period_order) - 1, 1)
    tick_positions = {
        period: x_start + (x_end - x_start) * (idx / denom)
        for period, idx in period_order.items()
    }
    axis_shapes: list[dict[str, object]] = [
        {
            "type": "line",
            "xref": "paper",
            "yref": "paper",
            "x0": x_start,
            "x1": x_end,
            "y0": y_axis,
            "y1": y_axis,
            "line": {"color": "rgba(51,65,85,0.55)", "width": 1.5},
        }
    ]
    axis_annotations: list[dict[str, object]] = [
        {
            "xref": "paper",
            "yref": "paper",
            "x": (x_start + x_end) / 2,
            "y": y_label - 0.045,
            "text": f"{label_prefix}Period".strip(),
            "showarrow": False,
            "font": {"size": 13, "color": "#334155"},
        }
    ]
    for period, x_pos in tick_positions.items():
        axis_shapes.append(
            {
                "type": "line",
                "xref": "paper",
                "yref": "paper",
                "x0": x_pos,
                "x1": x_pos,
                "y0": y_axis,
                "y1": y_axis + 0.018,
                "line": {"color": "rgba(51,65,85,0.55)", "width": 1.5},
            }
        )
        axis_annotations.append(
            {
                "xref": "paper",
                "yref": "paper",
                "x": x_pos,
                "y": y_label,
                "text": period,
                "showarrow": False,
                "font": {"size": 13, "color": "#0f172a"},
            }
        )
    return axis_annotations, axis_shapes


def count_by_topic_period(tagged_df: pd.DataFrame) -> dict[tuple[str, str], int]:
    grouped = tagged_df.groupby(["topic", "period"]).size()
    return {(topic, period): int(count) for (topic, period), count in grouped.items()}


def build_sankey_frames(
    tagged_df: pd.DataFrame,
    period_start: int = DEFAULT_PERIOD_START,
    period_end: int = DEFAULT_PERIOD_END,
    period_size: int = DEFAULT_PERIOD_SIZE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    periods = build_periods(period_start, period_end, period_size)
    if tagged_df.empty:
        return (
            pd.DataFrame(columns=["node", "topic", "category", "period", "count"]),
            pd.DataFrame(
                columns=[
                    "source",
                    "target",
                    "source_topic",
                    "target_topic",
                    "source_period",
                    "target_period",
                    "weight",
                    "transition_type",
                ]
            ),
        )
    filtered = tagged_df[tagged_df["period"].isin(periods)].copy()
    topic_counts = count_by_topic_period(filtered)
    topic_category = (
        filtered[["topic", "category"]]
        .drop_duplicates()
        .set_index("topic")["category"]
        .to_dict()
    )

    node_rows: list[dict[str, object]] = []
    edge_rows: list[dict[str, object]] = []

    for period in periods:
        for topic, category in sorted(topic_category.items()):
            count = topic_counts.get((topic, period), 0)
            if count > 0:
                node_rows.append(
                    {
                        "node": f"{topic}@{period}",
                        "topic": topic,
                        "category": category,
                        "period": period,
                        "count": count,
                    }
                )

    for left_period, right_period in zip(periods, periods[1:]):
        for topic in sorted(topic_category):
            left_count = topic_counts.get((topic, left_period), 0)
            right_count = topic_counts.get((topic, right_period), 0)
            if left_count and right_count:
                edge_rows.append(
                    {
                        "source": f"{topic}@{left_period}",
                        "target": f"{topic}@{right_period}",
                        "source_topic": topic,
                        "target_topic": topic,
                        "source_period": left_period,
                        "target_period": right_period,
                        "weight": min(left_count, right_count),
                        "transition_type": "persistence",
                    }
                )

        left_start, left_end = period_bounds(left_period)
        right_start, right_end = period_bounds(right_period)
        left_window = filtered[filtered["year"].between(left_start, left_end)]
        right_window = filtered[filtered["year"].between(right_start, right_end)]

        if left_window.empty or right_window.empty:
            continue

        left_pairs = (
            left_window.groupby("paper_id")["topic"]
            .apply(lambda topics: sorted(set(topics)))
            .tolist()
        )
        right_pairs = (
            right_window.groupby("paper_id")["topic"]
            .apply(lambda topics: sorted(set(topics)))
            .tolist()
        )

        left_topics = sorted({topic for topics in left_pairs for topic in topics})
        right_topics = sorted({topic for topics in right_pairs for topic in topics})
        transition_weights: dict[tuple[str, str], int] = {}

        for paper_topics_a in left_pairs:
            for paper_topics_b in right_pairs:
                for topic_a, topic_b in product(paper_topics_a, paper_topics_b):
                    if topic_a == topic_b:
                        continue
                    transition_weights[(topic_a, topic_b)] = transition_weights.get((topic_a, topic_b), 0) + 1

        for (topic_a, topic_b), weight in sorted(transition_weights.items()):
            if topic_a not in left_topics or topic_b not in right_topics:
                continue
            edge_rows.append(
                {
                    "source": f"{topic_a}@{left_period}",
                    "target": f"{topic_b}@{right_period}",
                    "source_topic": topic_a,
                    "target_topic": topic_b,
                    "source_period": left_period,
                    "target_period": right_period,
                    "weight": weight,
                    "transition_type": "cooccurrence",
                }
            )

    return (
        pd.DataFrame(node_rows, columns=["node", "topic", "category", "period", "count"]),
        pd.DataFrame(
            edge_rows,
            columns=[
                "source",
                "target",
                "source_topic",
                "target_topic",
                "source_period",
                "target_period",
                "weight",
                "transition_type",
            ],
        ),
    )


def render_sankey(nodes_df: pd.DataFrame, edges_df: pd.DataFrame, output_path: Path, min_weight: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if nodes_df.empty:
        go.Figure().write_html(str(output_path), include_plotlyjs="cdn")
        return

    filtered_edges = edges_df[edges_df["weight"] >= min_weight].copy()
    node_names = list(nodes_df["node"])
    node_index = {name: idx for idx, name in enumerate(node_names)}
    display_labels = nodes_df["topic"].tolist()
    period_order = {period: idx for idx, period in enumerate(nodes_df["period"].drop_duplicates())}
    max_nodes_in_period = int(nodes_df.groupby("period").size().max())
    node_x = [
        0.001 if len(period_order) == 1 else period_order[period] / max(len(period_order) - 1, 1)
        for period in nodes_df["period"]
    ]
    node_y_by_name: dict[str, float] = {}
    for period, group in nodes_df.groupby("period", sort=False):
        group = group.sort_values(["count", "topic"], ascending=[False, True]).reset_index(drop=True)
        count = len(group)
        if count == 1:
            positions = [0.5]
        else:
            top_margin = 0.03
            bottom_margin = 0.03
            usable = 1.0 - top_margin - bottom_margin
            slot = usable / count
            positions = [top_margin + slot * idx + slot / 2 for idx in range(count)]
        for position, node_name in zip(positions, group["node"]):
            node_y_by_name[node_name] = position
    node_y = [node_y_by_name[name] for name in node_names]
    filtered_edges = filtered_edges[
        filtered_edges["source"].isin(node_index) & filtered_edges["target"].isin(node_index)
    ].copy()

    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="fixed",
                node={
                    "label": display_labels,
                    "pad": 28,
                    "thickness": 18,
                    "x": node_x,
                    "y": node_y,
                    "customdata": nodes_df["period"].tolist(),
                    "hovertemplate": "%{label}<br>%{customdata}<extra></extra>",
                },
                link={
                    "source": [node_index[src] for src in filtered_edges["source"]],
                    "target": [node_index[tgt] for tgt in filtered_edges["target"]],
                    "value": filtered_edges["weight"].tolist(),
                    "label": filtered_edges["transition_type"].tolist(),
                    "customdata": [
                        f"{src_period} -> {tgt_period}"
                        for src_period, tgt_period in zip(
                            filtered_edges["source_period"],
                            filtered_edges["target_period"],
                        )
                    ],
                    "hovertemplate": "%{source.label} -> %{target.label}<br>%{customdata}<br>weight=%{value}<br>%{label}<extra></extra>",
                },
            )
        ]
    )
    axis_annotations, axis_shapes = _period_axis_artifacts(
        period_order=period_order,
        x_start=0.001 if len(period_order) == 1 else 0.0,
        x_end=0.999 if len(period_order) == 1 else 1.0,
        y_axis=-0.045,
        y_label=-0.08,
    )
    fig.update_layout(
        title="Topic Transition Sankey",
        font={"size": 12},
        annotations=axis_annotations,
        shapes=axis_shapes,
        height=max(900, 70 * max_nodes_in_period),
        margin={"t": 70, "l": 20, "r": 20, "b": 90},
    )
    fig.write_html(str(output_path), include_plotlyjs="cdn")


def _preview_topic_order(nodes_df: pd.DataFrame) -> list[str]:
    topic_totals = (
        nodes_df.groupby("topic", as_index=False)["count"]
        .sum()
        .sort_values(["count", "topic"], ascending=[False, True])
    )
    return topic_totals["topic"].tolist()


def _build_preview_frames(
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    max_topics_per_period: int = 5,
    max_cross_edges_per_step: int = 6,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if nodes_df.empty:
        return nodes_df.copy(), edges_df.iloc[0:0].copy()

    topic_order = _preview_topic_order(nodes_df)
    topic_rank = {topic: idx for idx, topic in enumerate(topic_order)}
    periods = nodes_df["period"].drop_duplicates().tolist()

    selected_topics: set[str] = set()
    for period in periods:
        period_nodes = (
            nodes_df[nodes_df["period"] == period]
            .sort_values(["count", "topic"], ascending=[False, True])
            .head(max_topics_per_period)
        )
        selected_topics.update(period_nodes["topic"].tolist())

    preview_nodes = nodes_df[nodes_df["topic"].isin(selected_topics)].copy()
    preview_nodes = preview_nodes.sort_values(
        ["period", "topic"],
        key=lambda col: col.map(topic_rank) if col.name == "topic" else col,
    )

    preview_edges: list[pd.DataFrame] = []

    persistence = edges_df[
        (edges_df["transition_type"] == "persistence")
        & (edges_df["source_topic"].isin(selected_topics))
        & (edges_df["target_topic"].isin(selected_topics))
    ].copy()
    preview_edges.append(persistence)

    for left_period, right_period in zip(periods, periods[1:]):
        cross = edges_df[
            (edges_df["transition_type"] == "cooccurrence")
            & (edges_df["source_period"] == left_period)
            & (edges_df["target_period"] == right_period)
            & (edges_df["source_topic"].isin(selected_topics))
            & (edges_df["target_topic"].isin(selected_topics))
        ].copy()
        cross = cross.sort_values(
            ["weight", "source_topic", "target_topic"],
            ascending=[False, True, True],
        ).head(max_cross_edges_per_step)
        preview_edges.append(cross)

    preview_edges_df = (
        pd.concat(preview_edges, ignore_index=True)
        if preview_edges
        else edges_df.iloc[0:0].copy()
    )
    preview_edges_df = preview_edges_df.drop_duplicates(
        subset=["source", "target", "transition_type"]
    ).copy()
    return preview_nodes, preview_edges_df


def render_sankey_preview(
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if nodes_df.empty:
        go.Figure().write_html(str(output_path), include_plotlyjs="cdn")
        return

    preview_nodes, preview_edges = _build_preview_frames(nodes_df, edges_df)
    node_names = list(preview_nodes["node"])
    node_index = {name: idx for idx, name in enumerate(node_names)}
    periods = preview_nodes["period"].drop_duplicates().tolist()
    period_order = {period: idx for idx, period in enumerate(periods)}
    topic_order = _preview_topic_order(preview_nodes)
    topic_rank = {topic: idx for idx, topic in enumerate(topic_order)}

    node_x = [
        0.02 if len(period_order) == 1 else 0.04 + 0.92 * period_order[period] / max(len(period_order) - 1, 1)
        for period in preview_nodes["period"]
    ]

    node_y_by_name: dict[str, float] = {}
    for period, group in preview_nodes.groupby("period", sort=False):
        group = group.sort_values(
            ["topic"],
            key=lambda col: col.map(topic_rank),
        ).reset_index(drop=True)
        count = len(group)
        if count == 1:
            positions = [0.5]
        else:
            top_margin = 0.1
            bottom_margin = 0.08
            usable = 1.0 - top_margin - bottom_margin
            slot = usable / count
            positions = [top_margin + slot * idx + slot / 2 for idx in range(count)]
        for position, node_name in zip(positions, group["node"]):
            node_y_by_name[node_name] = position
    node_y = [node_y_by_name[name] for name in node_names]

    preview_edges = preview_edges[
        preview_edges["source"].isin(node_index) & preview_edges["target"].isin(node_index)
    ].copy()
    preview_edges["link_color"] = preview_edges["transition_type"].map(
        {"persistence": "rgba(59, 130, 246, 0.45)", "cooccurrence": "rgba(15, 23, 42, 0.18)"}
    ).fillna("rgba(120,120,120,0.2)")

    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="fixed",
                node={
                    "label": preview_nodes["topic"].tolist(),
                    "pad": 22,
                    "thickness": 20,
                    "line": {"color": "rgba(30,41,59,0.35)", "width": 1},
                    "color": "rgba(251,146,60,0.72)",
                    "x": node_x,
                    "y": node_y,
                    "customdata": preview_nodes["period"].tolist(),
                    "hovertemplate": "%{label}<br>%{customdata}<extra></extra>",
                },
                link={
                    "source": [node_index[src] for src in preview_edges["source"]],
                    "target": [node_index[tgt] for tgt in preview_edges["target"]],
                    "value": preview_edges["weight"].tolist(),
                    "color": preview_edges["link_color"].tolist(),
                    "hovertemplate": "%{source.label} -> %{target.label}<br>weight=%{value}<extra></extra>",
                },
            )
        ]
    )
    fig.update_layout(
        title="Topic Transition Sankey",
        font={"size": 16, "color": "#0f172a"},
        width=1600,
        height=900,
        margin={"t": 80, "l": 40, "r": 40, "b": 110},
        paper_bgcolor="white",
        plot_bgcolor="white",
        annotations=_period_axis_artifacts(
            period_order=period_order,
            x_start=0.04,
            x_end=0.96,
            y_axis=-0.05,
            y_label=-0.09,
        )[0],
        shapes=_period_axis_artifacts(
            period_order=period_order,
            x_start=0.04,
            x_end=0.96,
            y_axis=-0.05,
            y_label=-0.09,
        )[1],
    )
    fig.write_html(str(output_path), include_plotlyjs="cdn")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--nodes-output", required=True)
    parser.add_argument("--edges-output", required=True)
    parser.add_argument("--html-output", required=True)
    parser.add_argument("--preview-html-output")
    parser.add_argument("--min-weight", type=int, default=2)
    parser.add_argument("--period-start", type=int, default=DEFAULT_PERIOD_START)
    parser.add_argument("--period-end", type=int, default=DEFAULT_PERIOD_END)
    parser.add_argument("--period-size", type=int, default=DEFAULT_PERIOD_SIZE)
    args = parser.parse_args()

    tagged_df = pd.read_csv(args.input)
    nodes_df, edges_df = build_sankey_frames(
        tagged_df,
        period_start=args.period_start,
        period_end=args.period_end,
        period_size=args.period_size,
    )
    Path(args.nodes_output).parent.mkdir(parents=True, exist_ok=True)
    nodes_df.to_csv(args.nodes_output, index=False, encoding="utf-8")
    edges_df.to_csv(args.edges_output, index=False, encoding="utf-8")
    render_sankey(nodes_df, edges_df, Path(args.html_output), args.min_weight)
    if args.preview_html_output:
        render_sankey_preview(nodes_df, edges_df, Path(args.preview_html_output))


if __name__ == "__main__":
    main()
