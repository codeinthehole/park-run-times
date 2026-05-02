"""
Fetch parkrun results for athlete 5332183 and return a list of tuples:
    (event, date, position, time, is_pb)
"""

import re
import sys
from datetime import date

import requests
from bs4 import BeautifulSoup

ATHLETE_URL = "https://www.parkrun.org.uk/parkrunner/5332183/all/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def parse_time(time_str: str) -> int:
    """Convert MM:SS time string to total seconds."""
    parts = time_str.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    raise ValueError(f"Unrecognised time format: {time_str!r}")


def parse_date(date_str: str) -> date:
    """Parse parkrun date string e.g. '01/01/2022' or '2022-01-01'."""
    date_str = date_str.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            from datetime import datetime
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {date_str!r}")


def fetch_results(session: requests.Session | None = None) -> list[tuple]:
    """
    Returns a list of (event, run_date, position, time_seconds, is_pb) tuples,
    sorted by date ascending.
    """
    s = session or requests.Session()
    response = s.get(ATHLETE_URL, headers=HEADERS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # The run history is the sortable results table (has an "Event" column header)
    table = None
    for t in soup.find_all("table", {"id": "results"}):
        header_cells = t.find("tr").find_all(["th", "td"])
        if any("event" in c.get_text(strip=True).lower() for c in header_cells):
            table = t
            break
    if table is None:
        raise RuntimeError("Could not find run history table in page")

    # Determine column indices from the header row
    header_row = table.find("tr")
    headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

    def col(name: str, *aliases: str) -> int | None:
        candidates = [name, *aliases]
        for i, h in enumerate(headers):
            if any(c in h for c in candidates):
                return i
        return None

    idx_event    = col("event")
    idx_date     = col("date", "run date")
    idx_position = col("pos", "position")
    idx_time     = col("time")
    idx_pb       = col("pb")

    for name, idx in (("event", idx_event), ("date", idx_date), ("pos", idx_position), ("time", idx_time)):
        if idx is None:
            raise RuntimeError(f"Column {name!r} not found in headers: {headers}")

    results = []
    for row in table.find_all("tr")[1:]:  # skip header
        cells = row.find_all(["td", "th"])
        if len(cells) <= max(idx_event, idx_date, idx_position, idx_time):
            continue

        event    = cells[idx_event].get_text(strip=True)
        run_date = parse_date(cells[idx_date].get_text(strip=True))
        position = int(re.sub(r"\D", "", cells[idx_position].get_text(strip=True)))
        time_s   = parse_time(cells[idx_time].get_text(strip=True))

        # PB? column contains "PB" when it's a personal best
        if idx_pb is not None:
            is_pb = bool(cells[idx_pb].get_text(strip=True))
        else:
            row_classes = row.get("class", [])
            is_pb = "pb" in [c.lower() for c in row_classes]

        results.append((event, run_date, position, time_s, is_pb))

    results.sort(key=lambda r: r[1])
    return results


if __name__ == "__main__":
    rows = fetch_results()
    print(f"{'Event':<30} {'Date':<12} {'Pos':>4} {'Time':>6} {'PB'}")
    print("-" * 60)
    for event, run_date, position, time_s, is_pb in rows:
        mins, secs = divmod(time_s, 60)
        print(
            f"{event:<30} {run_date!s:<12} {position:>4} "
            f"{mins:02d}:{secs:02d}  {'*' if is_pb else ''}"
        )
    print(f"\n{len(rows)} results")
