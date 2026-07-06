"""Generate page_data.py (PAGE string) from dashboard.html.

Used by the Android build, where loose data files can't be opened at runtime, so
the HTML is baked into an importable Python module instead.
"""
import os

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(here, "dashboard.html"), encoding="utf-8") as fh:
    html = fh.read()

with open(os.path.join(here, "page_data.py"), "w", encoding="utf-8") as fh:
    fh.write("# AUTO-GENERATED from dashboard.html by tools/gen_page_data.py\n")
    fh.write("PAGE = " + repr(html) + "\n")

print("wrote page_data.py (%d chars)" % len(html))
