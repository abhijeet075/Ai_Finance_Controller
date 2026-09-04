"""Dependency-light API performance smoke test."""
from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen


def hit(url: str, api_key: str | None) -> tuple[float, int]:
    headers = {"X-API-Key": api_key} if api_key else {}
    started = time.perf_counter()
    with urlopen(Request(url, headers=headers), timeout=10) as response:
        response.read()
        status = response.status
    return (time.perf_counter() - started) * 1000, status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url", default="http://localhost:8000/api/health"
    )
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--api-key")
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        rows = list(
            pool.map(
                lambda _: hit(args.url, args.api_key),
                range(args.requests),
            )
        )
    times = sorted(row[0] for row in rows)
    p95_index = max(0, int(len(times) * 0.95) - 1)
    result = {
        "requests": len(rows),
        "successes": sum(row[1] < 400 for row in rows),
        "p50_ms": round(statistics.median(times), 2),
        "p95_ms": round(times[p95_index], 2),
        "max_ms": round(max(times), 2),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
