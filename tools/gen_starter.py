"""Bake starter_snapshot.json into starter_data.py.

The Android build can't open loose data files at runtime, so the bundled starter
dashboard snapshot is embedded as an importable Python module. android_main writes
it into the cache on first launch so the app opens instantly with real data.
"""
import os

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(here, "starter_snapshot.json"), encoding="utf-8") as fh:
    snapshot = fh.read()

with open(os.path.join(here, "starter_data.py"), "w", encoding="utf-8") as fh:
    fh.write("# AUTO-GENERATED from starter_snapshot.json by tools/gen_starter.py\n")
    fh.write("SNAPSHOT30 = " + repr(snapshot) + "\n")

print("wrote starter_data.py (%d bytes snapshot)" % len(snapshot))
