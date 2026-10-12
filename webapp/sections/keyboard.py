# Keyboard Performance Status - M — month groups separated by one blank row.

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

import config
import keyboard_logic as kl
from graph_client import GraphError, get_sheet_grid
from sections.common import roster_choices, write_with_fresh_read
from sheet_grid import MONTH_NAMES

bp = Blueprint("keyboard", __name__, url_prefix="/keyboard")
SHEET = config.KEYBOARD_SHEET


def _load():
    return kl.parse_rows(get_sheet_grid(SHEET))


def _parse_period(value):
    """'2026-09' -> (2026, 9), or None."""
    try:
        year, month = (int(p) for p in (value or "").split("-"))
        return (year, month) if 1 <= month <= 12 else None
    except ValueError:
        return None


def _period_options(period_list):
    return [{"key": kl.period_key(y, m), "label": kl.period_label(y, m)} for y, m in reversed(period_list)]


def _to_float(value):
    try:
        return float(str(value).replace("%", "").replace("WPM", "").replace("wpm", "").strip())
    except (TypeError, ValueError):
        return None


@bp.route("/dashboard")
def dashboard():
    try:
        records, groups = _load()
    except (GraphError, ValueError) as e:
        return render_template("keyboard/dashboard.html", active_page="dashboard", error=str(e),
                               periods=[], selected=None, summary=None, names=[], table={}, period_list=[])
    period_list = kl.periods(groups)
    selected = _parse_period(request.args.get("period"))
    if selected not in period_list:
        selected = period_list[-1] if period_list else None
    summary = kl.month_summary(records, *selected) if selected else None
    names, table = kl.comparison_table(records, period_list)
    return render_template(
        "keyboard/dashboard.html", active_page="dashboard", error=None,
        periods=_period_options(period_list), selected=selected,
        selected_key=kl.period_key(*selected) if selected else "",
        selected_label=kl.period_label(*selected) if selected else "",
        summary=summary, names=names, table=table, period_list=period_list,
        period_label=kl.period_label,
    )


@bp.route("/add", methods=["GET", "POST"])
def add_entry():
    records, period_list, load_error = [], [], None
    try:
        records, groups = _load()
        period_list = kl.periods(groups)
    except (GraphError, ValueError) as e:
        load_error = str(e)
        flash(load_error, "err")

    latest = period_list[-1] if period_list else (date.today().year, date.today().month)
    form = {"name": "", "year": str(latest[0]), "month": str(latest[1]), "absent": "",
            "accuracy": "", "speed": "", "comments": "", "editing": ""}

    if request.method == "GET" and request.args.get("name") and request.args.get("period"):
        period = _parse_period(request.args["period"])
        record = kl.find_record(records, request.args["name"], *period) if period else None
        if record:
            form.update(
                name=record["name"], year=str(record["year"]), month=str(record["month_num"]),
                absent="1" if record["absent"] else "",
                accuracy="" if record["accuracy"] is None or record["absent"] else f"{record['accuracy'] * 100:g}",
                speed="" if record["speed"] is None or record["absent"] else f"{record['speed']:g}",
                comments=record["comments"], editing="1",
            )
        elif not load_error:
            flash("That entry is no longer in the sheet.", "err")
    elif request.method == "GET" and request.args.get("name"):
        # Back from "+ Add new employee": preselect the name just added.
        form["name"] = request.args["name"].strip()

    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k in form}
        try:
            entry = {
                "name": form["name"],
                "year": int(form["year"]) if form["year"].isdigit() else None,
                "month_num": int(form["month"]) if form["month"].isdigit() else None,
                "absent": bool(form["absent"]),
                "accuracy_pct": _to_float(form["accuracy"]) if form["accuracy"] else None,
                "speed_wpm": _to_float(form["speed"]) if form["speed"] else None,
                "comments": form["comments"],
            }
            if form["accuracy"] and entry["accuracy_pct"] is None:
                raise ValueError("Accuracy must be a number, e.g. 98.5")
            if form["speed"] and entry["speed_wpm"] is None:
                raise ValueError("Speed must be a number of words per minute, e.g. 24.5")
            action = write_with_fresh_read(SHEET, lambda grid: kl.plan_save(grid, entry, editing=bool(form["editing"])))
            label = kl.period_label(entry["year"], entry["month_num"])
            flash(f"Updated existing entry — {entry['name']}, {label}" if action == "updated"
                  else f"Saved — {entry['name']}, {label}", "ok")
            if form["editing"]:
                return redirect(url_for("keyboard.history"))
            return redirect(url_for("keyboard.add_entry"))
        except (ValueError, GraphError) as e:
            flash(str(e), "err")

    return render_template(
        "keyboard/add_entry.html", active_page="add", form=form,
        employees=roster_choices(form["name"]),
        month_names=MONTH_NAMES, editing=bool(form["editing"]),
    )


@bp.route("/history")
def history():
    employee = request.args.get("employee") or ""
    period_arg = request.args.get("period") or ""
    try:
        records, groups = _load()
    except (GraphError, ValueError) as e:
        return render_template("keyboard/history.html", active_page="history", error=str(e),
                               rows=[], employees=[], periods=[], employee=employee, period=period_arg)
    rows = records
    if employee:
        rows = [r for r in rows if r["name"].lower() == employee.lower()]
    period = _parse_period(period_arg)
    if period:
        rows = [r for r in rows if (r["year"], r["month_num"]) == period]
    rows = sorted(rows, key=lambda r: ((r["year"] or 0, r["month_num"] or 0), -r["row"]), reverse=True)
    return render_template(
        "keyboard/history.html", active_page="history", error=None, rows=rows,
        employees=sorted({r["name"] for r in records if r["name"]}, key=str.lower),
        periods=_period_options(kl.periods(groups)), employee=employee, period=period_arg,
        period_key=kl.period_key, period_label=kl.period_label,
    )


@bp.route("/history/delete", methods=["POST"])
def history_delete():
    name = request.form.get("name", "")
    period = _parse_period(request.form.get("entry_period"))
    try:
        if not period:
            raise ValueError("Could not identify which entry to delete.")
        write_with_fresh_read(SHEET, lambda grid: kl.plan_delete(grid, name, *period))
        flash(f"Deleted entry — {name}, {kl.period_label(*period)}", "ok")
    except (ValueError, GraphError) as e:
        flash(str(e), "err")
    return redirect(url_for("keyboard.history", employee=request.form.get("employee") or None,
                            period=request.form.get("period") or None))
