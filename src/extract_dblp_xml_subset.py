from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from lxml import etree as ET


VENUE_BY_KEY_PREFIX = {
    "conf/sigmod/": "SIGMOD",
    "conf/vldb/": "VLDB",
    "journals/pvldb/": "PVLDB",
    "journals/pacmmod/": "PACMMOD",
    "conf/nips/": "NeurIPS",
}

VENUE_KEY_PREFIXES = {
    "sigmod": "conf/sigmod/",
    "vldb": "conf/vldb/",
    "pvldb": "journals/pvldb/",
    "pacmmod": "journals/pacmmod/",
    "nips": "conf/nips/",
}

OUTPUT_COLUMNS = ["title", "year", "venue", "authors", "dblp_url", "doi"]
START_RE = re.compile(r"<(article|inproceedings)\b[^>]*\bkey=\"([^\"]+)\"")
END_RE = re.compile(r"</(article|inproceedings)>")
DOI_RE = re.compile(r"(10\.\d{4,9}/\S+)")


def venue_from_key(key: str, allowed_prefixes: set[str] | None = None) -> str | None:
    for prefix, venue in VENUE_BY_KEY_PREFIX.items():
        if allowed_prefixes is not None and prefix not in allowed_prefixes:
            continue
        if key.startswith(prefix):
            return venue
    return None


def clean_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.split()).strip()


def rec_url(key: str) -> str:
    return f"https://dblp.org/rec/{key}"


def parse_block(xml_block: str, key: str, venue: str) -> dict[str, str] | None:
    parser = ET.XMLParser(recover=True, resolve_entities=False, huge_tree=False)
    elem = ET.fromstring(xml_block.encode("utf-8", errors="ignore"), parser=parser)
    if elem is None:
        return None

    title = ""
    year = ""
    authors: list[str] = []
    ees: list[str] = []

    for child in elem:
        child_tag = child.tag
        if child_tag == "title":
            title = clean_text("".join(child.itertext()))
        elif child_tag == "year":
            year = clean_text("".join(child.itertext()))
        elif child_tag == "author":
            author = clean_text("".join(child.itertext()))
            if author:
                authors.append(author)
        elif child_tag == "ee":
            ee = clean_text("".join(child.itertext()))
            if ee:
                ees.append(ee)

    if not title or not year.isdigit():
        return None

    doi = ""
    for ee in ees:
        match = DOI_RE.search(ee)
        if match:
            doi = match.group(1).rstrip(".,);")
            break

    return {
        "title": title,
        "year": year,
        "venue": venue,
        "authors": "; ".join(authors),
        "dblp_url": rec_url(key),
        "doi": doi,
    }


def extract_subset(
    xml_path: Path,
    output_csv: Path,
    start_year: int,
    end_year: int,
    venue_keys: list[str] | None = None,
    max_records: int | None = None,
    progress_every: int = 0,
) -> int:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    in_target_block = False
    target_end_tag = ""
    target_key = ""
    target_venue = ""
    block_lines: list[str] = []

    allowed_prefixes = None
    if venue_keys:
        allowed_prefixes = {VENUE_KEY_PREFIXES[key] for key in venue_keys}

    with xml_path.open("r", encoding="utf-8", errors="ignore") as source, output_csv.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        for line in source:
            if not in_target_block:
                match = START_RE.search(line)
                if not match:
                    continue

                tag_name, key = match.group(1), match.group(2)
                venue = venue_from_key(key, allowed_prefixes=allowed_prefixes)
                if venue is None:
                    continue

                in_target_block = True
                target_end_tag = f"</{tag_name}>"
                target_key = key
                target_venue = venue
                block_lines = [line]

                if target_end_tag in line:
                    xml_block = "".join(block_lines)
                    record = parse_block(xml_block, target_key, target_venue)
                    if record is not None:
                        year = int(record["year"])
                        if start_year <= year <= end_year:
                            writer.writerow(record)
                            count += 1
                            if progress_every and count % progress_every == 0:
                                handle.flush()
                                print(f"wrote {count} rows...", flush=True)
                            if max_records is not None and count >= max_records:
                                handle.flush()
                                return count
                    in_target_block = False
                    block_lines = []
                continue

            block_lines.append(line)
            if target_end_tag not in line:
                continue

            xml_block = "".join(block_lines)
            record = parse_block(xml_block, target_key, target_venue)
            if record is not None:
                year = int(record["year"])
                if start_year <= year <= end_year:
                    writer.writerow(record)
                    count += 1
                    if progress_every and count % progress_every == 0:
                        handle.flush()
                        print(f"wrote {count} rows...", flush=True)
                    if max_records is not None and count >= max_records:
                        handle.flush()
                        return count

            in_target_block = False
            block_lines = []

        handle.flush()

    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml-path", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument(
        "--venue-key",
        action="append",
        choices=sorted(VENUE_KEY_PREFIXES),
        default=None,
    )
    parser.add_argument("--max-records", type=int)
    parser.add_argument("--progress-every", type=int, default=0)
    args = parser.parse_args()

    count = extract_subset(
        xml_path=Path(args.xml_path),
        output_csv=Path(args.output),
        start_year=args.start_year,
        end_year=args.end_year,
        venue_keys=args.venue_key or ["sigmod", "vldb", "pvldb", "pacmmod"],
        max_records=args.max_records,
        progress_every=args.progress_every,
    )
    print(f"wrote {count} rows")


if __name__ == "__main__":
    main()
