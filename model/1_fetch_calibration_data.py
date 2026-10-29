"""
Fetch historical international tournament odds from the-odds-api.com
for calibrating alpha and beta in the logistic regression betting model.

Covers: World Cup 2022, Euro 2020/2021, Euro 2024, Copa America 2021/2024

How it works:
  Odds  — the-odds-api.com historical endpoint, walking day by day through
           each tournament to collect Pinnacle h2h odds at ~kickoff time.
  Scores — martj42/international_results GitHub dataset (free CSV covering
            all international results since 1872). Downloaded once and cached.

Output: ./datasets/world_cup_2026/international_odds_calibration.csv
Columns: HomeTeam, AwayTeam, FTHG, FTAG, PSH, PSD, PSA,
         Home Open, Draw Open, Away Open, Stage
"""

import csv
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "project.env")
API_KEY = os.environ.get("ODDS_API_KEY")
BASE_URL = "https://api.the-odds-api.com/v4"
RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
RESULTS_CACHE = Path("./datasets/world_cup_2026/international_results_cache.csv")

# Sport keys validated against the-odds-api.com docs.
# If a key returns "Unknown sport", run check_available_tournaments.py to find the correct one.
TOURNAMENTS = [
    {
        "sport": "soccer_fifa_world_cup",
        "name": "World Cup 2022",
        "start": "2022-11-20",
        "end":   "2022-12-18",
    },
    {
        "sport": "soccer_fifa_world_cup",
        "name": "World Cup 2018",
        "start": "2022-11-20",
        "end":   "2022-12-18",
    },
    {
        "sport": "soccer_fifa_world_cup",
        "name": "World Cup 2014",
        "start": "2022-11-20",
        "end":   "2022-12-18",
    },
]

FIELDNAMES = [
    "HomeTeam", "AwayTeam", "FTHG", "FTAG",
    "PSH", "PSD", "PSA",
    "Home Open", "Draw Open", "Away Open",
    "Stage",
]
OUTPUT_FILE = "./datasets/world_cup_2026/international_odds_calibration_wc_data_only.csv"


# ── Results ──────────────────────────────────────────────────────────────────

def load_results_df():
    """Download martj42 international results CSV (cached locally)."""
    if not RESULTS_CACHE.exists():
        print("Downloading international results dataset...")
        resp = requests.get(RESULTS_URL, timeout=30)
        resp.raise_for_status()
        RESULTS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_CACHE.write_text(resp.text, encoding="utf-8")
        print(f"  Saved to {RESULTS_CACHE}")

    df = pd.read_csv(RESULTS_CACHE)
    df["date"] = pd.to_datetime(df["date"])
    return df


def lookup_score(results_df, home, away, commence_time):
    """
    Find the full-time score for a match in the martj42 dataset.
    Returns (home_goals, away_goals) or (None, None) if not found.

    Tries exact match first, then swapped home/away, then partial name match.
    Also tries the previous UTC date because tournaments hosted in the Americas
    (e.g. Copa América in the USA) have evening kickoffs that fall on the next
    UTC date vs the local match date stored in the results dataset.
    """
    utc_date = commence_time[:10]
    prev_date = (datetime.strptime(utc_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    candidate_dates = [utc_date, prev_date]

    def _score(row, flipped=False):
        try:
            h, a = int(row["home_score"]), int(row["away_score"])
            return (a, h) if flipped else (h, a)
        except (ValueError, TypeError):
            return None, None

    def _search(day):
        # Exact
        exact = day[(day["home_team"] == home) & (day["away_team"] == away)]
        if not exact.empty:
            return _score(exact.iloc[0])
        # Swapped home/away
        swapped = day[(day["home_team"] == away) & (day["away_team"] == home)]
        if not swapped.empty:
            return _score(swapped.iloc[0], flipped=True)
        # Partial name match (handles e.g. "USA" vs "United States")
        for _, row in day.iterrows():
            if (home in row["home_team"] or row["home_team"] in home) and \
               (away in row["away_team"] or row["away_team"] in away):
                return _score(row)
            if (away in row["home_team"] or row["home_team"] in away) and \
               (home in row["away_team"] or row["away_team"] in home):
                return _score(row, flipped=True)
        return None, None

    for date_str in candidate_dates:
        day = results_df[results_df["date"].dt.strftime("%Y-%m-%d") == date_str]
        h, a = _search(day)
        if h is not None:
            return h, a

    return None, None


# ── Odds ─────────────────────────────────────────────────────────────────────

def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def historical_odds_snapshot(sport, timestamp):
    """Return the data array from a historical odds snapshot, or [] on failure."""
    url = f"{BASE_URL}/historical/sports/{sport}/odds"
    params = {
        "apiKey": API_KEY,
        "date": timestamp,
        "regions": "eu",
        "markets": "h2h",
        "bookmakers": "pinnacle",
        "oddsFormat": "decimal",
    }
    resp = requests.get(url, params=params)
    if resp.status_code == 429:
        print("  Rate limited — waiting 60s...")
        time.sleep(60)
        return historical_odds_snapshot(sport, timestamp)
    if resp.status_code != 200:
        print(f"  Snapshot {timestamp} failed ({resp.status_code}): {resp.text[:120]}")
        return []
    return resp.json().get("data", [])


def extract_pinnacle(event):
    """Return (home_odds, draw_odds, away_odds) from Pinnacle h2h, or None."""
    home, away = event["home_team"], event["away_team"]
    for bk in event.get("bookmakers", []):
        if bk["key"] == "pinnacle":
            for mkt in bk.get("markets", []):
                if mkt["key"] == "h2h":
                    o = {x["name"]: x["price"] for x in mkt["outcomes"]}
                    h, d, a = o.get(home), o.get("Draw"), o.get(away)
                    if None not in (h, d, a):
                        return h, d, a
    return None


def discover_events(sport, start_date, end_date):
    """
    Walk day by day querying at noon UTC. Returns dict keyed by event_id:
      { home, away, commence_time, opening_odds }
    Opening odds are captured from the first snapshot the event appears in.
    """
    events = {}
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    while current <= end + timedelta(days=1):
        ts = fmt_dt(current.replace(hour=12, minute=0, second=0))
        for ev in historical_odds_snapshot(sport, ts):
            eid = ev["id"]
            if eid not in events:
                events[eid] = {
                    "home": ev["home_team"],
                    "away": ev["away_team"],
                    "commence_time": ev["commence_time"],
                    "opening_odds": extract_pinnacle(ev),
                }
        time.sleep(0.3)
        current += timedelta(days=1)

    return events


def get_closing_odds(sport, event_id, commence_time):
    """Query at kickoff-1min and find this event in the response."""
    kickoff = datetime.fromisoformat(commence_time.replace("Z", ""))
    ts = fmt_dt(kickoff - timedelta(minutes=1))
    for ev in historical_odds_snapshot(sport, ts):
        if ev["id"] == event_id:
            return extract_pinnacle(ev)
    return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not API_KEY:
        raise RuntimeError("ODDS_API_KEY not set — add it to project.env")

    results_df = load_results_df()
    os.makedirs("./data", exist_ok=True)
    total = 0

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for t in TOURNAMENTS:
            print(f"\n--- {t['name']} ---")

            print("  Phase 1: discovering events and opening odds...")
            events = discover_events(t["sport"], t["start"], t["end"])
            print(f"  Found {len(events)} unique events")

            for eid, ev in events.items():
                home, away = ev["home"], ev["away"]

                fthg, ftag = lookup_score(results_df, home, away, ev["commence_time"])
                if fthg is None:
                    print(f"  skip {home} vs {away} — score not found in results dataset")
                    continue

                closing = get_closing_odds(t["sport"], eid, ev["commence_time"])
                time.sleep(0.5)

                if closing is None:
                    print(f"  skip {home} vs {away} — no Pinnacle closing odds")
                    continue

                psh, psd, psa = closing
                opening = ev["opening_odds"]
                open_h, open_d, open_a = opening if opening else (None, None, None)

                writer.writerow({
                    "HomeTeam": home,
                    "AwayTeam": away,
                    "FTHG": fthg,
                    "FTAG": ftag,
                    "PSH": psh,
                    "PSD": psd,
                    "PSA": psa,
                    "Home Open": open_h,
                    "Draw Open": open_d,
                    "Away Open": open_a,
                    "Stage": 1,
                })
                print(f"  ✓ {home} {fthg}-{ftag} {away}")
                total += 1

    print(f"\nDone. {total} matches written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
