"""Native desktop launcher for the Congress Whales dashboard.

Double-click "Congress Whales.bat" (or run `pythonw desktop_app.py`). This starts
the local dashboard server on a background thread and opens it in a real desktop
window via the OS webview. If the native webview backend isn't available for any
reason, it falls back to opening your default browser.
"""
from __future__ import annotations

import os
import socket
import sys
import threading

# When running as a packaged .exe the script folder is a temp extraction dir, so
# point the cache at a stable per-user location and use a generic contact string.
if getattr(sys, "frozen", False):
    _base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    os.environ.setdefault("CW_CACHE_DIR", os.path.join(_base, "CongressWhales"))
os.environ.setdefault("CW_CONTACT_EMAIL", "congress-whales-desktop-app")

import app  # noqa: E402  (imported after env defaults are set)


def _free_port(preferred: int = 8787) -> int:
    for p in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((app.HOST, p)) != 0:  # nothing listening -> free
                return p
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((app.HOST, 0))
        return s.getsockname()[1]


def main() -> None:
    port = _free_port()
    server = app.make_server(port=port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://{app.HOST}:{port}"
    print(f"Congress Whales running at {url}")

    # Background watcher: desktop notification when a member files a new trade.
    try:
        import cw_notify
        cw_notify.start()
    except Exception:
        pass

    try:
        import webview
        webview.create_window("Congress Whales 🐋", url, width=1180, height=820,
                              min_size=(760, 560))
        webview.start()  # blocks until the window is closed
    except Exception as exc:
        # No native webview backend -> fall back to the default browser.
        print(f"(native window unavailable: {exc}) -> opening in browser")
        import webbrowser
        webbrowser.open(url)
        try:
            server.serve_forever()  # keep serving until the console is closed
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
