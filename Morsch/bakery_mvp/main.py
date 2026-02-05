"""CLI für Arbeitswünsche in der Bäckerei (MVP)."""
from __future__ import annotations

import sys
from typing import Dict, Optional

import db
from models import WEEKDAYS, PREF_VALUES, format_prefs_compact, normalize_pref, parse_filter_day, parse_filter_pref, validate_name, validate_pref


def prompt(text: str) -> str:
    return input(text)


def print_header(title: str) -> None:
    print("\n" + "=" * 50)
    print(title)
    print("=" * 50)


def choose_from_list(items: list, label_fn) -> Optional[int]:
    if not items:
        return None
    for idx, item in enumerate(items, start=1):
        print(f"({idx}) {label_fn(item)}")
    while True:
        choice = prompt("Auswahl (Nummer) oder Enter zum Abbrechen: ").strip()
        if choice == "":
            return None
        if not choice.isdigit() or not (1 <= int(choice) <= len(items)):
            print("Ungültige Auswahl. Bitte eine Nummer aus der Liste wählen.")
            continue
        return int(choice) - 1


def select_employee(conn) -> Optional[str]:
    print_header("Mitarbeiter auswählen")
    query = prompt("Suche nach Name oder ID (Teilstring, Enter = alle): ").strip()
    results = db.search_employees(conn, query if query != "" else None)
    if not results:
        print("Keine Treffer.")
        return None
    if len(results) == 1:
        emp = results[0]
        print(f"Ausgewählt: {emp['name']} ({emp['id']})")
        return emp["id"]
    idx = choose_from_list(results, lambda e: f"{e['name']} ({e['id']})")
    if idx is None:
        return None
    emp = results[idx]
    print(f"Ausgewählt: {emp['name']} ({emp['id']})")
    return emp["id"]


def create_employee(conn) -> Optional[str]:
    print_header("Mitarbeiter neu anlegen")
    while True:
        name = prompt("Name: ")
        res = validate_name(name)
        if not res.ok:
            print(res.message)
            continue
        emp_id = db.create_employee(conn, name)
        print(f"Mitarbeiter angelegt: {name.strip()} (ID: {emp_id})")
        return emp_id


def edit_preferences(conn, emp_id: str) -> None:
    emp = db.get_employee(conn, emp_id)
    if emp is None:
        print("Mitarbeiter nicht gefunden.")
        return
    print_header(f"Arbeitswünsche bearbeiten – {emp['name']} ({emp['id']})")
    current = db.get_preferences(conn, emp_id)
    print("Aktuelle Werte:")
    for day in WEEKDAYS:
        print(f"  {day}: {current.get(day, '-')}")
    print("\nEingabe pro Tag (no/yes/prefer), Enter = unverändert")

    new_prefs: Dict[str, str] = dict(current)
    for day in WEEKDAYS:
        while True:
            raw = prompt(f"{day} [{current[day]}]: ")
            norm = normalize_pref(raw)
            if norm is None:
                break
            if norm == "__invalid__":
                print("Ungültige Eingabe. Erlaubt: no/yes/prefer oder Enter.")
                continue
            new_prefs[day] = norm
            break

    db.update_preferences(conn, emp_id, new_prefs)
    print("Wünsche gespeichert.")


def show_overview(conn) -> None:
    print_header("Übersicht")
    filter_day_raw = prompt("Optionaler Filter – Wochentag (Mo/Di/…/So, Enter = kein Filter): ")
    if filter_day_raw.strip() != "":
        day = parse_filter_day(filter_day_raw)
        if not day:
            print("Ungültiger Wochentag. Kein Filter angewendet.")
            day = None
    else:
        day = None

    if day:
        pref_raw = prompt("Filter – Präferenz (no/yes/prefer): ")
        pref = parse_filter_pref(pref_raw)
        if not pref:
            print("Ungültige Präferenz. Kein Filter angewendet.")
            pref = None
    else:
        pref = None

    if day and pref:
        rows = db.filter_by_day_pref(conn, day, pref)
        if not rows:
            print("Keine Treffer.")
            return
        for emp, prefs in rows:
            print(f"- {emp['name']} ({emp['id']}): {format_prefs_compact(prefs)}")
        return

    rows = db.list_employees_with_prefs(conn)
    if not rows:
        print("Keine Mitarbeiter vorhanden.")
        return
    for emp, prefs in rows:
        print(f"- {emp['name']} ({emp['id']}): {format_prefs_compact(prefs)}")


def main() -> None:
    conn = db.get_conn()
    db.init_db(conn)

    selected_emp_id: Optional[str] = None

    while True:
        print_header("Bäckerei – Arbeitswünsche (MVP)")
        if selected_emp_id:
            emp = db.get_employee(conn, selected_emp_id)
            selected_label = f"{emp['name']} ({emp['id']})" if emp else "(ungültig)"
        else:
            selected_label = "(keiner)"
        print(f"Aktueller Mitarbeiter: {selected_label}")
        print("\nMenü:")
        print("(1) Mitarbeiter auswählen / suchen")
        print("(2) Mitarbeiter neu anlegen")
        print("(3) Arbeitswünsche bearbeiten")
        print("(4) Übersicht anzeigen")
        print("(5) Beenden")

        choice = prompt("Auswahl: ").strip()
        if choice == "1":
            selected_emp_id = select_employee(conn)
        elif choice == "2":
            selected_emp_id = create_employee(conn)
        elif choice == "3":
            if not selected_emp_id:
                print("Bitte zuerst einen Mitarbeiter auswählen.")
                continue
            edit_preferences(conn, selected_emp_id)
        elif choice == "4":
            show_overview(conn)
        elif choice == "5":
            print("Auf Wiedersehen!")
            break
        else:
            print("Ungültige Auswahl. Bitte 1-5 eingeben.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAbbruch durch Benutzer.")
        sys.exit(0)
