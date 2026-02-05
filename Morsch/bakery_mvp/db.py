"""SQLite-Zugriffsschicht für die Bäckerei-CLI."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from models import WEEKDAYS, PREF_VALUES


DB_FILENAME = "bakery.db"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_conn(db_path: str = DB_FILENAME) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Erstellt Tabellen, falls sie nicht existieren."""
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
    conn.commit()


def create_employee(conn: sqlite3.Connection, name: str) -> str:
    """Legt einen Mitarbeiter an und initialisiert Präferenzen mit 'no'."""
    emp_id = str(uuid.uuid4())
    ts = utc_now_iso()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO employees (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (emp_id, name.strip(), ts, ts),
    )
    cur.executemany(
        "INSERT INTO preferences (employee_id, weekday, pref, updated_at) VALUES (?, ?, ?, ?)",
        [(emp_id, day, "no", ts) for day in WEEKDAYS],
    )
    conn.commit()
    return emp_id


def update_employee_name(conn: sqlite3.Connection, emp_id: str, name: str) -> None:
    ts = utc_now_iso()
    cur = conn.cursor()
    cur.execute(
        "UPDATE employees SET name = ?, updated_at = ? WHERE id = ?",
        (name.strip(), ts, emp_id),
    )
    conn.commit()


def search_employees(conn: sqlite3.Connection, query: Optional[str]) -> List[sqlite3.Row]:
    cur = conn.cursor()
    if query is None or query.strip() == "":
        cur.execute("SELECT * FROM employees ORDER BY name")
        return cur.fetchall()
    q = f"%{query.strip()}%"
    cur.execute(
        "SELECT * FROM employees WHERE id LIKE ? OR name LIKE ? ORDER BY name",
        (q, q),
    )
    return cur.fetchall()


def get_employee(conn: sqlite3.Connection, emp_id: str) -> Optional[sqlite3.Row]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM employees WHERE id = ?", (emp_id,))
    return cur.fetchone()


def list_employees(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM employees ORDER BY name")
    return cur.fetchall()


def get_preferences(conn: sqlite3.Connection, emp_id: str) -> Dict[str, str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT weekday, pref FROM preferences WHERE employee_id = ?",
        (emp_id,),
    )
    rows = cur.fetchall()
    prefs: Dict[str, str] = {row["weekday"]: row["pref"] for row in rows}
    # Sicherstellen, dass alle Tage vorhanden sind
    for day in WEEKDAYS:
        prefs.setdefault(day, "no")
    return prefs


def update_preferences(
    conn: sqlite3.Connection, emp_id: str, new_prefs: Dict[str, str]
) -> None:
    ts = utc_now_iso()
    cur = conn.cursor()
    data = [(new_prefs[day], ts, emp_id, day) for day in WEEKDAYS]
    cur.executemany(
        "UPDATE preferences SET pref = ?, updated_at = ? WHERE employee_id = ? AND weekday = ?",
        data,
    )
    cur.execute("UPDATE employees SET updated_at = ? WHERE id = ?", (ts, emp_id))
    conn.commit()


def list_employees_with_prefs(conn: sqlite3.Connection) -> List[Tuple[sqlite3.Row, Dict[str, str]]]:
    employees = list_employees(conn)
    result: List[Tuple[sqlite3.Row, Dict[str, str]]] = []
    for emp in employees:
        prefs = get_preferences(conn, emp["id"])
        result.append((emp, prefs))
    return result


def filter_by_day_pref(
    conn: sqlite3.Connection, weekday: str, pref: str
) -> List[Tuple[sqlite3.Row, Dict[str, str]]]:
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
    result: List[Tuple[sqlite3.Row, Dict[str, str]]] = []
    for emp in employees:
        prefs = get_preferences(conn, emp["id"])
        result.append((emp, prefs))
    return result
