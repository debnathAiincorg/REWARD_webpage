import os
from datetime import date
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

import logic
from sections import SECTIONS, SECTIONS_BY_SLUG
from sections import daily, keyboard, monthly, whatsapp

app = Flask(__name__)
# Set FLASK_SECRET_KEY in the host's environment. The fallback exists only so a
# local checkout runs without setup — once this app is reachable over the
# network, a known key would let anyone forge a session cookie.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "performance-webapp-local-only")

for module in (daily, whatsapp, monthly, keyboard):
    app.register_blueprint(module.bp)


STATIC_DIR = Path(__file__).resolve().parent / "static"
ASSET_PATHS = [STATIC_DIR / "app.css", STATIC_DIR / "js" / "app.js"]


@app.context_processor
def inject_globals():
    # Cache-bust the CSS/JS with their newest mtime, so an edit takes effect on
    # the next load instead of a browser silently keeping a stale cached copy —
    # exactly the kind of "already fixed but still looks broken" confusion
    # that's bitten this app before (localStorage, and the CSS itself).
    try:
        asset_version = int(max(os.path.getmtime(p) for p in ASSET_PATHS))
    except OSError:
        asset_version = 0
    return {
        "current_year": date.today().year,
        "asset_version": asset_version,
        "sections": SECTIONS,
        # The section the current page belongs to (None on Home), which drives
        # the header's section name and its Dashboard / Add Entry / History tabs.
        "section": SECTIONS_BY_SLUG.get(request.blueprint) if request else None,
    }


@app.route("/")
def home():
    return render_template("home.html", active_page="home")


@app.route("/healthz")
def healthz():
    """Liveness probe for the host's deploy health check.

    Deliberately does not touch Graph: a Microsoft outage should surface as an
    error banner in the UI, not as a failed health check that gets the whole
    deployment rolled back.
    """
    return "ok", 200


# The pre-sections URLs keep working — bookmarks and old Edit links included.
# 307 (not 302) on the POST, so the browser re-sends the form to the new URL.
@app.route("/dashboard")
def legacy_dashboard():
    return redirect(url_for("daily.dashboard", **request.args))


@app.route("/add")
def legacy_add():
    return redirect(url_for("daily.add_entry", **request.args))


@app.route("/history")
def legacy_history():
    return redirect(url_for("daily.history", **request.args))


@app.route("/history/delete", methods=["POST"])
def legacy_history_delete():
    return redirect(url_for("daily.history_delete"), code=307)


def _back_to_add(name=None):
    """Return to the Add Entry page the roster change was made from.

    "next" is a section slug posted by the dropdown's roster forms; anything
    unknown falls back to Daily, so it can never redirect off the app.
    """
    slug = request.form.get("next") or "daily"
    if slug not in SECTIONS_BY_SLUG:
        slug = "daily"
    endpoint = f"{slug}.add_entry"
    return redirect(url_for(endpoint, name=name) if name else url_for(endpoint))


@app.route("/employees/add", methods=["POST"])
def employees_add():
    """Add a name to the shared employee roster (every section's dropdown).

    Writes employees.json only — never a sheet.
    """
    try:
        stored_name, was_added = logic.add_employee_name(request.form.get("name") or "")
    except OSError as e:
        flash(f"Could not save the employee list: {e}", "err")
        return _back_to_add()

    if not stored_name:
        flash("Enter a name to add.", "err")
        return _back_to_add()

    flash(
        f"Added {stored_name} to the employee list." if was_added
        else f"{stored_name} is already in the list — selected it for you.",
        "ok",
    )
    return _back_to_add(stored_name)


@app.route("/employees/delete", methods=["POST"])
def employees_delete():
    """Retire a name from the shared employee roster (every section's dropdown).

    Rewrites employees.json only: that person's rows in every sheet are left
    exactly as they are and still show up in History.
    """
    name = (request.form.get("name") or "").strip()
    try:
        removed = logic.remove_employee_name(name)
    except OSError as e:
        flash(f"Could not save the employee list: {e}", "err")
        return _back_to_add()

    if removed:
        flash(f"Removed {name} from the list — past entries are unchanged.", "ok")
    else:
        flash("That name is no longer in the list.", "err")
    return _back_to_add()


if __name__ == "__main__":
    # Local dev entry point only — in production the host runs gunicorn against
    # the `app` object above and never executes this block. Debug is off unless
    # explicitly asked for: it exposes an interactive code-execution console.
    debug = os.environ.get("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
    print(f"Starting on http://localhost:5000  (MAIN workbook, debug={debug})")
    app.run(debug=debug, port=5000)
