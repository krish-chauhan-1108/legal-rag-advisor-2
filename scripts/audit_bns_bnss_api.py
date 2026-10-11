"""Sequentially audit every BNS and BNSS section through TRANA's test API.

Set TRANA_TEST_API_TOKEN in the environment before running. The script never
prints or writes the token. Rows are flushed after each completed API request,
so an interrupted audit can be continued with --resume.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


DEFAULT_ENDPOINT = "https://legal-rag-advisor-api.onrender.com/__test/analyze"
FIELDS = (
    "act",
    "section",
    "query",
    "http_status",
    "answer",
    "applicable_laws_json",
    "sources_json",
    "requested_citation_present",
    "verified_source_present",
    "model_used",
    "processing_time_seconds",
    "error",
    "checked_at_utc",
)
SECTION_COUNTS = {"BNS": 358, "BNSS": 531}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ask the test API to explain every BNS and BNSS section, one at a "
            "time, and save the answers and verified source text to CSV."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("bns_bnss_audit.csv"),
        help="CSV output path (default: bns_bnss_audit.csv)",
    )
    parser.add_argument(
        "--endpoint",
        default=os.getenv("TRANA_TEST_API_URL", DEFAULT_ENDPOINT),
        help="Test endpoint URL (or set TRANA_TEST_API_URL)",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=3.0,
        help="Pause between requests (default: 3 seconds; requests stay sequential)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=75.0,
        help="Per-request timeout (default: 75 seconds)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=4,
        help="Retries for network errors, HTTP 429, and HTTP 5xx (default: 4)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Append to an existing CSV and skip sections already answered with HTTP 200",
    )
    args = parser.parse_args()
    if args.delay_seconds < 0 or args.timeout_seconds <= 0 or args.retries < 0:
        parser.error("delay must be nonnegative; timeout must be positive; retries must be nonnegative")
    return args


def load_completed(output_path: Path) -> set[tuple[str, str]]:
    if not output_path.exists():
        return set()
    completed: set[tuple[str, str]] = set()
    with output_path.open("r", newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            if row.get("http_status") == "200":
                completed.add((row.get("act", ""), row.get("section", "")))
    return completed


def json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def response_row(
    act: str,
    section: str,
    query: str,
    status: int | str,
    payload: dict[str, Any] | None,
    error: str = "",
) -> dict[str, str]:
    payload = payload or {}
    analysis = payload.get("analysis") or {}
    laws = analysis.get("applicable_laws") or []
    sources = payload.get("sources") or []
    citation_present = any(
        str(law.get("code", "")).upper() == act
        and str(law.get("section", "")) == section
        and bool(law.get("verified"))
        for law in laws
    )
    verified_source_present = any(
        str(source.get("code", "")).upper() == act
        and str(source.get("section", "")) == section
        and bool(source.get("verified"))
        for source in sources
    )
    return {
        "act": act,
        "section": section,
        "query": query,
        "http_status": str(status),
        "answer": str(analysis.get("general_analysis") or ""),
        "applicable_laws_json": json_cell(laws),
        "sources_json": json_cell(sources),
        "requested_citation_present": str(citation_present).lower(),
        "verified_source_present": str(verified_source_present).lower(),
        "model_used": str(payload.get("model_used") or ""),
        "processing_time_seconds": str(payload.get("processing_time_seconds") or ""),
        "error": error,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


async def request_one(
    client: httpx.AsyncClient,
    endpoint: str,
    token: str,
    act: str,
    section: str,
    retries: int,
) -> dict[str, str]:
    query = f"Explain {act} Section {section} in simple language."
    payload = {"query": query}
    last_error = ""

    for attempt in range(retries + 1):
        try:
            response = await client.post(
                endpoint,
                headers={"X-Test-Token": token},
                json=payload,
            )
            try:
                body = response.json()
            except ValueError:
                body = {}

            if response.status_code == 200:
                return response_row(act, str(section), query, 200, body)

            last_error = str(body.get("detail") or response.text[:500])
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt >= retries:
                return response_row(
                    act, str(section), query, response.status_code, body, last_error
                )

            retry_after = response.headers.get("Retry-After", "")
            try:
                wait_seconds = max(1.0, float(retry_after))
            except ValueError:
                wait_seconds = min(60.0, 2.0 ** attempt)
        except httpx.RequestError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt >= retries:
                return response_row(act, str(section), query, "network_error", None, last_error)
            wait_seconds = min(60.0, 2.0 ** attempt)

        print(
            f"Retrying {act} {section} after a transient error "
            f"({attempt + 1}/{retries}); waiting {wait_seconds:.0f}s.",
            file=sys.stderr,
        )
        await asyncio.sleep(wait_seconds)

    return response_row(act, str(section), query, "network_error", None, last_error)


async def run(args: argparse.Namespace) -> int:
    token = os.getenv("TRANA_TEST_API_TOKEN", "")
    if len(token) < 32:
        print(
            "Set TRANA_TEST_API_TOKEN to the same 32+ character token configured "
            "on the backend. The token is not read from a command-line argument.",
            file=sys.stderr,
        )
        return 2

    if args.output.exists() and not args.resume:
        print(
            f"{args.output} already exists. Choose another --output path or pass --resume.",
            file=sys.stderr,
        )
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = load_completed(args.output) if args.resume else set()
    todo = [
        (act, number)
        for act, maximum in SECTION_COUNTS.items()
        for number in range(1, maximum + 1)
        if (act, str(number)) not in completed
    ]
    if not todo:
        print("All BNS and BNSS sections already have successful rows.")
        return 0

    is_new = not args.output.exists() or args.output.stat().st_size == 0
    mode = "a" if args.resume else "w"
    delay_floor = max(0, len(todo) - 1) * args.delay_seconds
    print(
        f"Starting {len(todo)} sequential requests; delay alone is about "
        f"{delay_floor / 60:.1f} minutes. Output: {args.output}"
    )

    with args.output.open(mode, newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
            output.flush()

        timeout = httpx.Timeout(args.timeout_seconds, connect=20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for index, (act, section_number) in enumerate(todo, start=1):
                section = str(section_number)
                row = await request_one(
                    client,
                    args.endpoint,
                    token,
                    act,
                    section,
                    args.retries,
                )
                writer.writerow(row)
                output.flush()

                print(
                    f"[{index}/{len(todo)}] {act} {section}: "
                    f"HTTP {row['http_status']} | "
                    f"citation={row['requested_citation_present']} | "
                    f"source={row['verified_source_present']}"
                )
                if row["http_status"] == "404":
                    print(
                        "The test endpoint is disabled or the test token is invalid. "
                        "Check TRANA_TEST_API_TOKEN and the deployed backend, then retry.",
                        file=sys.stderr,
                    )
                    return 1
                if row["http_status"].isdigit() and 400 <= int(row["http_status"]) < 500:
                    print(
                        f"Stopping on non-retryable HTTP {row['http_status']}; "
                        "inspect the last CSV row before resuming.",
                        file=sys.stderr,
                    )
                    return 1
                if index < len(todo) and args.delay_seconds:
                    await asyncio.sleep(args.delay_seconds)

    print(f"Finished. CSV saved to {args.output}")
    return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Interrupted. Completed rows were flushed; rerun with --resume.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
