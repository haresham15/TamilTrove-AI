"""Dependency-free smoke checks for a deployed TamilTrove V2 API."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Any


def request_json(url: str, body: dict[str, Any] | None = None, timeout: float = 15) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"{url} returned HTTP {response.status}")
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"{url} returned HTTP {error.code}: {detail}") from error


def request_html(url: str, timeout: float = 15) -> None:
    request = urllib.request.Request(
        url,
        headers={"Accept": "text/html", "User-Agent": "tamiltrove-smoke/2"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            body = response.read(262_144).decode("utf-8", errors="replace").casefold()
            require(response.status == 200, f"{url} returned HTTP {response.status}")
            require(content_type == "text/html", f"{url} did not return HTML")
            require("<html" in body and "tamiltrove" in body, f"{url} did not render TamilTrove")
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{url} returned HTTP {error.code}") from error


def require(condition: Any, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--web-url")
    parser.add_argument("--expected-ranking-version")
    parser.add_argument("--ready-timeout", type=float, default=90)
    args = parser.parse_args()
    base_url = args.api_url.rstrip("/")

    health = request_json(f"{base_url}/health")
    require(health.get("status") in {"ok", "healthy"}, "process health check failed")

    deadline = time.monotonic() + args.ready_timeout
    readiness: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            readiness = request_json(f"{base_url}/ready", timeout=5)
            if readiness.get("ready") is True or readiness.get("status") == "ready":
                break
        except (OSError, RuntimeError):
            pass
        time.sleep(2)
    else:
        raise RuntimeError(f"service did not become ready: {readiness}")

    discovery = request_json(
        f"{base_url}/api/v1/search",
        {"query": "", "filters": {}, "page": 1, "page_size": 5},
        timeout=30,
    )
    require(isinstance(discovery.get("results"), list), "search results must be a list")
    meta = discovery.get("meta", {})
    require(meta.get("request_id"), "search response is missing request_id")
    require(meta.get("ranking_version"), "search response is missing ranking_version")
    if args.expected_ranking_version:
        require(
            meta.get("ranking_version") == args.expected_ranking_version,
            (
                "active ranking version does not match deployment intent: "
                f"expected {args.expected_ranking_version}, got {meta.get('ranking_version')}"
            ),
        )
    require(discovery["results"], "empty-query discovery returned no movies")
    for result in discovery["results"]:
        explanation = result.get("explanation", {})
        require(explanation.get("summary"), "result is missing an explanation summary")
        require(isinstance(explanation.get("evidence"), list), "explanation evidence must be a list")

    multilingual = request_json(
        f"{base_url}/api/v1/search",
        {"query": "Kaithi maari one night action thriller", "filters": {}, "page": 1, "page_size": 5},
        timeout=30,
    )
    require(multilingual.get("detected_language") in {"tanglish", "mixed", "en"}, "language detection missing")
    require(multilingual.get("results"), "Tanglish smoke query returned no results")
    if args.web_url:
        request_html(args.web_url.rstrip("/"), timeout=30)
    print(f"Smoke checks passed for {base_url} ({meta['ranking_version']})")


if __name__ == "__main__":
    main()
