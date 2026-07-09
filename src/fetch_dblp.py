from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm


VENUE_QUERIES = {
    "sigmod": {
        "query": "stream:conf/sigmod:",
        "url_prefixes": ["https://dblp.org/rec/conf/sigmod/"],
        "label": "SIGMOD",
    },
    "vldb": {
        "query": "stream:conf/vldb:",
        "url_prefixes": ["https://dblp.org/rec/conf/vldb/"],
        "label": "VLDB",
    },
    "pvldb": {
        "query": "stream:journals/pvldb:",
        "url_prefixes": ["https://dblp.org/rec/journals/pvldb/"],
        "label": "PVLDB",
    },
    "pacmmod": {
        "query": "stream:journals/pacmmod:",
        "url_prefixes": ["https://dblp.org/rec/journals/pacmmod/"],
        "label": "PACMMOD",
    },
    "nips": {
        "query": "stream:conf/nips:",
        "url_prefixes": ["https://dblp.org/rec/conf/nips/"],
        "label": "NeurIPS",
    },
}

DEFAULT_VENUE_KEYS = ["sigmod", "vldb", "pvldb", "pacmmod"]

PAPERS_COLUMNS = ["paper_id", "title", "year", "venue", "authors", "dblp_url", "doi"]
RAW_REQUIRED_COLUMNS = ["title", "year", "venue"]

REQUEST_HEADERS = {
    "User-Agent": "vldb-sigmod-topic-evolution/1.0 (research prototype)",
}


def fetch_dblp_query(
    session: requests.Session,
    query: str,
    start: int,
    limit: int = 200,
    max_retries: int = 6,
) -> list[dict]:
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = session.get(
                "https://dblp.org/search/publ/api",
                params={"q": query, "h": limit, "f": start, "format": "json"},
                headers=REQUEST_HEADERS,
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            hits = payload.get("result", {}).get("hits", {}).get("hit", [])
            if isinstance(hits, dict):
                hits = [hits]
            return hits
        except requests.RequestException as exc:
            last_error = exc
            if attempt == max_retries - 1:
                break
            time.sleep(min(2**attempt, 20))
    if last_error is not None:
        raise last_error
    return []


def normalize_authors(hit_info: dict) -> str:
    authors = hit_info.get("authors", {}).get("author", [])
    if isinstance(authors, dict):
        authors = [authors]
    names = []
    for author in authors:
        if isinstance(author, dict):
            names.append(str(author.get("text") or author.get("@pid") or "").strip())
        else:
            names.append(str(author).strip())
    return "; ".join(name for name in names if name)


def should_skip_title(title: str) -> bool:
    normalized = title.lower()
    skip_phrases = [
        "proceedings of",
        "companion of",
        "industrial track",
        "tutorial",
        "panel",
        "demonstration",
        "demo:",
        "phd symposium",
    ]
    return any(phrase in normalized for phrase in skip_phrases)


def cache_path(cache_dir: Path, venue_key: str, year: int) -> Path:
    return cache_dir / f"{venue_key}_{year}.csv"


def empty_papers_df() -> pd.DataFrame:
    return pd.DataFrame(columns=PAPERS_COLUMNS)


def year_rows_to_df(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["title", "year", "venue", "authors", "dblp_url", "doi"])


def normalize_manual_papers(df: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in RAW_REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in manual raw data: {missing}")

    normalized = df.copy()
    for optional in ["authors", "dblp_url", "doi"]:
        if optional not in normalized.columns:
            normalized[optional] = ""

    normalized["title"] = normalized["title"].astype(str).str.strip()
    normalized["venue"] = normalized["venue"].astype(str).str.strip()
    normalized["year"] = pd.to_numeric(normalized["year"], errors="coerce")
    normalized = normalized.dropna(subset=["year"])
    normalized["year"] = normalized["year"].astype(int)
    normalized = normalized[normalized["title"] != ""]
    normalized = normalized.drop_duplicates(subset=["title", "year", "venue"])
    return assign_paper_ids(normalized[["title", "year", "venue", "authors", "dblp_url", "doi"]])


def load_manual_papers(manual_dir: Path, start_year: int, end_year: int) -> pd.DataFrame:
    csv_paths = sorted(manual_dir.glob("*.csv"))
    if not csv_paths:
        return empty_papers_df()

    frames: list[pd.DataFrame] = []
    for csv_path in csv_paths:
        frame = pd.read_csv(csv_path)
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    normalized = normalize_manual_papers(combined)
    filtered = normalized[normalized["year"].between(start_year, end_year)].copy()
    if filtered.empty:
        return empty_papers_df()
    return filtered.reset_index(drop=True)


def load_manual_papers_from_files(csv_paths: list[Path], start_year: int, end_year: int) -> pd.DataFrame:
    existing_paths = [path for path in csv_paths if path.exists()]
    if not existing_paths:
        return empty_papers_df()

    frames: list[pd.DataFrame] = []
    for csv_path in existing_paths:
        frames.append(pd.read_csv(csv_path))

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    normalized = normalize_manual_papers(combined)
    filtered = normalized[normalized["year"].between(start_year, end_year)].copy()
    if filtered.empty:
        return empty_papers_df()
    return filtered.reset_index(drop=True)


def collect_year_papers(
    session: requests.Session,
    venue_key: str,
    year: int,
) -> list[dict[str, object]]:
    config = VENUE_QUERIES[venue_key]
    all_rows: list[dict[str, object]] = []
    offset = 0
    query = f"{config['query']} {year}"

    while True:
        hits = fetch_dblp_query(session, query, offset)
        if not hits:
            break

        year_hits = 0
        for hit in hits:
            info = hit.get("info", {})
            year_text = str(info.get("year", "")).strip()
            if not year_text.isdigit():
                continue
            hit_year = int(year_text)
            if hit_year != year:
                continue
            year_hits += 1

            url = str(info.get("url", "")).strip()
            if config["url_prefixes"] and not any(url.startswith(prefix) for prefix in config["url_prefixes"]):
                continue

            title = str(info.get("title", "")).strip()
            if not title or should_skip_title(title):
                continue

            all_rows.append(
                {
                    "title": title,
                    "year": hit_year,
                    "venue": config["label"],
                    "authors": normalize_authors(info),
                    "dblp_url": url,
                    "doi": str(info.get("doi", "")).strip(),
                }
            )

        offset += len(hits)
        if len(hits) < 200 or year_hits == 0:
            break
        time.sleep(0.4)

    return all_rows


def collect_venue_papers(
    session: requests.Session,
    venue_key: str,
    start_year: int,
    end_year: int,
    cache_dir: Path,
) -> list[dict[str, object]]:
    all_rows: list[dict[str, object]] = []

    for year in range(start_year, end_year + 1):
        year_cache = cache_path(cache_dir, venue_key, year)
        if year_cache.exists():
            cached_df = pd.read_csv(year_cache)
            all_rows.extend(cached_df.to_dict("records"))
            continue

        try:
            year_rows = collect_year_papers(session, venue_key, year)
        except requests.RequestException:
            continue

        year_df = year_rows_to_df(year_rows).drop_duplicates(subset=["title", "year", "venue"])
        year_cache.parent.mkdir(parents=True, exist_ok=True)
        year_df.to_csv(year_cache, index=False, encoding="utf-8")
        all_rows.extend(year_df.to_dict("records"))
        time.sleep(0.6)

    return all_rows


def assign_paper_ids(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (venue, year), group in df.sort_values(["venue", "year", "title"]).groupby(["venue", "year"]):
        prefix = venue.lower()
        for index, row in enumerate(group.to_dict("records"), start=1):
            row["paper_id"] = f"{prefix}_{year}_{index:04d}"
            rows.append(row)
    return pd.DataFrame(rows)[["paper_id", "title", "year", "venue", "authors", "dblp_url", "doi"]]


def fetch_all(
    start_year: int,
    end_year: int,
    cache_dir: Path | None = None,
    venue_keys: list[str] | None = None,
) -> pd.DataFrame:
    cache_dir = cache_dir or Path("data/raw/dblp_cache")
    venue_keys = venue_keys or DEFAULT_VENUE_KEYS
    collected: list[dict[str, object]] = []
    with requests.Session() as session:
        for venue_key in tqdm(venue_keys, desc="Fetching DBLP venues"):
            collected.extend(collect_venue_papers(session, venue_key, start_year, end_year, cache_dir))

    df = pd.DataFrame(collected).drop_duplicates(subset=["title", "year", "venue"])
    if df.empty:
        return empty_papers_df()
    return assign_paper_ids(df)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--venue-key",
        action="append",
        choices=sorted(VENUE_QUERIES),
        default=None,
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    df = fetch_all(
        args.start_year,
        args.end_year,
        output_path.parent.parent / "raw" / "dblp_cache",
        venue_keys=args.venue_key or DEFAULT_VENUE_KEYS.copy(),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8")


if __name__ == "__main__":
    main()
