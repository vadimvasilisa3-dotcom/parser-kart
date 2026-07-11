"""Inspect recent parser-kart jobs on VDS."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(r"c:\Projects\NEXUS_TABLES\nexus_wallet_sync\.env"))
sys.path.insert(0, str(Path(r"c:\Projects\NEXUS_TABLES\nexus_wallet_sync\deploy")))
from ssh_client import connect  # noqa: E402


def run(client, cmd: str) -> str:
    _, stdout, _ = client.exec_command(cmd)
    return stdout.read().decode("utf-8", errors="replace")


def main() -> int:
    client = connect()
    try:
        jobs_raw = run(client, "curl -sf http://127.0.0.1:8000/api/jobs")
        jobs = json.loads(jobs_raw)
        print(f"=== Recent jobs ({len(jobs)}) ===")
        for j in jobs[:10]:
            print(
                f"{j.get('id','')[:8]}… | {j.get('status')} | found={j.get('found')}/{j.get('max_results')} | "
                f"cat={j.get('category')} | city={j.get('city')} | query={j.get('query')}"
            )

        if jobs:
            job_id = jobs[0]["id"]
            detail_raw = run(client, f"curl -sf http://127.0.0.1:8000/api/jobs/{job_id}")
            detail = json.loads(detail_raw)
            print(f"\n=== Latest job detail: {job_id} ===")
            print(f"status={detail.get('status')} found={detail.get('found')} total={detail.get('total')}")
            print(f"message={detail.get('message')}")
            print(f"filters={detail.get('filters')}")
            print("\n--- logs ---")
            for line in detail.get("logs", [])[-25:]:
                print(line)
            results = detail.get("results") or []
            print(f"\n--- results ({len(results)}) ---")
            for r in results[:5]:
                print(f"  {r.get('name')} | {r.get('phone')} | {r.get('address','')[:60]}")

        print("\n=== scraper.log tail ===")
        print(run(client, "tail -50 /opt/parser-kart/scraper.log 2>/dev/null || echo '(no file)'"))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
