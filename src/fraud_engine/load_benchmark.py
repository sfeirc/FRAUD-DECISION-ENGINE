from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
import numpy as np

from fraud_engine.benchmark import environment_metadata


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _payload(level: int, index: int) -> dict[str, object]:
    return {
        "transaction_id": f"load-c{level}-{index}",
        "trace_id": f"trace-load-c{level}-{index}",
        "event_time": datetime(2026, 8, 1, 12, index % 60, tzinfo=UTC).isoformat(),
        "customer_id": f"load-customer-{level}-{index}",
        "card_id": f"load-card-{level}-{index}",
        "merchant_id": f"load-merchant-{index % 40}",
        "amount": 15.0 + index % 300,
        "currency": "EUR",
        "country": "FR",
        "ip_address": f"10.{level}.{index // 250}.{index % 250 + 1}",
        "device_id": f"load-device-{level}-{index}",
        "merchant_category": "electronics" if index % 7 == 0 else "grocery",
        "authentication_method": "3ds",
        "authentication_successful": True,
        "latitude": 48.8566,
        "longitude": 2.3522,
    }


async def _send_batch(
    base_url: str, *, concurrency: int, requests: int, start_index: int
) -> tuple[list[dict[str, object]], float]:
    semaphore = asyncio.Semaphore(concurrency)
    timeout = httpx.Timeout(30.0)
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:

        async def send(index: int) -> dict[str, object]:
            async with semaphore:
                started = time.perf_counter_ns()
                response = await client.post(
                    f"{base_url}/v1/payments/authorize",
                    json=_payload(concurrency, start_index + index),
                )
                latency_ms = (time.perf_counter_ns() - started) / 1_000_000
                body: dict[str, Any] = {}
                if response.headers.get("content-type", "").startswith("application/json"):
                    body = response.json()
                return {
                    "concurrency": concurrency,
                    "request_index": index,
                    "status_code": response.status_code,
                    "client_latency_ms": latency_ms,
                    "server_decision_latency_ms": body.get("latency_ms", ""),
                    "decision": body.get("decision", ""),
                }

        started = time.perf_counter()
        rows = await asyncio.gather(*(send(index) for index in range(requests)))
        elapsed = time.perf_counter() - started
    return rows, elapsed


def _wait_until_ready(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"benchmark server exited during startup: {output}")
        try:
            if httpx.get(f"{base_url}/v1/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError("benchmark server did not become healthy within 30 seconds")


def _run_level(
    concurrency: int, requests: int, warmup: int
) -> tuple[list[dict[str, object]], float]:
    port = _available_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="fraud-load-") as temporary:
        environment = os.environ.copy()
        environment["FRAUD_DATABASE_PATH"] = str(Path(temporary) / "load.sqlite3")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "fraud_engine.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_until_ready(base_url, process)
            asyncio.run(
                _send_batch(
                    base_url,
                    concurrency=concurrency,
                    requests=warmup,
                    start_index=1_000_000,
                )
            )
            return asyncio.run(
                _send_batch(
                    base_url,
                    concurrency=concurrency,
                    requests=requests,
                    start_index=0,
                )
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def summarize_level(
    rows: list[dict[str, object]], elapsed_seconds: float
) -> dict[str, float | int]:
    successful = [row for row in rows if row["status_code"] == 200]
    latencies = np.asarray([float(cast(Any, row["client_latency_ms"])) for row in successful])
    return {
        "requests": len(rows),
        "successful_requests": len(successful),
        "errors": len(rows) - len(successful),
        "elapsed_seconds": elapsed_seconds,
        "throughput_requests_per_second": len(successful) / elapsed_seconds,
        "client_latency_ms_p50": float(np.percentile(latencies, 50)),
        "client_latency_ms_p95": float(np.percentile(latencies, 95)),
        "client_latency_ms_p99": float(np.percentile(latencies, 99)),
    }


def _load_svg(levels: dict[int, dict[str, float | int]], output: Path) -> None:
    maximum_throughput = max(
        float(row["throughput_requests_per_second"]) for row in levels.values()
    )
    maximum_p99 = max(float(row["client_latency_ms_p99"]) for row in levels.values())
    blocks = []
    for index, (concurrency, row) in enumerate(levels.items()):
        x = 95 + index * 145
        throughput = float(row["throughput_requests_per_second"])
        p99 = float(row["client_latency_ms_p99"])
        throughput_height = 145 * throughput / maximum_throughput
        latency_height = 145 * p99 / maximum_p99
        blocks.append(
            f'<rect x="{x}" y="{230 - throughput_height:.1f}" width="42" '
            f'height="{throughput_height:.1f}" fill="#34d6c6"/>'
            f'<rect x="{x + 45}" y="{230 - latency_height:.1f}" width="42" '
            f'height="{latency_height:.1f}" fill="#f7b955"/>'
            f'<text x="{x + 15}" y="254" fill="#c9d8e8" font-size="12">c{concurrency}</text>'
            f'<text x="{x - 5}" y="{70 - throughput_height / 10:.1f}" '
            f'fill="#34d6c6" font-size="10">{throughput:.1f}/s</text>'
            f'<text x="{x + 43}" y="{82 - latency_height / 10:.1f}" '
            f'fill="#f7b955" font-size="10">{p99:.1f}ms</text>'
        )
    output.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="300" '
        'viewBox="0 0 720 300"><rect width="100%" height="100%" fill="#0d1b2d"/>'
        '<text x="20" y="28" fill="#e8f0f8" font-size="17" font-weight="700">'
        "Loopback HTTP concurrency benchmark</text>"
        '<rect x="445" y="18" width="12" height="12" fill="#34d6c6"/>'
        '<text x="462" y="28" fill="#c9d8e8" font-size="11">throughput</text>'
        '<rect x="550" y="18" width="12" height="12" fill="#f7b955"/>'
        '<text x="567" y="28" fill="#c9d8e8" font-size="11">p99 latency</text>'
        + "".join(blocks)
        + '<text x="20" y="285" fill="#8fa7bf" font-size="11">'
        + "Fresh single-worker process per level; SQLite FULL sync; client and server on one host."
        + "</text></svg>",
        encoding="utf-8",
    )


def run_load_benchmark(
    output_dir: Path,
    *,
    concurrency_levels: list[int],
    requests_per_level: int = 100,
    warmup_requests: int = 10,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, object]] = []
    measurements: dict[int, dict[str, float | int]] = {}
    for concurrency in concurrency_levels:
        rows, elapsed = _run_level(concurrency, requests_per_level, warmup_requests)
        all_rows.extend(rows)
        measurements[concurrency] = summarize_level(rows, elapsed)
    summary: dict[str, object] = {
        **environment_metadata(),
        "configuration": {
            "concurrency_levels": concurrency_levels,
            "requests_per_level": requests_per_level,
            "warmup_requests": warmup_requests,
            "server": "one uvicorn worker; fresh process and SQLite database per level",
            "client": "async HTTP/1.1 over loopback with connection pooling",
            "durability": "SQLite WAL with synchronous=FULL",
            "scope": (
                "includes HTTP parsing/serialization, scheduling, temporal and graph state, "
                "champion/challenger inference, explanation, and durable journal write; "
                "excludes remote network, TLS, proxy, and container overhead"
            ),
        },
        "measurements": {str(key): value for key, value in measurements.items()},
    }
    with (output_dir / "raw_requests.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    _load_svg(measurements, output_dir / "http_load.svg")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the complete HTTP authorization path")
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks/results/http-load"))
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 4, 8, 16])
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=10)
    args = parser.parse_args()
    summary = run_load_benchmark(
        args.output_dir,
        concurrency_levels=args.concurrency,
        requests_per_level=args.requests,
        warmup_requests=args.warmup,
    )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
