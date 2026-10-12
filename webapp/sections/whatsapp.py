# Employee Whatsapp — a flat contact list (First_Name | Last_Name | Mobile_1).

from flask import Blueprint, flash, redirect, render_template, request, url_for

import config
import logic
import whatsapp_logic as wl
from graph_client import GraphError, get_sheet_grid
from sections.common import roster_choices, write_with_fresh_read

bp = Blueprint("whatsapp", __name__, url_prefix="/whatsapp")
SHEET = config.WHATSAPP_SHEET


def _load_contacts():
    return wl.parse_contacts(get_sheet_grid(SHEET))


@bp.route("/dashboard")
def dashboard():
    try:
        contacts = _load_contacts()
    except (GraphError, ValueError) as e:
        return render_template("whatsapp/dashboard.html", active_page="dashboard", error=str(e),
                               contacts=[], summary=None)
    summary = wl.dashboard_summary(contacts, logic.load_employee_list())
    return render_template("whatsapp/dashboard.html", active_page="dashboard", error=None,
                           contacts=sorted(contacts, key=lambda c: c["full_name"].lower()),
                           summary=summary)


@bp.route("/add", methods=["GET", "POST"])
def add_entry():
    form = {"first": "", "last": "", "mobile": "", "orig_first": "", "orig_last": ""}

    if request.method == "GET" and request.args.get("first"):
        # Editing from History: prefill from the sheet as it is now.
        try:
            contact = wl.find_contact(_load_contacts(), request.args["first"], request.args.get("last", ""))
        except (GraphError, ValueError) as e:
            flash(str(e), "err")
            contact = None
        if contact:
            form.update(first=contact["first_name"], last=contact["last_name"],
                        mobile=contact["mobile_raw"],
                        orig_first=contact["first_name"], orig_last=contact["last_name"])
        else:
            flash("That contact is no longer in the sheet.", "err")
    elif request.method == "GET" and request.args.get("name"):
        # Back from "+ Add new employee": preselect the name just added and
        # split it into First_Name (first word) / Last_Name (the rest).
        first, _, last = request.args["name"].strip().partition(" ")
        form.update(first=first, last=last.strip())

    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k in form}
        original = (form["orig_first"], form["orig_last"]) if form["orig_first"] else None
        try:
            action = write_with_fresh_read(
                SHEET, lambda grid: wl.plan_save(grid, form["first"], form["last"], form["mobile"], original))
            name = f"{form['first']} {form['last']}".strip()
            flash(f"Updated contact — {name}" if action == "updated" else f"Saved — {name}", "ok")
            return redirect(url_for("whatsapp.history") if original else url_for("whatsapp.add_entry"))
        except (ValueError, GraphError) as e:
            flash(str(e), "err")

    # The employee dropdown shows the contact's full name as the current pick
    # (it only fills First / Last name; it posts nothing itself).
    picked = f"{form['first']} {form['last']}".strip()
    return render_template("whatsapp/add_entry.html", active_page="add", form=form,
                           editing=bool(form["orig_first"]),
                           employees=roster_choices(picked), picked=picked)


@bp.route("/history")
def history():
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status") or ""
    try:
        contacts = _load_contacts()
    except (GraphError, ValueError) as e:
        return render_template("whatsapp/history.html", active_page="history", error=str(e),
                               rows=[], q=q, status=status)
    rows = contacts
    if q:
        needle = q.lower()
        rows = [c for c in rows if needle in c["full_name"].lower() or needle in c["mobile_raw"]]
    if status == "problem":
        rows = [c for c in rows if c["status"] != "ok"]
    return render_template("whatsapp/history.html", active_page="history", error=None,
                           rows=rows, q=q, status=status)


@bp.route("/history/delete", methods=["POST"])
def history_delete():
    first = request.form.get("first", "")
    last = request.form.get("last", "")
    try:
        write_with_fresh_read(SHEET, lambda grid: wl.plan_delete(grid, first, last))
        flash(f"Deleted contact — {first} {last}".strip(), "ok")
    except (ValueError, GraphError) as e:
        flash(str(e), "err")
    return redirect(url_for("whatsapp.history", q=request.form.get("q") or None,
                            status=request.form.get("status") or None))
