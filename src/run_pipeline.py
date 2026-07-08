from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from build_graphs import build_period_graphs, build_topic_burst, build_topic_trend, save_graph_outputs
from build_sankey import build_sankey_frames, render_sankey
from extract_topics import tag_papers
from fetch_dblp import fetch_all, load_manual_papers, load_manual_papers_from_files
from periods import DEFAULT_PERIOD_END, DEFAULT_PERIOD_SIZE, DEFAULT_PERIOD_START, build_periods
from visualize_pyvis import render_period_html


def ensure_dirs(project_root: Path) -> dict[str, Path]:
    paths = {
        "raw": project_root / "data" / "raw",
        "processed": project_root / "data" / "processed",
        "csv": project_root / "outputs" / "csv",
        "gephi": project_root / "outputs" / "gephi",
        "html": project_root / "outputs" / "html",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def build_index_html(html_dir: Path, periods: list[str]) -> None:
    links = [
        *[(f"Topic Network {period}", f"topic_network_{period}.html") for period in periods],
        ("Topic Transition Sankey", "topic_transition_sankey.html"),
    ]
    lines = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8"><title>Topic Evolution Outputs</title></head><body>',
        "<h1>Topic Evolution Outputs</h1>",
        "<ul>",
    ]
    for label, href in links:
        lines.append(f'<li><a href="{href}">{label}</a></li>')
    lines.extend(["</ul>", "</body></html>"])
    (html_dir / "index.html").write_text("\n".join(lines), encoding="utf-8")


def run_pipeline(
    start_year: int,
    end_year: int,
    min_edge_weight: int,
    sankey_min_weight: int,
    skip_fetch: bool,
    use_manual_raw: bool,
    manual_raw_files: list[str],
    period_start: int,
    period_end: int,
    period_size: int,
) -> None:
    project_root = Path(__file__).resolve().parent.parent
    paths = ensure_dirs(project_root)
    periods = build_periods(period_start, period_end, period_size)

    raw_papers = paths["raw"] / "papers.csv"
    manual_raw_dir = paths["raw"] / "manual"
    processed_papers = paths["processed"] / "papers.csv"
    paper_topics = paths["processed"] / "paper_topics.csv"
    untagged_papers = paths["csv"] / "untagged_papers.csv"
    sankey_nodes = paths["csv"] / "sankey_nodes.csv"
    sankey_edges = paths["csv"] / "sankey_edges.csv"
    sankey_html = paths["html"] / "topic_transition_sankey.html"

    if manual_raw_files:
        papers_df = load_manual_papers_from_files(
            [Path(path) for path in manual_raw_files],
            start_year,
            end_year,
        )
        raw_papers.parent.mkdir(parents=True, exist_ok=True)
        papers_df.to_csv(raw_papers, index=False, encoding="utf-8")
        papers_df.to_csv(processed_papers, index=False, encoding="utf-8")
    elif use_manual_raw:
        papers_df = load_manual_papers(manual_raw_dir, start_year, end_year)
        raw_papers.parent.mkdir(parents=True, exist_ok=True)
        papers_df.to_csv(raw_papers, index=False, encoding="utf-8")
        papers_df.to_csv(processed_papers, index=False, encoding="utf-8")
    elif skip_fetch and processed_papers.exists():
        papers_df = pd.read_csv(processed_papers)
    else:
        papers_df = fetch_all(start_year, end_year)
        papers_df.to_csv(raw_papers, index=False, encoding="utf-8")
        papers_df.to_csv(processed_papers, index=False, encoding="utf-8")

    tagged_df, untagged_df = tag_papers(
        papers_df,
        period_start=period_start,
        period_end=period_end,
        period_size=period_size,
    )
    tagged_df.to_csv(paper_topics, index=False, encoding="utf-8")
    untagged_df.to_csv(untagged_papers, index=False, encoding="utf-8")

    trend_df = build_topic_trend(tagged_df)
    burst_df = build_topic_burst(trend_df)
    nodes_by_period, edges_by_period = build_period_graphs(
        tagged_df,
        period_start=period_start,
        period_end=period_end,
        period_size=period_size,
    )
    save_graph_outputs(trend_df, burst_df, nodes_by_period, edges_by_period, paths["csv"], paths["gephi"])

    for period in periods:
        nodes_path = paths["gephi"] / f"topic_nodes_{period}.csv"
        edges_path = paths["gephi"] / f"topic_edges_{period}.csv"
        if nodes_path.exists() and edges_path.exists():
            render_period_html(
                nodes_path,
                edges_path,
                paths["html"] / f"topic_network_{period}.html",
                min_edge_weight,
            )

    sankey_nodes_df, sankey_edges_df = build_sankey_frames(
        tagged_df,
        period_start=period_start,
        period_end=period_end,
        period_size=period_size,
    )
    sankey_nodes_df.to_csv(sankey_nodes, index=False, encoding="utf-8")
    sankey_edges_df.to_csv(sankey_edges, index=False, encoding="utf-8")
    render_sankey(sankey_nodes_df, sankey_edges_df, sankey_html, sankey_min_weight)
    build_index_html(paths["html"], periods)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=DEFAULT_PERIOD_START)
    parser.add_argument("--end-year", type=int, default=DEFAULT_PERIOD_END)
    parser.add_argument("--min-edge-weight", type=int, default=1)
    parser.add_argument("--sankey-min-weight", type=int, default=2)
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--use-manual-raw", action="store_true")
    parser.add_argument("--manual-raw-file", action="append", default=[])
    parser.add_argument("--period-start", type=int, default=DEFAULT_PERIOD_START)
    parser.add_argument("--period-end", type=int, default=DEFAULT_PERIOD_END)
    parser.add_argument("--period-size", type=int, default=DEFAULT_PERIOD_SIZE)
    args = parser.parse_args()
    run_pipeline(
        start_year=args.start_year,
        end_year=args.end_year,
        min_edge_weight=args.min_edge_weight,
        sankey_min_weight=args.sankey_min_weight,
        skip_fetch=args.skip_fetch,
        use_manual_raw=args.use_manual_raw,
        manual_raw_files=args.manual_raw_file,
        period_start=args.period_start,
        period_end=args.period_end,
        period_size=args.period_size,
    )


if __name__ == "__main__":
    main()
