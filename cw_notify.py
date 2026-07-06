"""Background watcher that pops a desktop notification when a member of Congress
files a NEW trade disclosure.

Polls the recent House/Senate feed on an interval, remembers which filing IDs it
has already seen (persisted in the cache dir), and notifies only on genuinely new
ones. The very first run just seeds the seen-set so you aren't flooded with a
notification for every existing filing.
"""
from __future__ import annotations

import json
import os
import threading
import time

import cw_congress
from cw_http import CACHE_DIR

_SEEN = os.path.join(CACHE_DIR, "seen_filings.json")


def _load_seen() -> dict:
    try:
        with open(_SEEN, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_seen(seen: dict) -> None:
    try:
        with open(_SEEN, "w", encoding="utf-8") as fh:
            json.dump(seen, fh)
    except Exception:
        pass


def _notify(title: str, message: str) -> None:
    try:
        from plyer import notification
        notification.notify(title=title, message=message,
                            app_name="Congress Whales", timeout=12)
        return
    except Exception:
        pass
    # Fallback: Windows toast via PowerShell (no extra dependency).
    try:
        import subprocess
        ps = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null;"
            "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
            f"$t.GetElementsByTagName('text')[0].AppendChild($t.CreateTextNode('{title}')) > $null;"
            f"$t.GetElementsByTagName('text')[1].AppendChild($t.CreateTextNode('{message}')) > $null;"
            "$n=[Windows.UI.Notifications.ToastNotification]::new($t);"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Congress Whales').Show($n);")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=15)
    except Exception:
        pass


def poll_once(notify: bool = True) -> int:
    """Check recent filings; notify on new ones. Returns count of new filings."""
    seen = _load_seen()
    first_run = not seen
    trades = cw_congress.get_congress_trades(days=4)
    by_filing: dict[str, dict] = {}
    for t in trades:
        doc = t.get("doc_id")
        if not doc:
            continue
        f = by_filing.setdefault(doc, {"member": t["member"], "chamber": t["chamber"],
                                       "tickers": set()})
        if t["asset_code"] in cw_congress.STOCK_CODES:
            f["tickers"].add(t["ticker"])
    new = 0
    for doc, f in by_filing.items():
        if doc in seen:
            continue
        seen[doc] = int(time.time())
        new += 1
        if notify and not first_run and f["tickers"]:
            tk = ", ".join(sorted(f["tickers"])[:6])
            _notify(f"New disclosure: {f['member']}", f"{f['chamber']} · {tk}")
    _save_seen(seen)
    return new


def start(interval_seconds: int = 900) -> None:
    """Start the background watcher (daemon thread)."""
    def loop():
        poll_once(notify=False)  # seed silently on startup
        while True:
            time.sleep(interval_seconds)
            try:
                poll_once(notify=True)
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True, name="cw-notify").start()
