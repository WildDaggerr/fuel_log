#!/usr/bin/env python3
"""
fuel_log.py — Enkel bränslelogg för bensin/diesel.
Sparar poster i fuel_log.csv och räknar ut förbrukning (l/100 km), kostnad/km m.m.

Kommandon (kör i terminalen):
  python fuel_log.py add --date 2025-08-27 --odometer 210123 --liters 43.2 --price 19.49 --full yes --notes "E20 OKQ8"
  python fuel_log.py list --limit 20
  python fuel_log.py stats
  python fuel_log.py month 2025-08
  python fuel_log.py export fuel_log_export.csv

Förklaring:
- För exakt förbrukning används "tank-till-tank": från senaste FULL till nuvarande FULL.
- Du kan lägga in PARTIAL (t.ex. toppa lite) mellan två FULL — scriptet räknar ihop liter automatiskt.
- Datumformat: ÅÅÅÅ-MM-DD. Odometer i km. Pris per liter i SEK.
"""

import argparse
import csv
import os
from datetime import datetime
from collections import defaultdict

CSV_FILE = "fuel_log.csv"
FIELDNAMES = ["date", "odometer_km", "liters", "price_per_liter_sek", "full_fill", "notes"]

def ensure_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()

def parse_bool(v: str) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"y","yes","true","1","full","f","ja"}

def add_entry(args):
    ensure_csv()
    # Validate inputs
    try:
        dt = datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit("Fel: datum måste vara i formatet ÅÅÅÅ-MM-DD.")
    try:
        odo = float(args.odometer)
        lit = float(args.liters)
        price = float(args.price)
    except ValueError:
        raise SystemExit("Fel: odometer/liters/price måste vara numeriska.")
    full = parse_bool(args.full)
    notes = args.notes or ""

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow({
            "date": dt.isoformat(),
            "odometer_km": f"{odo:.1f}",
            "liters": f"{lit:.3f}",
            "price_per_liter_sek": f"{price:.3f}",
            "full_fill": "yes" if full else "no",
            "notes": notes
        })
    print("✅ Post tillagd.")
    # Efter tillägg: visa ev. ny beräknad cykel
    show_last_cycle_consumption()

def read_rows():
    ensure_csv()
    rows = []
    with open(CSV_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                r["date"] = datetime.strptime(r["date"], "%Y-%m-%d").date()
            except Exception:
                continue
            r["odometer_km"] = float(r["odometer_km"])
            r["liters"] = float(r["liters"])
            r["price_per_liter_sek"] = float(r["price_per_liter_sek"])
            r["full_fill"] = (r["full_fill"].strip().lower() == "yes")
            rows.append(r)
    rows.sort(key=lambda x: (x["date"], x["odometer_km"]))
    return rows

def list_entries(args):
    rows = read_rows()
    if not rows:
        print("Ingen data än.")
        return
    limit = args.limit or 20
    for r in rows[-limit:]:
        total_cost = r["liters"] * r["price_per_liter_sek"]
        print(f'{r["date"]}  {r["odometer_km"]:9.1f} km  {r["liters"]:6.3f} L  '
              f'{r["price_per_liter_sek"]:5.2f} kr/L  {"FULL" if r["full_fill"] else "partial":7}  '
              f'kostnad {total_cost:7.2f} kr  {r["notes"]}')

def cycles(rows):
    """Dela upp i tank-till-tank-cykler (från FULL till FULL). Returnerar lista med dicts."""
    cycles = []
    buffer = []
    last_full = None
    for r in rows:
        buffer.append(r)
        if r["full_fill"]:
            if last_full is None:
                last_full = r
                buffer = [r]  # börja ny buffert
            else:
                # cykeln är allt efter förra full till nuvarande full (inklusive partials + current full)
                cycle_rows = buffer
                # Första i bufferten är förra fullen
                start = cycle_rows[0]
                end = cycle_rows[-1]
                liters_used = sum(x["liters"] for x in cycle_rows[1:])  # allt efter start-full till och med end (som är full)
                distance = end["odometer_km"] - start["odometer_km"]
                total_cost = sum(x["liters"] * x["price_per_liter_sek"] for x in cycle_rows[1:])
                if distance > 0 and liters_used > 0:
                    l_per_100 = liters_used / distance * 100
                    cost_per_km = total_cost / distance
                else:
                    l_per_100 = None
                    cost_per_km = None
                cycles.append({
                    "start_date": start["date"],
                    "end_date": end["date"],
                    "start_odo": start["odometer_km"],
                    "end_odo": end["odometer_km"],
                    "distance_km": distance,
                    "liters_used": liters_used,
                    "l_per_100km": l_per_100,
                    "cost_total_sek": total_cost,
                    "cost_per_km_sek": cost_per_km,
                    "fills_count": len(cycle_rows)-1
                })
                # starta ny cykel från denna full
                last_full = r
                buffer = [r]
    return cycles

def stats(args):
    rows = read_rows()
    if len(rows) < 2:
        print("Lägg till fler poster för statistik.")
        return
    cs = cycles(rows)
    if not cs:
        print("Behöver minst två FULL-tankningar för att räkna förbrukning.")
        return
    # Skriv ut senaste cykeln
    latest = cs[-1]
    print("— Senaste full->full —")
    print(f'{latest["start_date"]} ({latest["start_odo"]:.1f} km)  →  {latest["end_date"]} ({latest["end_odo"]:.1f} km)')
    print(f'Distans: {latest["distance_km"]:.1f} km  |  Liter: {latest["liters_used"]:.3f} L  |  '
          f'Förbrukning: {latest["l_per_100km"]:.2f} L/100km  |  Kostnad: {latest["cost_total_sek"]:.2f} kr  '
          f'({latest["cost_per_km_sek"]:.2f} kr/km)  |  Antal tankningar: {latest["fills_count"]}')
    # Summera alla
    v = [c for c in cs if c["l_per_100km"] is not None]
    avg_l100 = sum(c["l_per_100km"] for c in v) / len(v)
    avg_cost_km = sum(c["cost_per_km_sek"] for c in v) / len(v)
    total_km = sum(c["distance_km"] for c in v)
    total_l = sum(c["liters_used"] for c in v)
    total_cost = sum(c["cost_total_sek"] for c in v)
    print("\n— Totalt (alla cykler) —")
    print(f'Total distans: {total_km:.1f} km  |  Total liter: {total_l:.1f} L  |  Total kostnad: {total_cost:.2f} kr')
    print(f'Medelförbrukning: {avg_l100:.2f} L/100km  |  Snittkostnad: {avg_cost_km:.2f} kr/km')

def month(args):
    rows = read_rows()
    if not rows:
        print("Ingen data än.")
        return
    try:
        y, m = args.ym.split("-")
        y = int(y); m = int(m)
    except Exception:
        raise SystemExit("Ange månad som ÅÅÅÅ-MM, t.ex. 2025-08")
    # summera per månad (baserat på datum för POSTER, inte cykler)
    liters = 0.0
    cost = 0.0
    fills = 0
    for r in rows:
        if r["date"].year == y and r["date"].month == m:
            liters += r["liters"]
            cost += r["liters"] * r["price_per_liter_sek"]
            fills += 1
    print(f"Månad {y}-{m:02d}:")
    print(f"Tankningar: {fills}  |  Liter: {liters:.3f} L  |  Kostnad: {cost:.2f} kr")
    # Frivillig: uppskatta km via cykler som slutar i denna månad
    cs = cycles(rows)
    month_km = sum(c["distance_km"] for c in cs if c["end_date"].year == y and c["end_date"].month == m)
    if month_km > 0:
        print(f"Uppskattad körsträcka (från cykler som slutar denna månad): {month_km:.1f} km")

def export_csv(args):
    ensure_csv()
    dest = args.dest or "fuel_log_export.csv"
    with open(CSV_FILE, "r", newline="", encoding="utf-8") as src, \
         open(dest, "w", newline="", encoding="utf-8") as out:
        out.write(src.read())
    print(f"Exporterade till {dest}")

def show_last_cycle_consumption():
    rows = read_rows()
    cs = cycles(rows)
    if cs:
        latest = cs[-1]
        if latest["l_per_100km"] is not None:
            print("⛽ Ny cykel beräknad:")
            print(f'{latest["start_date"]} → {latest["end_date"]}: {latest["l_per_100km"]:.2f} L/100km '
                  f'({latest["distance_km"]:.1f} km, {latest["liters_used"]:.3f} L, {latest["cost_per_km_sek"]:.2f} kr/km)')

def main():
    parser = argparse.ArgumentParser(description="Enkel bränslelogg (bensin/diesel) med förbrukningsberäkning.")
    sub = parser.add_subparsers(dest="cmd")

    p_add = sub.add_parser("add", help="Lägg till en tankning")
    p_add.add_argument("--date", required=True, help="Datum ÅÅÅÅ-MM-DD")
    p_add.add_argument("--odometer", required=True, help="Mätarställning i km (t.ex. 210123.0)")
    p_add.add_argument("--liters", required=True, help="Tankad volym i liter (t.ex. 43.2)")
    p_add.add_argument("--price", required=True, help="Pris per liter i SEK (t.ex. 19.49)")
    p_add.add_argument("--full", required=True, help="FULL tankning? yes/no")
    p_add.add_argument("--notes", default="", help="Anteckningar (t.ex. station, väg, körning)")
    p_add.set_defaults(func=add_entry)

    p_list = sub.add_parser("list", help="Lista senaste poster")
    p_list.add_argument("--limit", type=int, default=20, help="Antal rader att visa")
    p_list.set_defaults(func=list_entries)

    p_stats = sub.add_parser("stats", help="Visa förbrukning och snitt")
    p_stats.set_defaults(func=stats)

    p_month = sub.add_parser("month", help="Summera en månad (ÅÅÅÅ-MM)")
    p_month.add_argument("ym", help="ÅÅÅÅ-MM")
    p_month.set_defaults(func=month)

    p_export = sub.add_parser("export", help="Exportera CSV")
    p_export.add_argument("dest", nargs="?", help="Filnamn (default fuel_log_export.csv)")
    p_export.set_defaults(func=export_csv)

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return
    args.func(args)

if __name__ == "__main__":
    main()
