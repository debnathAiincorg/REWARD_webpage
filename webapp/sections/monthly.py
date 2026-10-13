# Monthly Performance Bonus — month blocks under yellow date banners.

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

import config
import logic
import monthly_logic as ml
from graph_client import GraphError, get_sheet_grid
from sections.common import load_roster, roster_choices, write_with_fresh_read
from sheet_grid import MONTH_NAMES, fold, month_number

bp = Blueprint("monthly", __name__, url_prefix="/monthly")
SHEET = config.MONTHLY_SHEET


def _load():
    return ml.parse_blocks(get_sheet_grid(SHEET))


def _block_options(blocks):
    return [{"id": b["id"], "label": b["label"]} for b in sorted(blocks, key=lambda b: b["date"], reverse=True)]


def _previous_month(d):
    return 12 if d.month == 1 else d.month - 1


def _today():
    """Today's date — a function so tests can fix "today"."""
    return date.today()


@bp.route("/dashboard")
def dashboard():
    try:
        _, blocks, _ = _load()
    except (GraphError, ValueError) as e:
        return render_template("monthly/dashboard.html", active_page="dashboard", error=str(e),
                               blocks=[], block=None, summary=None, roster=None, is_default=False, strip=None)
    # Opens on the latest block dated today or earlier (switching on the
    # banner day itself); any block can be picked.
    block = ml.find_block(blocks, request.args.get("block"))
    is_default = block is None
    if is_default:
        block = ml.report_block(blocks, _today())
    # Headcounts come from the shared roster, like Daily's dashboard.
    roster_figures = ml.roster_kpis(block, load_roster()) if block else None
    # Period strip and the "previous period" figure (the block before).
    strip = None
    if block:
        prev = ml.previous_block(blocks, block)
        default = ml.report_block(blocks, _today())
        strip = {
            "bonus_month": ml.bonus_month(block),
            "reason": ml.report_reason(block, _today()),
            "default_text": f"latest block up to today ({default['text']})",
            "previous": {"text": prev["text"], "total": ml.block_summary(prev)["total_amount"]} if prev else None,
        }
    return render_template("monthly/dashboard.html", active_page="dashboard", error=None,
                           blocks=_block_options(blocks), block=block,
                           summary=ml.block_summary(block) if block else None, roster=roster_figures,
                           is_default=is_default, strip=strip)


@bp.route("/add", methods=["GET", "POST"])
def add_entry():
    blocks, records, load_error = [], [], None
    try:
        _, blocks, records = _load()
    except (GraphError, ValueError) as e:
        load_error = str(e)
        flash(load_error, "err")

    latest = max(blocks, key=lambda b: b["date"]) if blocks else None
    form = {"block": latest["id"] if latest else "new", "name": "", "bonus": "", "status": "",
            "status_date": date.today().isoformat(), "notes": "",
            "for_month": str(_previous_month(latest["date"])) if latest else "", "editing": ""}

    if request.method == "GET" and request.args.get("block"):
        block = ml.find_block(blocks, request.args["block"])
        if block:
            form["block"] = block["id"]
            form["for_month"] = str(_previous_month(block["date"]))
            record = ml.find_record(block, request.args.get("name", ""))
            if record:
                form.update(
                    name=record["name"],
                    bonus="" if record["bonus"] == "" else str(record["bonus"]),
                    status=next((s for s in ml.STATUS_CHOICES if fold(s) == fold(record["status"])), ""),
                    status_date=record["status_date"].isoformat() if record["status_date"] else form["status_date"],
                    notes=record["notes"],
                    for_month=str(month_number(record["for_month"]) or form["for_month"]),
                    editing="1",
                )
        elif not load_error:
            flash("That month block is no longer in the sheet.", "err")
    elif request.method == "GET" and request.args.get("name"):
        # Back from "+ Add new employee": preselect the name just added.
        form["name"] = request.args["name"].strip()

    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k in form}
        try:
            status_date = None
            if form["status_date"]:
                status_date = logic.parse_date_value(form["status_date"])
                if not status_date:
                    raise ValueError("Enter a valid status date.")
            entry = {
                "name": form["name"], "bonus": form["bonus"], "status": form["status"],
                "status_date": status_date, "notes": form["notes"],
                "for_month": int(form["for_month"]) if form["for_month"].isdigit() else None,
            }
            action = write_with_fresh_read(
                SHEET, lambda grid: ml.plan_save(grid, form["block"], entry, editing=bool(form["editing"])))
            messages = {
                "updated": "Updated existing entry",
                "filled": "Filled in the pre-filled row",
                "added": "Added a new row to the block",
                "created": "Created a new month block",
            }
            flash(f"{messages[action]} — {entry['name']}", "ok")
            if form["editing"]:
                return redirect(url_for("monthly.history", block=form["block"]))
            return redirect(url_for("monthly.add_entry"))
        except (ValueError, GraphError) as e:
            flash(str(e), "err")

    selected_block = ml.find_block(blocks, form["block"])
    prefilled = [r["name"] for r in selected_block["rows"]] if selected_block else []
    return render_template(
        "monthly/add_entry.html", active_page="add", form=form,
        blocks=_block_options(blocks),
        new_block_date=ml.next_block_date(blocks),
        block_names={b["id"]: [r["name"] for r in b["rows"]] for b in blocks},
        prefilled=prefilled,
        employees=roster_choices(form["name"]),
        status_choices=ml.STATUS_CHOICES, month_names=MONTH_NAMES,
        editing=bool(form["editing"]),
    )


@bp.route("/history")
def history():
    block_id = request.args.get("block") or ""
    employee = request.args.get("employee") or ""
    status = request.args.get("status") or ""
    try:
        _, blocks, records = _load()
    except (GraphError, ValueError) as e:
        return render_template("monthly/history.html", active_page="history", error=str(e), rows=[],
                               blocks=[], employees=[], block_id=block_id, employee=employee, status=status,
                               status_choices=ml.STATUS_CHOICES)
    rows = records
    if block_id:
        rows = [r for r in rows if r["block_id"] == block_id]
    if employee:
        rows = [r for r in rows if fold(r["name"]) == fold(employee)]
    if status == "empty":
        rows = [r for r in rows if not r["filled"]]
    elif status == "Pending":
        rows = [r for r in rows if fold(r["status"]) not in ("approved", "missed")]
    elif status:
        rows = [r for r in rows if fold(r["status"]) == fold(status)]
    rows = sorted(rows, key=lambda r: (r["block_date"], -r["row"]), reverse=True)
    return render_template(
        "monthly/history.html", active_page="history", error=None, rows=rows,
        blocks=_block_options(blocks),
        employees=sorted({r["name"] for r in records}, key=fold),
        block_id=block_id, employee=employee, status=status, status_choices=ml.STATUS_CHOICES,
    )


@bp.route("/history/delete", methods=["POST"])
def history_delete():
    name = request.form.get("name", "")
    entry_block = request.form.get("entry_block", "")
    try:
        write_with_fresh_read(SHEET, lambda grid: ml.plan_clear(grid, entry_block, name))
        flash(f"Cleared {name}'s entry in the {date.fromisoformat(entry_block):%d %b %Y} block — "
              "the name stays in the block.", "ok")
    except (ValueError, GraphError) as e:
        flash(str(e), "err")
    return redirect(url_for("monthly.history", block=request.form.get("block") or None,
                            employee=request.form.get("employee") or None,
                            status=request.form.get("status") or None))
