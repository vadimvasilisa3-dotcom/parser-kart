import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(r"c:\Projects\NEXUS_TABLES\nexus_wallet_sync\.env"))
sys.path.insert(0, str(Path(r"c:\Projects\NEXUS_TABLES\nexus_wallet_sync\deploy")))
from ssh_client import connect

c = connect()
for cmd in [
    "systemctl status parser-kart --no-pager | head -15",
    "ufw status numbered 2>/dev/null | head -25 || true",
    "curl -s http://127.0.0.1:8000/api/health",
]:
    _, o, e = c.exec_command(cmd)
    print("---", cmd)
    print(o.read().decode(errors="replace"))
c.close()
