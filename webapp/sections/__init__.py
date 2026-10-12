# The four sections — one per sheet of the workbook. Each is a Flask blueprint
# whose slug is its URL prefix (/daily/..., /whatsapp/...) and which exposes
# the same three endpoints: dashboard, add_entry, history. base.html builds
# the section nav from this list, so the order here is the order on screen.

SECTIONS = [
    {
        "slug": "daily",
        "title": "Daily Performance Bonus",
        "icon": "calendar-check",
        "blurb": "Daily points per category, week-to-date totals",
    },
    {
        "slug": "whatsapp",
        "title": "Employee Whatsapp",
        "icon": "message-circle",
        "blurb": "Contact list with WhatsApp links",
    },
    {
        "slug": "monthly",
        "title": "Monthly Performance Bonus",
        "icon": "wallet",
        "blurb": "Monthly bonus blocks, approvals and status",
    },
    {
        "slug": "keyboard",
        "title": "Keyboard Performance Status - M",
        "icon": "keyboard",
        "blurb": "Monthly typing accuracy and speed",
    },
]

SECTIONS_BY_SLUG = {s["slug"]: s for s in SECTIONS}
