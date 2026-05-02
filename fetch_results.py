"""
Fetch parkrun results for athlete 5332183, plot a time-series line chart,
and save it as chart.png (referenced by README.md).
"""

import re
from datetime import date
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
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


def plot_results(rows: list[tuple], output: Path = Path("chart.png"), y_min: float = 18, y_max: float | None = None) -> None:
    events = sorted({r[0] for r in rows})
    colours = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    event_colour = {e: colours[i % len(colours)] for i, e in enumerate(events)}

    all_dates = [r[1] for r in rows]
    all_times = [r[3] / 60 for r in rows]  # seconds → minutes

    fig, ax = plt.subplots(figsize=(14, 6))

    for event in events:
        colour = event_colour[event]
        event_rows = [r for r in rows if r[0] == event]
        dates = [r[1] for r in event_rows]
        times = [r[3] / 60 for r in event_rows]
        ax.scatter(dates, times, color=colour, s=40, zorder=2, label=event)

    # X axis: one tick per year, minor ticks every month
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_minor_locator(mdates.MonthLocator())
    ax.set_xlim(min(all_dates), max(all_dates))
    ax.set_ylim(bottom=y_min, top=y_max)

    # Y axis: MM:SS labels
    def fmt_mins(val, _):
        m, s = divmod(int(round(val * 60)), 60)
        return f"{m}:{s:02d}"

    ax.yaxis.set_major_formatter(plt.FuncFormatter(fmt_mins))

    ax.set_xlabel("Date")
    ax.set_ylabel("Time")
    ax.set_title("Parkrun times")
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    # Deduplicate legend entries (one per event, not one per scatter call)
    handles, labels = ax.get_legend_handles_labels()
    seen = {}
    for h, l in zip(handles, labels):
        seen.setdefault(l, h)
    ax.legend(seen.values(), seen.keys(), loc="upper left", bbox_to_anchor=(1.01, 1), borderaxespad=0)

    fig.tight_layout()
    fig.savefig(output, dpi=150)
    print(f"Chart saved to {output}")


if __name__ == "__main__":
    rows = fetch_results()
    plot_results(rows, output=Path("chart_all.png"))
    plot_results(rows, output=Path("chart_focused.png"), y_max=24, y_min=19)
