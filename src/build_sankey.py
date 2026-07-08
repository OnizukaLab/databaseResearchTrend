from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from periods import DEFAULT_PERIOD_END, DEFAULT_PERIOD_SIZE, DEFAULT_PERIOD_START, build_periods, period_bounds


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
    period_annotations = [
        {
            "xref": "paper",
            "yref": "paper",
            "x": 0.001 if len(period_order) == 1 else idx / max(len(period_order) - 1, 1),
            "y": 1.08,
            "text": period,
            "showarrow": False,
            "font": {"size": 13},
        }
        for period, idx in period_order.items()
    ]
    fig.update_layout(
        title="Topic Transition Sankey",
        font={"size": 12},
        annotations=period_annotations,
        height=max(900, 70 * max_nodes_in_period),
        margin={"t": 70, "l": 20, "r": 20, "b": 20},
    )
    fig.write_html(str(output_path), include_plotlyjs="cdn")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--nodes-output", required=True)
    parser.add_argument("--edges-output", required=True)
    parser.add_argument("--html-output", required=True)
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


if __name__ == "__main__":
    main()
