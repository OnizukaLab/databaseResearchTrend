from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import pandas as pd

from periods import DEFAULT_PERIOD_END, DEFAULT_PERIOD_SIZE, DEFAULT_PERIOD_START, build_periods


def build_topic_trend(tagged_df: pd.DataFrame) -> pd.DataFrame:
    if tagged_df.empty:
        return pd.DataFrame(columns=["topic", "category", "year", "count", "total_papers", "share"])
    tagged = tagged_df[tagged_df["period"] != "other"].copy()
    if tagged.empty:
        return pd.DataFrame(columns=["topic", "category", "year", "count", "total_papers", "share"])
    counts = (
        tagged.groupby(["topic", "category", "year"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )
    totals = tagged.groupby("year", as_index=False).size().rename(columns={"size": "total_papers"})
    merged = counts.merge(totals, on="year", how="left")
    merged["share"] = merged["count"] / merged["total_papers"]
    return merged.sort_values(["year", "topic"]).reset_index(drop=True)


def build_topic_burst(trend_df: pd.DataFrame) -> pd.DataFrame:
    if trend_df.empty:
        return pd.DataFrame(
            columns=["topic", "category", "year", "share", "prev_avg_share", "burst_score"]
        )
    rows: list[dict[str, object]] = []
    for (topic, category), group in trend_df.groupby(["topic", "category"]):
        year_to_share = dict(zip(group["year"], group["share"]))
        for year in sorted(group["year"].unique()):
            prev_years = [year - 3, year - 2, year - 1]
            prev_values = [year_to_share[y] for y in prev_years if y in year_to_share]
            prev_avg = sum(prev_values) / len(prev_values) if len(prev_values) == 3 else None
            share = year_to_share[year]
            rows.append(
                {
                    "topic": topic,
                    "category": category,
                    "year": year,
                    "share": share,
                    "prev_avg_share": prev_avg,
                    "burst_score": None if prev_avg is None else share - prev_avg,
                }
            )
    return pd.DataFrame(rows).sort_values(["year", "topic"]).reset_index(drop=True)


def build_period_graphs(
    tagged_df: pd.DataFrame,
    period_start: int = DEFAULT_PERIOD_START,
    period_end: int = DEFAULT_PERIOD_END,
    period_size: int = DEFAULT_PERIOD_SIZE,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    periods = build_periods(period_start, period_end, period_size)
    nodes_by_period: dict[str, pd.DataFrame] = {}
    edges_by_period: dict[str, pd.DataFrame] = {}

    if tagged_df.empty:
        for period in periods:
            nodes_by_period[period] = pd.DataFrame(
                columns=["Id", "Label", "Type", "Category", "Period", "Count"]
            )
            edges_by_period[period] = pd.DataFrame(
                columns=["Source", "Target", "Type", "Weight", "Period"]
            )
        return nodes_by_period, edges_by_period

    valid = tagged_df[tagged_df["period"].isin(periods)].copy()

    for period in periods:
        period_df = valid[valid["period"] == period]
        node_counts = (
            period_df.groupby(["topic", "category"], as_index=False)
            .size()
            .rename(columns={"size": "Count"})
        )
        node_counts["Id"] = node_counts["topic"]
        node_counts["Label"] = node_counts["topic"]
        node_counts["Type"] = "Undirected"
        node_counts["Period"] = period
        node_counts = node_counts.rename(columns={"category": "Category"})
        node_cols = ["Id", "Label", "Type", "Category", "Period", "Count"]
        nodes_by_period[period] = node_counts[node_cols].sort_values("Id").reset_index(drop=True)

        edge_weights: dict[tuple[str, str], int] = {}
        for _, paper_topics in period_df.groupby("paper_id"):
            topics = sorted(set(paper_topics["topic"]))
            for source, target in combinations(topics, 2):
                edge_weights[(source, target)] = edge_weights.get((source, target), 0) + 1

        edge_rows = [
            {
                "Source": source,
                "Target": target,
                "Type": "Undirected",
                "Weight": weight,
                "Period": period,
            }
            for (source, target), weight in sorted(edge_weights.items())
        ]
        edges_by_period[period] = pd.DataFrame(
            edge_rows,
            columns=["Source", "Target", "Type", "Weight", "Period"],
        )

    return nodes_by_period, edges_by_period


def save_graph_outputs(
    trend_df: pd.DataFrame,
    burst_df: pd.DataFrame,
    nodes_by_period: dict[str, pd.DataFrame],
    edges_by_period: dict[str, pd.DataFrame],
    csv_dir: Path,
    gephi_dir: Path,
) -> None:
    csv_dir.mkdir(parents=True, exist_ok=True)
    gephi_dir.mkdir(parents=True, exist_ok=True)

    trend_df.to_csv(csv_dir / "topic_trend.csv", index=False, encoding="utf-8")
    burst_df.to_csv(csv_dir / "topic_burst.csv", index=False, encoding="utf-8")

    for period, nodes_df in nodes_by_period.items():
        nodes_df.to_csv(gephi_dir / f"topic_nodes_{period}.csv", index=False, encoding="utf-8")
        edges_by_period[period].to_csv(
            gephi_dir / f"topic_edges_{period}.csv",
            index=False,
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--csv-dir", required=True)
    parser.add_argument("--gephi-dir", required=True)
    parser.add_argument("--period-start", type=int, default=DEFAULT_PERIOD_START)
    parser.add_argument("--period-end", type=int, default=DEFAULT_PERIOD_END)
    parser.add_argument("--period-size", type=int, default=DEFAULT_PERIOD_SIZE)
    args = parser.parse_args()

    tagged_df = pd.read_csv(args.input)
    trend_df = build_topic_trend(tagged_df)
    burst_df = build_topic_burst(trend_df)
    nodes_by_period, edges_by_period = build_period_graphs(
        tagged_df,
        period_start=args.period_start,
        period_end=args.period_end,
        period_size=args.period_size,
    )
    save_graph_outputs(trend_df, burst_df, nodes_by_period, edges_by_period, Path(args.csv_dir), Path(args.gephi_dir))


if __name__ == "__main__":
    main()
