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
                     r'<span class="[^"]*text-\[2\.6rem\][^"]*lg:text-\[3\.8rem\][^"]*">ADIRI</span>', html)


def test_footer_shows_build_id(client):
    import app as app_module
    html = client.get("/").get_data(as_text=True)
    if app_module.BUILD_ID:
        assert f"build {app_module.BUILD_ID}" in html


@pytest.mark.parametrize("url", PAGES)
def test_header_scrolls_with_the_page(client, url):
    html = client.get(url).get_data(as_text=True)
    header_tag = re.search(r"<header\b[^>]*>", html).group(0)
    assert "sticky" not in header_tag and "fixed" not in header_tag


@pytest.mark.parametrize("url", PAGES)
def test_tagline_beside_adiri_on_one_baseline(client, url):
    html = client.get(url).get_data(as_text=True)
    link = re.search(r'<a href="/"[^>]*aria-label="ADIRI — go to the home page"[^>]*>(.*?)</a>', html, re.S)
    assert "items-baseline" in re.search(r'<a href="/"[^>]*aria-label="ADIRI[^>]*>', html).group(0)
    assert "flex-col" not in re.search(r'<a href="/"[^>]*aria-label="ADIRI[^>]*>', html).group(0)
    tagline = re.search(r'<span class="([^"]*)">Rewards &amp; Recognition</span>', link.group(1)).group(1)
    # Same size, weight and colour as before; hidden (not wrapped) where it won't fit.
    for cls in ("text-[0.7rem]", "sm:text-xs", "lg:text-[0.82rem]", "font-semibold", "text-on-chrome-accent",
                "whitespace-nowrap", "hidden", "sm:inline"):
        assert cls in tagline.split(), cls
    if url != "/":
        assert "lg:hidden" in tagline.split() and "xl:inline" in tagline.split()
