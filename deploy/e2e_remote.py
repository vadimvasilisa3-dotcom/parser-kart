"""E2E на VDS: health, UI-статика, тестовый сбор 3 организаций."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(r"c:\Projects\NEXUS_TABLES\nexus_wallet_sync\.env"))
sys.path.insert(0, str(Path(r"c:\Projects\NEXUS_TABLES\nexus_wallet_sync\deploy")))
from ssh_client import connect  # noqa: E402

BASE = "http://127.0.0.1:8000"
TIMEOUT_SEC = 600
POLL_SEC = 10


def run(client, cmd: str) -> tuple[int, str]:
    _, stdout, _ = client.exec_command(cmd)
    out = stdout.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out.strip()


def main() -> int:
    results: list[dict] = []
    client = connect()
    try:
        for name, cmd in [
            ("service_active", "systemctl is-active parser-kart"),
            ("health", f"curl -sf {BASE}/api/health"),
            (
                "cities_count",
                f"curl -sf {BASE}/cities.json | python3 -c \"import sys,json; print(len(json.load(sys.stdin)))\"",
            ),
            ("index_has_select", f"curl -sf {BASE}/ | grep -c 'id=\"city\"' || true"),
        ]:
            code, out = run(client, cmd)
            ok = code == 0 and out and out != "0"
            if name == "index_has_select":
                ok = code == 0 and out != "0"
            results.append({"test": name, "ok": ok, "detail": out[:500]})
            print(f"{'OK' if ok else 'FAIL'}  {name}: {out[:120]}")

        payload = json.dumps(
            {"category": "Салоны красоты", "city": "Чебоксары", "max_results": 3},
            ensure_ascii=False,
        )
        code, out = run(
            client,
            f"curl -sf -X POST {BASE}/api/jobs -H 'Content-Type: application/json' -d '{payload}'",
        )
        job_ok = code == 0
        job_id = ""
        if job_ok:
            try:
                job_id = json.loads(out).get("job_id", "")
            except json.JSONDecodeError:
                job_ok = False
        results.append({"test": "create_job", "ok": job_ok and bool(job_id), "detail": out})
        print(f"{'OK' if job_ok else 'FAIL'}  create_job: {out}")

        if not job_id:
            _print_summary(results)
            return 1

        deadline = time.time() + TIMEOUT_SEC
        final_status = "unknown"
        found = 0
        final_detail = ""
        while time.time() < deadline:
            time.sleep(POLL_SEC)
            code, out = run(client, f"curl -sf {BASE}/api/jobs/{job_id}")
            if code != 0:
                continue
            job = json.loads(out)
            final_status = job.get("status", "")
            found = job.get("found", 0)
            msg = job.get("message", "")
            print(f"  poll: status={final_status} found={found} — {msg[:80]}")
            if final_status in ("completed", "failed"):
                final_detail = out[:2000]
                break

        scrape_ok = final_status == "completed" and found >= 1
        results.append(
            {
                "test": "scrape_e2e",
                "ok": scrape_ok,
                "detail": f"status={final_status} found={found}; {final_detail[:400]}",
            }
        )
        print(f"{'OK' if scrape_ok else 'FAIL'}  scrape_e2e: status={final_status} found={found}")

    finally:
        client.close()

    _print_summary(results)
    failed = sum(1 for r in results if not r["ok"])
    return 1 if failed else 0


def _print_summary(results: list[dict]) -> None:
    passed = sum(1 for r in results if r["ok"])
    failed = len(results) - passed
    print(f"\n=== Remote E2E: {passed} passed, {failed} failed ===")
    for r in results:
        if not r["ok"]:
            print(f"  FAIL {r['test']}: {r['detail'][:200]}")


if __name__ == "__main__":
    raise SystemExit(main())
