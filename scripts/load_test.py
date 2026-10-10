"""课程注册系统的轻量并发与延迟测试，不依赖第三方压测工具。

密码只从 LOAD_TEST_PASSWORD 环境变量读取。示例：
  LOAD_TEST_USERNAME=student1 LOAD_TEST_PASSWORD='...' \
    python -m scripts.load_test --path '/api/catalog/offerings?term_code=2026FA'
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import os
import statistics
import sys
import threading
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def _json_request(url: str, *, method: str = "GET", body: dict | None = None,
                  token: str = "", timeout: float = 130) -> tuple[int, bytes]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def _login(base_url: str, username: str, password: str, timeout: float) -> str:
    status, raw = _json_request(
        urljoin(base_url, "/api/auth/login"), method="POST",
        body={"username": username, "password": password}, timeout=timeout,
    )
    if status != 200:
        raise RuntimeError(f"登录失败（HTTP {status}）")
    return json.loads(raw)["access_token"]


def _percentile(values: list[float], percent: int) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percent / 100) - 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description="课程注册系统并发与延迟测试")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--path", default="/api/catalog/offerings?term_code=2026FA")
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=130)
    parser.add_argument("--max-p80", type=float, default=120,
                        help="80%% 请求的最大允许秒数，默认 120")
    parser.add_argument("--max-response", type=float, default=10,
                        help="单次请求最大允许秒数，课程目录默认 10")
    parser.add_argument("--anonymous", action="store_true",
                        help="测试无需登录的路径，例如 /health/live")
    args = parser.parse_args()
    if not 1 <= args.concurrency <= 2000:
        parser.error("--concurrency 必须在 1–2000 之间")
    if not 1 <= args.requests <= 100000:
        parser.error("--requests 必须在 1–100000 之间")

    token = os.getenv("LOAD_TEST_TOKEN", "")
    if not args.anonymous and not token:
        username = os.getenv("LOAD_TEST_USERNAME", "")
        password = os.getenv("LOAD_TEST_PASSWORD", "")
        if not username or not password:
            parser.error("请设置 LOAD_TEST_USERNAME 和 LOAD_TEST_PASSWORD，或 LOAD_TEST_TOKEN")
        token = _login(args.base_url, username, password, args.timeout)

    target = urljoin(args.base_url, args.path)
    start_gate = threading.Event()

    def hit(_: int) -> tuple[int, float, str]:
        start_gate.wait()
        started = perf_counter()
        try:
            status, _ = _json_request(target, token=token, timeout=args.timeout)
            return status, perf_counter() - started, ""
        except (TimeoutError, URLError, OSError) as error:
            return 0, perf_counter() - started, f"{type(error).__name__}: {error}"

    started = perf_counter()
    workers = min(args.concurrency, args.requests)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(hit, index) for index in range(args.requests)]
        start_gate.set()
        results = [future.result() for future in as_completed(futures)]
    wall_seconds = perf_counter() - started

    latencies = [elapsed for _, elapsed, _ in results]
    successful = [elapsed for status, elapsed, _ in results if 200 <= status < 300]
    statuses: dict[str, int] = {}
    errors: dict[str, int] = {}
    for status, _, error in results:
        statuses[str(status)] = statuses.get(str(status), 0) + 1
        if error:
            errors[error] = errors.get(error, 0) + 1
    report = {
        "target": target,
        "concurrency": workers,
        "requests": args.requests,
        "success_rate_percent": round(len(successful) * 100 / len(results), 2),
        "throughput_requests_per_second": round(len(results) / wall_seconds, 2),
        "latency_seconds": {
            "min": round(min(latencies), 4),
            "mean": round(statistics.fmean(latencies), 4),
            "p50": round(_percentile(latencies, 50), 4),
            "p80": round(_percentile(latencies, 80), 4),
            "p95": round(_percentile(latencies, 95), 4),
            "max": round(max(latencies), 4),
        },
        "http_status_counts": statuses,
        "errors": errors,
    }
    report["requirements"] = {
        "all_requests_succeeded": len(successful) == len(results),
        "p80_within_limit": report["latency_seconds"]["p80"] <= args.max_p80,
        "max_response_within_limit": report["latency_seconds"]["max"] <= args.max_response,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(report["requirements"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
