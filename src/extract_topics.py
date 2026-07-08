from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from periods import DEFAULT_PERIOD_END, DEFAULT_PERIOD_SIZE, DEFAULT_PERIOD_START, period_of
from topic_dictionary import GENERIC_TERMS, TOPIC_DICT

TAGGED_COLUMNS = [
    "paper_id",
    "title",
    "year",
    "venue",
    "topic",
    "category",
    "matched_keyword",
    "period",
]
UNTAGGED_COLUMNS = ["paper_id", "title", "year", "venue", "authors", "dblp_url", "doi"]


def normalize_text(text: str) -> str:
    lowered = str(text).lower()
    return re.sub(r"\s+", " ", lowered).strip()


def keyword_matches(normalized_title: str, keyword: str) -> bool:
    keyword = normalize_text(keyword)
    if keyword in GENERIC_TERMS:
        return False
    if " " in keyword or "-" in keyword or "/" in keyword:
        return keyword in normalized_title
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", normalized_title) is not None


def match_topics(title: str) -> list[dict[str, str]]:
    normalized_title = normalize_text(title)
    matches: list[dict[str, str]] = []
    for topic, config in TOPIC_DICT.items():
        matched_keyword = next(
            (keyword for keyword in config["keywords"] if keyword_matches(normalized_title, keyword)),
            None,
        )
        if matched_keyword is not None:
            matches.append(
                {
                    "topic": topic,
                    "category": config["category"],
                    "matched_keyword": matched_keyword,
                }
            )
    return matches


def tag_papers(
    papers_df: pd.DataFrame,
    period_start: int = DEFAULT_PERIOD_START,
    period_end: int = DEFAULT_PERIOD_END,
    period_size: int = DEFAULT_PERIOD_SIZE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    tagged_rows: list[dict[str, object]] = []
    untagged_rows: list[dict[str, object]] = []

    for row in papers_df.to_dict("records"):
        matches = match_topics(row["title"])
        if not matches:
            untagged_rows.append(row)
            continue

        for match in matches:
            tagged_rows.append(
                {
                    "paper_id": row["paper_id"],
                    "title": row["title"],
                    "year": row["year"],
                    "venue": row["venue"],
                    "topic": match["topic"],
                    "category": match["category"],
                    "matched_keyword": match["matched_keyword"],
                    "period": period_of(int(row["year"]), period_start, period_end, period_size),
                }
            )

    return (
        pd.DataFrame(tagged_rows, columns=TAGGED_COLUMNS),
        pd.DataFrame(untagged_rows, columns=UNTAGGED_COLUMNS),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--untagged-output", required=True)
    parser.add_argument("--period-start", type=int, default=DEFAULT_PERIOD_START)
    parser.add_argument("--period-end", type=int, default=DEFAULT_PERIOD_END)
    parser.add_argument("--period-size", type=int, default=DEFAULT_PERIOD_SIZE)
    args = parser.parse_args()

    papers_df = pd.read_csv(args.input)
    tagged_df, untagged_df = tag_papers(
        papers_df,
        period_start=args.period_start,
        period_end=args.period_end,
        period_size=args.period_size,
    )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    tagged_df.to_csv(args.output, index=False, encoding="utf-8")
    untagged_df.to_csv(args.untagged_output, index=False, encoding="utf-8")


if __name__ == "__main__":
    main()
