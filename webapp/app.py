from datetime import date

from flask import Flask, flash, redirect, render_template, request, url_for

import config
import logic
from graph_client import GraphError, add_table_row, get_table_columns, get_table_rows, update_table_row

app = Flask(__name__)
app.secret_key = "performance-webapp-local-only"  # single-user local tool, not internet-facing

# Widget hints for the Add Entry form. A category NOT listed here still works —
# it just falls back to a plain number input instead of a styled toggle/choice row.
KNOWN_WIDGETS = {
    "Punctuality": "toggle01",
    "L&D": "toggle01",
    "Fluency Compliance": "toggle01",
    "Innovation": "toggle01",
    "Extraordinary Performance": "choice",
    "Extra Hours": "decimal",
}
# Placeholder scale — adjust to match your actual Extraordinary Performance points.
EXTRAORDINARY_CHOICES = [0, 1, 2, 3]


@app.context_processor
def inject_globals():
    return {"active_file": config.ACTIVE_FILE}


def _load_records():
    headers = get_table_columns()
    rows = get_table_rows()
    records = logic.rows_to_records(headers, rows)
    cols = logic.detect_columns(headers)
    return records, cols


@app.route("/")
def dashboard():
    try:
        records, cols = _load_records()
    except GraphError as e:
        return render_template(
            "dashboard.html", active_page="dashboard", error=str(e),
            today=date.today(), week_start=None, today_entries=[],
            category_names=[], text_names=[], totals=[], totals_row=None,
        )

    today = date.today()
    today_entries = logic.entries_for_date(records, today)
    monday, _ = logic.week_bounds(today)
    totals = logic.totals_by_employee(records, monday, today, cols["category_names"])
    totals_list = sorted(
        [{"name": n, **v} for n, v in totals.items()],
        key=lambda x: (-x["amount"], x["name"]),
    )
    totals_row = {
        "points": sum(t["points"] for t in totals_list),
        "amount": sum(t["amount"] for t in totals_list),
    } if totals_list else None
    return render_template(
        "dashboard.html", active_page="dashboard", error=None,
        today=today, week_start=monday, today_entries=today_entries,
        category_names=cols["category_names"], text_names=cols["text_names"],
        totals=totals_list, totals_row=totals_row,
    )


@app.route("/add", methods=["GET", "POST"])
def add_entry():
    try:
        records, cols = _load_records()
    except GraphError as e:
        flash(str(e), "err")
        return render_template(
            "add_entry.html", active_page="add", employees=[], categories=[], text_fields=[],
            known_widgets=KNOWN_WIDGETS, extraordinary_choices=EXTRAORDINARY_CHOICES,
            today=date.today().isoformat(),
        )

    employees = logic.distinct_employees(records)
    categories = cols["category_names"]
    text_fields = cols["text_names"]

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        date_str = request.form.get("date") or ""
        entry_date = logic.parse_date_value(date_str)

        errors = []
        if not name:
            errors.append("Select an employee.")
        if not entry_date:
            errors.append("Enter a valid date.")

        values_by_column = {}
        for cat in categories:
            raw = request.form.get(f"cat__{cat}")
            values_by_column[cat] = logic.to_number(raw)
        for tf in text_fields:
            values_by_column[tf] = (request.form.get(f"txt__{tf}") or "").strip()

        if not errors:
            try:
                existing_index = logic.find_existing_row(records, name, entry_date)
                payload = dict(values_by_column)
                payload["Name"] = name
                payload["Date"] = entry_date.isoformat()

                if existing_index is not None:
                    existing_record = next(r for r in records if r["_row_index"] == existing_index)
                    if cols["index_idx"] is not None:
                        payload["Index"] = existing_record.get("Index")
                    # A blank text field means "didn't touch it" — keep the sheet's
                    # existing note instead of wiping it with an empty string.
                    for tf in text_fields:
                        if not payload[tf]:
                            payload[tf] = existing_record.get(tf) or ""
                    update_table_row(existing_index, payload)
                    flash(f"Updated existing entry — {name}, {date_str}", "ok")
                else:
                    if cols["index_idx"] is not None:
                        payload["Index"] = logic.next_index(records)
                    add_table_row(payload)
                    flash(f"Saved — {name}, {date_str}", "ok")
                return redirect(url_for("add_entry"))
            except GraphError as e:
                errors.append(str(e))

        for err in errors:
            flash(err, "err")

    return render_template(
        "add_entry.html", active_page="add", employees=employees, categories=categories,
        text_fields=text_fields, known_widgets=KNOWN_WIDGETS,
        extraordinary_choices=EXTRAORDINARY_CHOICES, today=date.today().isoformat(),
    )


@app.route("/history")
def history():
    try:
        records, cols = _load_records()
    except GraphError as e:
        return render_template(
            "history.html", active_page="history", error=str(e),
            rows=[], employees=[], categories=[], text_names=[],
            selected_employee="", selected_from="", selected_to="",
        )

    employee = request.args.get("employee") or None
    from_str = request.args.get("from", "")
    to_str = request.args.get("to", "")
    date_from = logic.parse_date_value(from_str) if from_str else None
    date_to = logic.parse_date_value(to_str) if to_str else None

    filtered = logic.filter_records(records, employee=employee, date_from=date_from, date_to=date_to)
    filtered.sort(key=lambda r: (r.get("Date") or date.min, r.get("Name") or ""), reverse=True)

    return render_template(
        "history.html", active_page="history", error=None,
        rows=filtered, employees=logic.distinct_employees(records),
        categories=cols["category_names"], text_names=cols["text_names"],
        selected_employee=employee or "", selected_from=from_str, selected_to=to_str,
    )


if __name__ == "__main__":
    print(f"Starting on http://localhost:5000  (ACTIVE_FILE={config.ACTIVE_FILE})")
    app.run(debug=True, port=5000)
