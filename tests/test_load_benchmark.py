from fraud_engine.load_benchmark import run_load_benchmark, summarize_level


def test_load_summary_reports_errors_throughput_and_tail_latency() -> None:
    rows = [
        {"status_code": 200, "client_latency_ms": 10.0},
        {"status_code": 200, "client_latency_ms": 20.0},
        {"status_code": 500, "client_latency_ms": 30.0},
    ]
    summary = summarize_level(rows, elapsed_seconds=0.5)
    assert summary["successful_requests"] == 2
    assert summary["errors"] == 1
    assert summary["throughput_requests_per_second"] == 4.0
    assert summary["client_latency_ms_p99"] > summary["client_latency_ms_p50"]


def test_http_load_benchmark_exercises_real_server_and_writes_evidence(tmp_path) -> None:
    summary = run_load_benchmark(
        tmp_path,
        concurrency_levels=[1],
        requests_per_level=2,
        warmup_requests=1,
    )
    measurement = summary["measurements"]["1"]
    assert measurement["successful_requests"] == 2
    assert measurement["errors"] == 0
    assert (tmp_path / "raw_requests.csv").is_file()
    assert (tmp_path / "summary.json").is_file()
    assert (tmp_path / "http_load.svg").is_file()
