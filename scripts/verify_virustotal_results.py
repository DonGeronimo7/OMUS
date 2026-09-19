#!/usr/bin/env python3
"""Wait for VirusTotal analyses and render conservative release evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen


API_ROOT = "https://www.virustotal.com/api/v3"
POLL_SECONDS = 15
MAX_POLLS = 60


def _get_json(path: str, api_key: str) -> dict:
    request = Request(
        f"{API_ROOT}/{path}",
        headers={"accept": "application/json", "x-apikey": api_key},
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS API root
        return json.load(response)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wait_for_results(results: list[dict], api_key: str) -> list[dict]:
    completed = []
    for result in results:
        analysis_id = result["id"]
        for attempt in range(MAX_POLLS):
            analysis = _get_json(f"analyses/{analysis_id}", api_key)["data"]
            attributes = analysis.get("attributes", {})
            if attributes.get("status") == "completed":
                stats = attributes.get("stats", {})
                completed.append({
                    "name": result["name"],
                    "sha256": result.get("sha256", ""),
                    "link": result["link"],
                    "malicious": int(stats.get("malicious", 0)),
                    "suspicious": int(stats.get("suspicious", 0)),
                    "undetected": int(stats.get("undetected", 0)),
                })
                break
            if attempt + 1 == MAX_POLLS:
                raise TimeoutError(f"VirusTotal analysis did not complete: {result['name']}")
            time.sleep(POLL_SECONDS)
    return completed


def render_markdown(results: list[dict]) -> str:
    lines = [
        "<!-- virustotal-results:start -->",
        "## VirusTotal analysis",
        "",
        "VirusTotal scanned the five primary distributable artifacts. Results are a point-in-time signal, not a certification of safety.",
        "",
        "| Artifact | SHA-256 | Result at scan time | Analysis |",
        "| --- | --- | --- | --- |",
    ]
    for result in sorted(results, key=lambda item: item["name"]):
        detections = result["malicious"] + result["suspicious"]
        wording = (
            "0 detections at scan time"
            if detections == 0
            else f"{result['malicious']} malicious, {result['suspicious']} suspicious"
        )
        lines.append(
            f"| `{result['name']}` | `{result['sha256']}` | {wording} | [VirusTotal analysis]({result['link']}) |"
        )
    lines.extend(["", "<!-- virustotal-results:end -->", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path, default=Path("scan-assets"))
    args = parser.parse_args()
    api_key = os.environ["VT_API_KEY"]
    submitted = json.loads(os.environ["VT_RESULTS_JSON"])
    if len(submitted) != 5:
        raise ValueError(f"expected exactly 5 VirusTotal submissions, found {len(submitted)}")
    for result in submitted:
        expected = _sha256(args.asset_dir / result["name"])
        if result.get("sha256") != expected:
            raise ValueError(f"SHA-256 mismatch for {result['name']}")
    completed = wait_for_results(submitted, api_key)
    args.output.write_text(render_markdown(completed), encoding="utf-8")
    has_detections = any(item["malicious"] or item["suspicious"] for item in completed)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(summary).write_text(render_markdown(completed), encoding="utf-8")
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"has-detections={str(has_detections).lower()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
