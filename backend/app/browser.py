"""
NATRA backend — Playwright browser automation helper.

Phase 2, Task 18: establish that Playwright browser automation is
installed and working, before any real scraping logic exists. Mirrors
`db.py`'s Task 4 role for Oracle: a small, isolated liveness check that
later tasks (CBE/Telebirr receipt fetching, Tasks 20/22) will build on.

No receipt-fetching or parsing logic lives here yet — this module's only
job is confirming a headless browser can actually launch and load a page.
"""

from playwright.sync_api import sync_playwright


def check_browser() -> dict:
    """
    Launch a headless Chromium browser, load a trivial page, and close it.

    Returns a plain dict describing success/failure, the same shape as
    `db.check_connection()` — never raises, so a broken browser
    installation degrades to a clear error response instead of crashing
    the request.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto("about:blank")
                page.close()
            finally:
                browser.close()
        return {"browser_ready": True}
    except Exception as exc:  # noqa: BLE001 - deliberately broad, mirrors check_connection()
        return {"browser_ready": False, "error": str(exc)}
