"""Web-App (Flask) für Arbeitswünsche in der Bäckerei (MVP)."""
from __future__ import annotations

import os
import sqlite3
from datetime import date, timedelta
import uuid
import secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional

from flask import Flask, redirect, render_template, request, url_for, flash, session, jsonify

WEEKDAYS: List[str] = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
PREF_VALUES: List[str] = ["no", "yes", "prefer"]
DB_FILENAME = "bakery.db"
ADMIN_TOKEN = os.getenv("BAKERY_ADMIN_TOKEN", "admin123")
ROLES: List[str] = ["baker", "service"]
CONTRACT_TYPES: List[str] = ["FullTime", "PartTime", "Minijob", "Apprentice"]

SHIFT_WINDOWS = {
    "baker": {
        "fixed": (3 * 60, 11 * 60, "03:00–11:00"),
    },
    "service": {
        "early": (6 * 60, 14 * 60 + 30, "06:00–14:30"),
        "late": (10 * 60, 18 * 60, "10:00–18:00"),
    },
}

CAL_START = 0
CAL_END = 24 * 60

app = Flask(__name__)
app.secret_key = "dev-secret-change-me"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILENAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employees (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS preferences (
            employee_id TEXT NOT NULL,
            weekday TEXT NOT NULL,
            pref TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(employee_id, weekday),
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schedules (
            employee_id TEXT NOT NULL,
            week_start TEXT NOT NULL,
            weekday TEXT NOT NULL,
            slot TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(employee_id, week_start, weekday),
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        )
        """
    )
    # Migration light: role + employee fields
    cur.execute("PRAGMA table_info(employees)")
    cols = [row[1] for row in cur.fetchall()]
    if "role" not in cols:
        cur.execute("ALTER TABLE employees ADD COLUMN role TEXT")
    if "contract_type" not in cols:
        cur.execute("ALTER TABLE employees ADD COLUMN contract_type TEXT")
    if "weekly_hours" not in cols:
        cur.execute("ALTER TABLE employees ADD COLUMN weekly_hours INTEGER")
    if "max_hours_per_day" not in cols:
        cur.execute("ALTER TABLE employees ADD COLUMN max_hours_per_day INTEGER")
    if "can_work_sun" not in cols:
        cur.execute("ALTER TABLE employees ADD COLUMN can_work_sun INTEGER")
    if "hourly_salary" not in cols:
        cur.execute("ALTER TABLE employees ADD COLUMN hourly_salary REAL")
    conn.commit()
    conn.close()


def generate_employee_id() -> str:
    return f"{secrets.randbelow(10**8):08d}"


def employee_id_exists(emp_id: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM employees WHERE id = ?", (emp_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def create_employee(
    name: str,
    role: str,
    contract_type: str,
    weekly_hours: int,
    max_hours_per_day: int,
    can_work_sun: int,
    hourly_salary: float,
) -> str:
    emp_id = generate_employee_id()
    while employee_id_exists(emp_id):
        emp_id = generate_employee_id()
    ts = utc_now_iso()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO employees
        (id, name, role, contract_type, weekly_hours, max_hours_per_day, can_work_sun, hourly_salary, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            emp_id,
            name.strip(),
            role,
            contract_type,
            weekly_hours,
            max_hours_per_day,
            can_work_sun,
            hourly_salary,
            ts,
            ts,
        ),
    )
    cur.executemany(
        "INSERT INTO preferences (employee_id, weekday, pref, updated_at) VALUES (?, ?, ?, ?)",
        [(emp_id, day, "no", ts) for day in WEEKDAYS],
    )
    conn.commit()
    conn.close()
    return emp_id


def list_employees() -> List[sqlite3.Row]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM employees ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return rows


def search_employees(query: Optional[str]) -> List[sqlite3.Row]:
    conn = get_conn()
    cur = conn.cursor()
    if not query:
        cur.execute("SELECT * FROM employees ORDER BY name")
    else:
        q = f"%{query.strip()}%"
        cur.execute(
            "SELECT * FROM employees WHERE id LIKE ? OR name LIKE ? ORDER BY name",
            (q, q),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_employee(emp_id: str) -> Optional[sqlite3.Row]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM employees WHERE id = ?", (emp_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_preferences(emp_id: str) -> Dict[str, str]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT weekday, pref FROM preferences WHERE employee_id = ?",
        (emp_id,),
    )
    rows = cur.fetchall()
    conn.close()
    prefs = {row["weekday"]: row["pref"] for row in rows}
    for day in WEEKDAYS:
        prefs.setdefault(day, "no")
    return prefs


def update_preferences(emp_id: str, new_prefs: Dict[str, str]) -> None:
    ts = utc_now_iso()
    conn = get_conn()
    cur = conn.cursor()
    data = [(new_prefs[day], ts, emp_id, day) for day in WEEKDAYS]
    cur.executemany(
        "UPDATE preferences SET pref = ?, updated_at = ? WHERE employee_id = ? AND weekday = ?",
        data,
    )
    cur.execute("UPDATE employees SET updated_at = ? WHERE id = ?", (ts, emp_id))
    conn.commit()
    conn.close()


def get_schedule(emp_id: str, week_start: str) -> Dict[str, str]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT weekday, slot FROM schedules WHERE employee_id = ? AND week_start = ?",
        (emp_id, week_start),
    )
    rows = cur.fetchall()
    conn.close()
    data = {row["weekday"]: row["slot"] for row in rows}
    for day in WEEKDAYS:
        data.setdefault(day, "off")
    return data


def save_schedule(emp_id: str, week_start: str, slots: Dict[str, str]) -> None:
    ts = utc_now_iso()
    conn = get_conn()
    cur = conn.cursor()
    for day in WEEKDAYS:
        cur.execute(
            """
            INSERT INTO schedules (employee_id, week_start, weekday, slot, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(employee_id, week_start, weekday)
            DO UPDATE SET slot = excluded.slot, updated_at = excluded.updated_at
            """,
            (emp_id, week_start, day, slots[day], ts),
        )
    conn.commit()
    conn.close()


def week_start_from_value(value: str) -> str:
    year_str, week_str = value.split("-W")
    year = int(year_str)
    week = int(week_str)
    monday = date.fromisocalendar(year, week, 1)
    return monday.isoformat()


def current_week_value() -> str:
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def week_value_from_date(d: date) -> str:
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def week_nav_values(week_value: str) -> Dict[str, str]:
    monday = date.fromisoformat(week_start_from_value(week_value))
    prev_week = week_value_from_date(monday - timedelta(days=7))
    next_week = week_value_from_date(monday + timedelta(days=7))
    return {"prev": prev_week, "next": next_week}


def week_day_numbers(week_value: str) -> Dict[str, int]:
    monday = date.fromisoformat(week_start_from_value(week_value))
    return {WEEKDAYS[i]: (monday + timedelta(days=i)).day for i in range(7)}


def list_employees_with_prefs() -> List[tuple]:
    rows = list_employees()
    result = []
    for emp in rows:
        prefs = get_preferences(emp["id"])
        result.append((emp, prefs))
    return result


def filter_by_day_pref(weekday: str, pref: str) -> List[tuple]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT e.*
        FROM employees e
        JOIN preferences p ON e.id = p.employee_id
        WHERE p.weekday = ? AND p.pref = ?
        ORDER BY e.name
        """,
        (weekday, pref),
    )
    employees = cur.fetchall()
    conn.close()
    result = []
    for emp in employees:
        prefs = get_preferences(emp["id"])
        result.append((emp, prefs))
    return result


init_db()


def current_employee() -> Optional[sqlite3.Row]:
    emp_id = session.get("employee_id")
    if not emp_id:
        return None
    return get_employee(emp_id)


@app.context_processor
def inject_current_employee():
    return {"current_employee": current_employee}


def login_required():
    emp = current_employee()
    if not emp:
        flash("Bitte zuerst einloggen.", "error")
        return redirect(url_for("login"))
    return None


@app.route("/")
def index():
    emp = current_employee()
    if emp:
        return redirect(url_for("overview"))
    return redirect(url_for("login"))

@app.route("/planner")
def planner():
    return render_template("planner.html", title="Schichtplan")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        emp_id = request.form.get("employee_id", "").strip()
        if not name or not emp_id:
            flash("Bitte Name und Mitarbeiter-ID eingeben.", "error")
            return render_template("login.html")

        emp = get_employee(emp_id)
        if not emp or emp["name"].strip().lower() != name.lower():
            flash("Login fehlgeschlagen. Name oder ID stimmt nicht.", "error")
            return render_template("login.html")

        session["employee_id"] = emp_id
        first_name = emp["name"].strip().split()[0]
        flash(f"Willkommen, {first_name}!", "success")
        return redirect(url_for("overview"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Erfolgreich ausgeloggt.", "success")
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("admin_gate.html")

    stage = request.form.get("stage", "").strip()
    if stage == "gate":
        admin_pw = request.form.get("admin_password", "").strip()
        if admin_pw != ADMIN_TOKEN:
            flash("Admin-Passwort ist falsch.", "error")
            return render_template("admin_gate.html")
        return render_template("register.html", gate_ok=True)

    if stage == "create":
        if request.form.get("gate_ok") != "1":
            flash("Bitte zuerst das Admin-Passwort eingeben.", "error")
            return render_template("admin_gate.html")
        name = request.form.get("name", "").strip()
        role = request.form.get("role", "").strip()
        contract_type = request.form.get("contract_type", "").strip()
        weekly_hours = request.form.get("weekly_hours", "").strip()
        max_hours_per_day = request.form.get("max_hours_per_day", "").strip()
        can_work_sun = request.form.get("can_work_sun", "").strip()
        hourly_salary = request.form.get("hourly_salary", "").strip()
        if len(name) < 2:
            flash("Name muss mindestens 2 Zeichen haben.", "error")
            return render_template("register.html")
        if role not in ROLES:
            flash("Bitte eine gültige Rolle auswählen.", "error")
            return render_template("register.html")
        if contract_type not in CONTRACT_TYPES:
            flash("Bitte einen gültigen Vertragstyp auswählen.", "error")
            return render_template("register.html")
        if not weekly_hours.isdigit():
            flash("Weekly Hours muss eine Zahl sein.", "error")
            return render_template("register.html")
        if not max_hours_per_day.isdigit():
            flash("Max Hours Per Day muss eine Zahl sein.", "error")
            return render_template("register.html")
        try:
            salary_val = float(hourly_salary.replace(",", "."))
        except Exception:
            flash("Hourly Salary muss eine Zahl sein.", "error")
            return render_template("register.html")
        if can_work_sun not in ["yes", "no"]:
            flash("Bitte Can Work Sun korrekt auswählen.", "error")
            return render_template("register.html")

        emp_id = create_employee(
            name,
            role,
            contract_type,
            int(weekly_hours),
            int(max_hours_per_day),
            1 if can_work_sun == "yes" else 0,
            salary_val,
        )
        flash(f"Mitarbeiter angelegt: {name} (ID: {emp_id})", "success")
        return redirect(url_for("login"))

    return render_template("admin_gate.html")


@app.route("/admin", methods=["GET", "POST"])
def admin():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, role, contract_type, weekly_hours, max_hours_per_day,
               can_work_sun, hourly_salary
        FROM employees
        ORDER BY name
        """
    )
    employees = cur.fetchall()
    conn.close()

    if request.method == "POST":
        admin_pw = request.form.get("admin_password", "").strip()
        if admin_pw != ADMIN_TOKEN:
            flash("Admin-Passwort ist falsch.", "error")
            return render_template("admin_login.html")
        return render_template("admin_panel.html", employees=employees)
    return render_template("admin_login.html")


@app.route("/api/preferences", methods=["GET"])
def api_preferences():
    week_value = request.args.get("week", "").strip() or current_week_value()
    try:
        week_start = week_start_from_value(week_value)
    except Exception:
        week_value = current_week_value()
        week_start = week_start_from_value(week_value)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, role, contract_type, weekly_hours, max_hours_per_day,
               can_work_sun, hourly_salary
        FROM employees
        ORDER BY name
        """
    )
    employees = cur.fetchall()
    conn.close()

    data = []
    for emp in employees:
        slots = get_schedule(emp["id"], week_start)
        data.append(
            {
                "employee_id": emp["id"],
                "name": emp["name"],
                "role": emp["role"],
                "contract_type": emp["contract_type"],
                "weekly_hours": emp["weekly_hours"],
                "max_hours_per_day": emp["max_hours_per_day"],
                "can_work_sun": bool(emp["can_work_sun"]) if emp["can_work_sun"] is not None else None,
                "hourly_salary": emp["hourly_salary"],
                "week_start": week_start,
                "slots": slots,
            }
        )

    resp = jsonify(data)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/employees", methods=["GET", "POST"])
def employees():
    gate = login_required()
    if gate:
        return gate

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if len(name) < 2:
            flash("Name muss mindestens 2 Zeichen haben.", "error")
        else:
            emp_id = create_employee(name)
            flash(f"Mitarbeiter angelegt: {name} ({emp_id})", "success")
            return redirect(url_for("employees"))

    query = request.args.get("q", "").strip()
    rows = search_employees(query if query else None)
    return render_template("employees.html", employees=rows, query=query)


@app.route("/employees/<emp_id>/prefs", methods=["GET", "POST"])
def edit_prefs(emp_id: str):
    gate = login_required()
    if gate:
        return gate

    emp = get_employee(emp_id)
    if not emp:
        flash("Mitarbeiter nicht gefunden.", "error")
        return redirect(url_for("employees"))

    current = get_preferences(emp_id)
    if request.method == "POST":
        new_prefs: Dict[str, str] = dict(current)
        for day in WEEKDAYS:
            val = request.form.get(day)
            if val in PREF_VALUES:
                new_prefs[day] = val
        update_preferences(emp_id, new_prefs)
        flash("Wünsche gespeichert.", "success")
        return redirect(url_for("edit_prefs", emp_id=emp_id))

    return render_template("prefs.html", employee=emp, prefs=current, weekdays=WEEKDAYS)


@app.route("/overview", methods=["GET", "POST"])
def overview():
    gate = login_required()
    if gate:
        return gate

    emp = current_employee()
    if not emp:
        return redirect(url_for("login"))

    week_value = request.values.get("week", "").strip() or current_week_value()
    try:
        week_start = week_start_from_value(week_value)
    except Exception:
        week_value = current_week_value()
        week_start = week_start_from_value(week_value)
    nav = week_nav_values(week_value)
    day_numbers = week_day_numbers(week_value)

    role = emp["role"] or "service"
    role = role if role in SHIFT_WINDOWS else "service"
    allowed_slots = list(SHIFT_WINDOWS[role].keys())

    if request.method == "POST":
        slots = get_schedule(emp["id"], week_start)
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            day = (payload.get("day") or "").strip()
            action = (payload.get("action") or "").strip()
            slot = (payload.get("slot") or "").strip()
            if payload.get("week"):
                try:
                    week_start = week_start_from_value(str(payload.get("week")))
                    slots = get_schedule(emp["id"], week_start)
                except Exception:
                    pass
            if day in WEEKDAYS and action == "set" and slot in allowed_slots:
                current = slots.get(day, "off")
                slots[day] = "off" if current == slot else slot
                save_schedule(emp["id"], week_start, slots)
            return ("", 204)
        else:
            slots: Dict[str, str] = {}
            for day in WEEKDAYS:
                val = request.form.get(day, "off")
                if val not in allowed_slots and val != "off":
                    val = "off"
                slots[day] = val
            save_schedule(emp["id"], week_start, slots)
            flash("Zeiten gespeichert.", "success")
            return redirect(url_for("overview", week=week_value))

    slots = get_schedule(emp["id"], week_start)
    slot_boxes = []
    for slot_key, (start, end, label) in SHIFT_WINDOWS[role].items():
        visible_start = max(start, CAL_START)
        visible_end = min(end, CAL_END)
        if visible_end <= visible_start:
            continue
        top = max(0, visible_start - CAL_START)
        height = max(0, visible_end - visible_start)
        slot_boxes.append(
            {"slot": slot_key, "top": top, "height": height, "label": label}
        )

    return render_template(
        "overview.html",
        weekdays=WEEKDAYS,
        week_value=week_value,
        nav=nav,
        day_numbers=day_numbers,
        role=role,
        slots=slots,
        allowed_slots=allowed_slots,
        slot_boxes=slot_boxes,
        cal_start=CAL_START,
        cal_end=CAL_END,
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
