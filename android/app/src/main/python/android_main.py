"""Chaquopy entry point for the Android app.

Kotlin calls start(filesDir); we set a writable cache dir, start the same HTTP
dashboard server the desktop app uses on a background thread, and return the port
for the WebView to load.
"""
import os
import socket
import threading

_state = {}


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start(cache_dir: str = "") -> int:
    if "port" in _state:
        return _state["port"]

    # Must be set BEFORE importing app (cache paths are read at import time).
    if cache_dir:
        os.environ["CW_CACHE_DIR"] = cache_dir
    os.environ.setdefault("CW_CONTACT_EMAIL", "congress-whales-android")

    import app  # noqa: E402

    port = _free_port()
    server = app.make_server(port=port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _state["port"] = port
    return port
