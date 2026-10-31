"""Trim the Swiss GTFS feed to a few reference days so OpenTripPlanner can load it on a laptop.

Usage: python3 data/preprocessing/trim_gtfs.py [data/ref/otp/gtfs.zip] [data/ref/otp/graph/gtfs.zip]
Source: opentransportdata.swiss "Timetable 2026 (GTFS2020)", ~290 MB zip / 3.7 GB stop_times.

Keeps only trips running on DATES (a summer weekend: mountain buses and cable cars run then; the
timetable year is Dec 2025 - Dec 2026). Calendars are rewritten as calendar_dates for those days only.
"""

import csv
import io
import sys
import zipfile
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

DATES = [date(2026, 7, 11), date(2026, 7, 12)]  # Saturday, Sunday

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "data/ref/otp/gtfs.zip")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "data/ref/otp/graph/gtfs.zip")

Columns = dict[str, int]  # header name -> index
Keep = Callable[[list[str], Columns], bool]


def rows(feed: zipfile.ZipFile, name: str) -> Iterator[list[str]]:
    with feed.open(name) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""))
        header = next(reader)
        yield header
        yield from reader


def copy_filtered(feed: zipfile.ZipFile, out: zipfile.ZipFile, name: str, keep: Keep) -> int:
    """Copy `name` keeping rows where keep(row, columns) is true; returns rows kept."""
    it = rows(feed, name)
    header = next(it)
    col = {h: i for i, h in enumerate(header)}
    kept = 0
    with out.open(name, "w") as f, io.TextIOWrapper(f, encoding="utf-8", newline="") as text:
        writer = csv.writer(text)
        writer.writerow(header)
        for row in it:
            if keep(row, col):
                writer.writerow(row)
                kept += 1
    return kept


def active_services(feed: zipfile.ZipFile) -> dict[str, set[date]]:
    days = {d.strftime("%Y%m%d"): d for d in DATES}
    weekday = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    active: dict[str, set[date]] = {}
    it = rows(feed, "calendar.txt")
    col = {h: i for i, h in enumerate(next(it))}
    for row in it:
        for key, d in days.items():
            if (
                row[col["start_date"]] <= key <= row[col["end_date"]]
                and row[col[weekday[d.weekday()]]] == "1"
            ):
                active.setdefault(row[col["service_id"]], set()).add(d)
    it = rows(feed, "calendar_dates.txt")
    col = {h: i for i, h in enumerate(next(it))}
    for row in it:
        d = days.get(row[col["date"]])
        if d is None:
            continue
        service = row[col["service_id"]]
        if row[col["exception_type"]] == "1":
            active.setdefault(service, set()).add(d)
        else:
            active.get(service, set()).discard(d)
    return {s: ds for s, ds in active.items() if ds}


OUT.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(SRC) as feed, zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as out:
    services = active_services(feed)
    print(f"{len(services)} services run on {', '.join(map(str, DATES))}")

    with out.open("calendar_dates.txt", "w") as f, io.TextIOWrapper(f, encoding="utf-8", newline="") as text:
        writer = csv.writer(text)
        writer.writerow(["service_id", "date", "exception_type"])
        for service, ds in services.items():
            writer.writerows([service, d.strftime("%Y%m%d"), "1"] for d in sorted(ds))

    trip_ids: set[str] = set()

    def keep_trip(row: list[str], col: Columns) -> bool:
        if row[col["service_id"]] in services:
            trip_ids.add(row[col["trip_id"]])
            return True
        return False

    print("trips:", copy_filtered(feed, out, "trips.txt", keep_trip))
    print("stop_times:", copy_filtered(feed, out, "stop_times.txt", lambda r, c: r[c["trip_id"]] in trip_ids))
    print(
        "frequencies:", copy_filtered(feed, out, "frequencies.txt", lambda r, c: r[c["trip_id"]] in trip_ids)
    )

    def keep_transfer(row: list[str], col: Columns) -> bool:
        trips = [row[col[k]] for k in ("from_trip_id", "to_trip_id") if k in col]
        return all(t == "" or t in trip_ids for t in trips)

    print("transfers:", copy_filtered(feed, out, "transfers.txt", keep_transfer))
    for name in ("agency.txt", "routes.txt", "stops.txt", "feed_info.txt"):
        out.writestr(name, feed.read(name))

print(f"-> {OUT} ({OUT.stat().st_size / 1e6:.0f} MB)")
