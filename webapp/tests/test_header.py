# The header's logo is the "ADIRI" wordmark alone: nothing (no trophy tile or
# any icon) may appear to the left of it, on Home or on any section page.
# Fake data only — no Graph.

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_routes import client  # noqa: F401  (pytest fixture)

PAGES = ["/"] + [f"/{s}/{p}" for s in ("daily", "whatsapp", "monthly", "keyboard")
                 for p in ("dashboard", "add", "history")]


def header_before_wordmark(html):
    header = re.search(r"<header\b.*?</header>", html, re.S).group(0)
    return header[: header.index(">ADIRI<")]


@pytest.mark.parametrize("url", PAGES)
def test_no_icon_left_of_adiri(client, url):
    before = header_before_wordmark(client.get(url).get_data(as_text=True))
    assert "<svg" not in before and "<img" not in before and "data-lucide" not in before
    assert "logoGold" not in before                       # the old trophy tile's gradient


@pytest.mark.parametrize("url", PAGES)
def test_wordmark_links_home(client, url):
    html = client.get(url).get_data(as_text=True)
    assert re.search(r'<a href="/"[^>]*aria-label="ADIRI — go to the home page"[^>]*>\s*'
                     r'<span class="text-\[1\.87rem\][^"]*">ADIRI</span>', html)
