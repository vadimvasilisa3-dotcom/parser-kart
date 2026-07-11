"""Deploy parser-kart to VDSka VPS via SSH (uses NEXUS_SSH_* from nexus .env)."""
from __future__ import annotations

import os
import sys
import tarfile
import tempfile
from pathlib import Path

from dotenv import load_dotenv

NEXUS_ENV = Path(r"c:\Projects\NEXUS_TABLES\nexus_wallet_sync\.env")
load_dotenv(NEXUS_ENV)

sys.path.insert(0, str(Path(r"c:\Projects\NEXUS_TABLES\nexus_wallet_sync\deploy")))
from ssh_client import connect  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REMOTE_DIR = "/opt/parser-kart"
EXCLUDE = {".venv", "__pycache__", ".git", "data/output", ".pytest_cache"}


def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE:
        return True
    if path.suffix == ".pyc":
        return True
    return False


def make_archive() -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
    tmp.close()
    archive = Path(tmp.name)
    with tarfile.open(archive, "w:gz") as tar:
        for item in ROOT.rglob("*"):
            if _should_skip(item):
                continue
            if item.is_file():
                tar.add(item, arcname=item.relative_to(ROOT))
    return archive


def run_remote(client, cmd: str) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def main() -> int:
    print(f"==> Host: {os.getenv('NEXUS_SSH_HOST', '217.177.46.34')}")
    archive = make_archive()
    print(f"==> Archive: {archive} ({archive.stat().st_size // 1024} KB)")

    client = connect()
    sftp = client.open_sftp()
    try:
        remote_tar = "/tmp/parser-kart-deploy.tar.gz"
        print("==> Upload")
        sftp.put(str(archive), remote_tar)

        script = f"""
set -e
mkdir -p {REMOTE_DIR}
tar -xzf {remote_tar} -C {REMOTE_DIR}
rm -f {remote_tar}
cd {REMOTE_DIR}
    if [ ! -f .env ]; then cp .env.example .env; fi
    grep -q '^SCRAPE_REVIEWS=true' .env 2>/dev/null || sed -i 's/^SCRAPE_REVIEWS=.*/SCRAPE_REVIEWS=true/' .env 2>/dev/null || echo 'SCRAPE_REVIEWS=true' >> .env
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip wget gnupg unzip || true
if ! command -v google-chrome >/dev/null 2>&1; then
  wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg || true
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y google-chrome-stable || true
fi
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
id parserkart >/dev/null 2>&1 || useradd -r -m -d {REMOTE_DIR} -s /bin/bash parserkart || true
chown -R parserkart:parserkart {REMOTE_DIR} || chown -R root:root {REMOTE_DIR}
cp deploy/parser-kart.service /etc/systemd/system/parser-kart.service
systemctl daemon-reload
systemctl enable parser-kart
systemctl restart parser-kart
sleep 2
systemctl is-active parser-kart
curl -s http://127.0.0.1:8000/api/health || true
"""
        print("==> Remote install")
        code, out, err = run_remote(client, script)
        print(out.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
        if err:
            print(err.encode("utf-8", errors="replace").decode("utf-8", errors="replace"), file=sys.stderr)
        if code != 0:
            print(f"Remote exit code: {code}", file=sys.stderr)
            return code
    finally:
        sftp.close()
        client.close()
        archive.unlink(missing_ok=True)

    print("==> Done: http://217.177.46.34:8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
