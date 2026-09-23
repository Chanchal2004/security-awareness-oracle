import json
import os
import time
from pathlib import Path

import requests

RENDER_API_URL = os.environ.get("RENDER_API_URL", "https://security-awareness-platform-2.onrender.com").rstrip("/")
PC_SYNC_TOKEN = os.environ["PC_SYNC_TOKEN"]
LOCAL_DATA_PATH = Path(os.environ.get("LOCAL_DATA_PATH", r"C:\Chanchal\SecurityAwarenessData"))
POLL_SECONDS = int(os.environ.get("PC_SYNC_POLL_SECONDS", "5"))
STATE_FILE = LOCAL_DATA_PATH / ".sync_state.json"


def load_since() -> str:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8")).get("since", "")
    except Exception:
        return ""


def save_since(value: str) -> None:
    STATE_FILE.write_text(json.dumps({"since": value}, indent=2), encoding="utf-8")


def sync_once() -> None:
    LOCAL_DATA_PATH.mkdir(parents=True, exist_ok=True)
    submissions_dir = LOCAL_DATA_PATH / "submissions"
    submissions_dir.mkdir(parents=True, exist_ok=True)
    since = load_since()
    r = requests.get(
        f"{RENDER_API_URL}/api/pc-sync/submissions",
        params={"since": since},
        headers={"X-PC-SYNC-TOKEN": PC_SYNC_TOKEN},
        timeout=20,
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    newest = since
    for item in items:
        sid = str(item["id"])
        (submissions_dir / f"{sid}.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        ts = item.get("timestamp", "")
        if ts > newest:
            newest = ts
    if newest and newest != since:
        save_since(newest)
    print(f"Synced {len(items)} submission(s)")


if __name__ == "__main__":
    print(f"PC sync agent running. Saving to: {LOCAL_DATA_PATH}")
    while True:
        try:
            sync_once()
        except Exception as exc:
            print(f"Sync error: {exc}")
        time.sleep(POLL_SECONDS)
