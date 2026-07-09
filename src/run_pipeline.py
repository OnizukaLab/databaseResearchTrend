from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from build_graphs import build_period_graphs, build_topic_burst, build_topic_trend, save_graph_outputs
from build_sankey import build_sankey_frames, render_sankey
from extract_topics import tag_papers
from fetch_dblp import DEFAULT_VENUE_KEYS, fetch_all, load_manual_papers, load_manual_papers_from_files
from periods import DEFAULT_PERIOD_END, DEFAULT_PERIOD_SIZE, DEFAULT_PERIOD_START, build_periods
from visualize_pyvis import CATEGORY_COLORS, render_period_html


def ensure_dirs(project_root: Path, target_slug: str) -> dict[str, Path]:
    paths = {
        "raw_root": project_root / "data" / "raw",
        "processed_root": project_root / "data" / "processed",
        "csv_root": project_root / "outputs" / "csv",
        "gephi_root": project_root / "outputs" / "gephi",
        "html_root": project_root / "outputs" / "html",
        "raw": project_root / "data" / "raw" / target_slug,
        "processed": project_root / "data" / "processed" / target_slug,
        "csv": project_root / "outputs" / "csv" / target_slug,
        "gephi": project_root / "outputs" / "gephi" / target_slug,
        "html": project_root / "outputs" / "html" / target_slug,
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def normalize_target_slug(value: str) -> str:
    slug = str(value).strip().lower().replace(" ", "-").replace("_", "-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def normalize_venue_name(value: str) -> str:
    normalized = str(value).strip().upper()
    if normalized in {"NIPS", "NEURIPS"}:
        return "NEURIPS"
    return normalized


def infer_target_slug(venue_keys: list[str], output_prefix: str) -> str:
    custom = normalize_target_slug(output_prefix)
    if custom:
        return custom
    normalized_keys = sorted(venue_keys)
    if normalized_keys == sorted(DEFAULT_VENUE_KEYS):
        return "database"
    if normalized_keys == ["nips"]:
        return "neurips"
    return "-".join(normalized_keys)


def infer_title_prefix(venue_keys: list[str]) -> str:
    normalized_keys = sorted(venue_keys)
    if normalized_keys == sorted(DEFAULT_VENUE_KEYS):
        return "Database "
    if normalized_keys == ["nips"]:
        return "NeurIPS "
    return ""


def build_preview_payload(nodes_path: Path, edges_path: Path, min_edge_weight: int) -> dict[str, list[dict[str, object]]]:
    nodes_df = pd.read_csv(nodes_path)
    edges_df = pd.read_csv(edges_path)
    if not edges_df.empty:
        edges_df = edges_df[edges_df["Weight"] >= min_edge_weight].copy()

    max_count = float(nodes_df["Count"].max()) if not nodes_df.empty else 1.0
    nodes = []
    for row in nodes_df.to_dict("records"):
        normalized = (float(row["Count"]) / max_count) ** 0.5 if max_count > 0 else 0.0
        size = 14 + 22 * normalized
        nodes.append(
            {
                "id": row["Id"],
                "label": row["Label"],
                "title": f"{row['Label']}<br>{row['Category']}<br>count={row['Count']}",
                "value": float(row["Count"]),
                "size": round(size, 2),
                "color": CATEGORY_COLORS.get(row["Category"], "#577590"),
                "font": {"color": "#0f172a", "size": 18, "face": "Arial"},
            }
        )

    edges = []
    for row in edges_df.to_dict("records"):
        edges.append(
            {
                "from": row["Source"],
                "to": row["Target"],
                "value": float(row["Weight"]),
                "width": round(0.8 + float(row["Weight"]) * 1.15, 2),
                "title": f"co-occurrence={row['Weight']}",
                "color": {"color": "#94a3b8", "opacity": 0.35},
                "smooth": {"enabled": True, "type": "dynamic"},
            }
        )
    return {"nodes": nodes, "edges": edges}


def build_index_html(html_dir: Path, gephi_dir: Path, periods: list[str], min_edge_weight: int, title_prefix: str = "") -> None:
    preview_payloads: dict[str, dict[str, list[dict[str, object]]]] = {}
    for period in periods:
        nodes_path = gephi_dir / f"topic_nodes_{period}.csv"
        edges_path = gephi_dir / f"topic_edges_{period}.csv"
        if nodes_path.exists() and edges_path.exists():
            preview_payloads[period] = build_preview_payload(nodes_path, edges_path, min_edge_weight)

    lines = [
        "<!doctype html>",
        "<html lang=\"en\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>Topic Evolution Outputs</title>",
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/dist/vis-network.min.js" integrity="sha512-LnvoEWDFrqGHlHmDD2101OrLcbsfkrzoSpvtSQtxK3RMnRV0eOkhhBN2dXHKRrUU8p2DGRTk35n4O8nWSVe1mQ==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>',
        '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/dist/dist/vis-network.min.css" integrity="sha512-WgxfT5LWjfszlPHXRmBWHkV2eceiWTOBvrKCNbdgDYTHrT2AeLCGbF4sZlZw3UMN3WtL0tGUoIAKsu8mllg/XA==" crossorigin="anonymous" referrerpolicy="no-referrer" />',
        "<style>",
        ":root { color-scheme: light; --bg:#f8fafc; --panel:#ffffff; --ink:#0f172a; --muted:#475569; --line:#dbe3ee; --accent:#2563eb; }",
        "* { box-sizing: border-box; }",
        "body { margin:0; font-family: Arial, sans-serif; background:var(--bg); color:var(--ink); }",
        ".page { max-width: 1920px; margin: 0 auto; padding: 20px; }",
        "h1 { margin: 0 0 8px; font-size: 2rem; }",
        "h2 { margin: 0 0 12px; font-size: 1.25rem; }",
        "p.lead { margin: 0 0 24px; color: var(--muted); }",
        ".panel { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.08); overflow: hidden; }",
        ".panel-header { display:flex; align-items:center; justify-content:space-between; gap:16px; padding: 16px 20px; border-bottom: 1px solid var(--line); }",
        ".panel-header h2 { margin:0; font-size:1.1rem; }",
        ".panel-header a { color: var(--accent); text-decoration: none; font-weight: 600; }",
        ".panel iframe { display:block; width:100%; border:0; background:#fff; }",
        ".sankey-frame { height: 1080px; }",
        ".section { margin-top: 28px; }",
        ".section-head { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; margin-bottom: 14px; }",
        ".section-head p { margin:0; color: var(--muted); }",
        ".gallery { display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 16px; align-items:start; }",
        ".network-card { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.08); overflow:hidden; }",
        ".network-meta { display:flex; align-items:center; justify-content:space-between; gap:12px; padding: 14px 16px; border-bottom: 1px solid var(--line); }",
        ".network-meta strong { font-size: 1rem; }",
        ".network-meta a { color: var(--accent); text-decoration:none; font-weight:600; white-space:nowrap; }",
        ".network-preview { width:100%; height:720px; background:#fff; }",
        ".network-preview canvas { outline:none; }",
        "@media (max-width: 1200px) { .gallery { grid-template-columns: 1fr; } .sankey-frame { height: 880px; } .network-preview { height: 720px; } }",
        "</style>",
        "</head><body>",
        "<div class=\"page\">",
        f"<h1>{title_prefix}Topic Evolution Outputs</h1>".replace("  ", " ").strip(),
        f"<p class=\"lead\">Sankey transition overview followed by period-wise topic clustering views for {', '.join(periods)}.</p>",
        "<section class=\"panel\">",
        "<div class=\"panel-header\">",
        f"<h2>{title_prefix}Topic Transition Sankey</h2>".replace("  ", " ").strip(),
        '<a href="topic_transition_sankey.html">Open standalone</a>',
        "</div>",
        '<iframe class="sankey-frame" src="topic_transition_sankey.html" loading="lazy" title="Topic Transition Sankey"></iframe>',
        "</section>",
        '<section class="section">',
        '<div class="section-head">',
        "<div>",
        "<h2>Period-wise Topic Networks</h2>",
        "<p>Three clustering views are arranged side by side for direct comparison across periods.</p>",
        "</div>",
        "</div>",
        '<div class="gallery">',
    ]
    for period in periods:
        title = f"{title_prefix}Topic Network {period}".replace("  ", " ").strip()
        href = f"topic_network_{period}.html"
        lines.extend(
            [
                '<article class="network-card">',
                '<div class="network-meta">',
                f"<strong>{period}</strong>",
                f'<a href="{href}">Open standalone</a>',
                "</div>",
                f'<div class="network-preview" id="network-preview-{period}"></div>',
                "</article>",
            ]
        )
    lines.extend(
        [
            "</div>",
            "</section>",
            "<script>",
            "const previewOptions = {",
            "  autoResize: true,",
            "  interaction: { hover: true, navigationButtons: false, keyboard: false },",
            "  physics: {",
            "    enabled: true,",
            "    solver: 'forceAtlas2Based',",
            "    stabilization: { iterations: 1200, fit: true },",
            "    minVelocity: 0.15,",
            "    forceAtlas2Based: { gravitationalConstant: -80, centralGravity: 0.01, springLength: 170, springConstant: 0.04, damping: 0.9, avoidOverlap: 0.8 }",
            "  },",
            "  edges: { smooth: { type: 'dynamic' }, color: { inherit: false } },",
            "  nodes: { shape: 'dot', borderWidth: 1.5, borderWidthSelected: 2, scaling: { min: 10, max: 36 } }",
            "};",
        ]
    )
    for period in periods:
        payload = preview_payloads.get(period, {"nodes": [], "edges": []})
        var_name = f"data_{period.replace('-', '_')}"
        lines.extend(
            [
                f"const {var_name} = {json.dumps(payload)};",
                f"(function() {{",
                f"  const container = document.getElementById('network-preview-{period}');",
                f"  const data = {{ nodes: new vis.DataSet({var_name}.nodes), edges: new vis.DataSet({var_name}.edges) }};",
                f"  const network = new vis.Network(container, data, previewOptions);",
                f"  network.once('stabilizationIterationsDone', function() {{",
                f"    network.setOptions({{ physics: false }});",
                f"    network.fit({{ animation: false }});",
                f"    network.moveTo({{ scale: 0.95 }});",
                f"  }});",
                f"}})();",
            ]
        )
    lines.extend(["</script>", "</div>", "</body></html>"])
    (html_dir / "index.html").write_text("\n".join(lines), encoding="utf-8")


def build_root_html_index(html_root: Path) -> None:
    entries = [
        ("Database", "database/index.html"),
        ("NeurIPS", "neurips/index.html"),
    ]
    lines = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8"><title>Topic Evolution Outputs</title></head><body>',
        "<h1>Topic Evolution Outputs</h1>",
        "<ul>",
    ]
    for label, href in entries:
        if (html_root / href).exists():
            lines.append(f'<li><a href="{href}">{label}</a></li>')
    lines.extend(["</ul>", "</body></html>"])
    (html_root / "index.html").write_text("\n".join(lines), encoding="utf-8")


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
    venue_keys: list[str],
    output_prefix: str,
) -> None:
    project_root = Path(__file__).resolve().parent.parent
    target_slug = infer_target_slug(venue_keys, output_prefix)
    paths = ensure_dirs(project_root, target_slug)
    periods = build_periods(period_start, period_end, period_size)
    title_prefix = infer_title_prefix(venue_keys)

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
        papers_df = fetch_all(start_year, end_year, venue_keys=venue_keys)
        papers_df.to_csv(raw_papers, index=False, encoding="utf-8")
        papers_df.to_csv(processed_papers, index=False, encoding="utf-8")

    allowed_venues = {normalize_venue_name(key) for key in venue_keys}
    if not papers_df.empty:
        papers_df["year"] = pd.to_numeric(papers_df["year"], errors="coerce")
        papers_df = papers_df.dropna(subset=["year"]).copy()
        papers_df["year"] = papers_df["year"].astype(int)
        papers_df = papers_df[papers_df["year"].between(start_year, end_year)].copy()
        venue_series = papers_df["venue"].map(normalize_venue_name)
        papers_df = papers_df[venue_series.isin(allowed_venues)].copy()

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
    save_graph_outputs(
        trend_df,
        burst_df,
        nodes_by_period,
        edges_by_period,
        paths["csv"],
        paths["gephi"],
    )

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
    build_index_html(paths["html"], paths["gephi"], periods, min_edge_weight, title_prefix=title_prefix)
    build_root_html_index(paths["html_root"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=DEFAULT_PERIOD_START)
    parser.add_argument("--end-year", type=int, default=DEFAULT_PERIOD_END)
    parser.add_argument("--min-edge-weight", type=int, default=1)
    parser.add_argument("--sankey-min-weight", type=int, default=2)
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--use-manual-raw", action="store_true")
    parser.add_argument("--manual-raw-file", action="append", default=[])
    parser.add_argument(
        "--venue-key",
        action="append",
        choices=sorted(DEFAULT_VENUE_KEYS + ["nips"]),
        default=None,
    )
    parser.add_argument("--output-prefix", default="")
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
        venue_keys=args.venue_key or DEFAULT_VENUE_KEYS.copy(),
        output_prefix=args.output_prefix,
    )


if __name__ == "__main__":
    main()
