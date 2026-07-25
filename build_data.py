"""
FTW Thunder Dashboard — Data Builder
=====================================
Reads raw CSVs organized by TEAM SEASON ("era") and produces
data/tournaments.json and data/season.json for the web dashboard.

FOLDER STRUCTURE (each era gets its own subfolder, name must match exactly):

    data/raw_tournaments/
        11U Spring 2026/
            Tournament Stats - 2026-02-28 PAC Mudbug Classic.csv
            ...
        12U Fall 2026/
            (empty until the season starts)
        12U Spring 2027/
            (empty until the season starts)

    data/raw_season/
        11U Spring 2026/
            Season - 2026-02-28.csv
            ...
        12U Fall 2026/
        12U Spring 2027/

USAGE:
    python3 build_data.py

To add a new era later: add its name to the ERAS list below, create the
matching subfolders, and re-run. No other code changes needed.
"""

import json
import re
import glob
import os
import pandas as pd

# Ordered oldest -> newest. This list controls what shows up in the
# dashboard's season dropdown, even for eras that have no data yet.
ERAS = [
    "11U Spring 2026",
    "12U Fall 2026",
    "12U Spring 2027",
]

RAW_DIR = os.path.join("data", "raw_tournaments")
OUT_FILE = os.path.join("data", "tournaments.json")

SEASON_RAW_DIR = os.path.join("data", "raw_season")
SEASON_OUT_FILE = os.path.join("data", "season.json")

FNAME_RE = re.compile(r"Tournament[ _]Stats[ _]-[ _](\d{4}-\d{2}-\d{2})[ _](.+)\.csv$", re.IGNORECASE)
SEASON_FNAME_RE = re.compile(r"Season[ _]-[ _](\d{4}-\d{2}-\d{2})\.csv$", re.IGNORECASE)


def clean_num(v):
    """Convert GameChanger-style cell to float or None."""
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "-", "N/A", "nan", "NaN"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def pct(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    return round(numerator / denominator * 100, 2)


def extract_row(row):
    """Pull the metrics the dashboard cares about out of one CSV row (player or Totals)."""
    ab = clean_num(row.get("AB"))
    ip = clean_num(row.get("IP"))
    bb1 = clean_num(row.get("BB.1"))  # walks allowed (pitching)
    hhb = clean_num(row.get("HHB"))
    kl = clean_num(row.get("K-L"))
    loo = clean_num(row.get("LOO"))
    bbs = clean_num(row.get("BBS"))

    return {
        # Hitting
        "PA": clean_num(row.get("PA")),
        "AB": ab,
        "AVG": clean_num(row.get("AVG")),
        "OBP": clean_num(row.get("OBP")),
        "QAB%": clean_num(row.get("QAB%")),
        "C%": clean_num(row.get("C%")),
        "HHB": hhb,
        "HHB%": pct(hhb, ab),
        "BA/RISP": clean_num(row.get("BA/RISP")),
        "K-L": kl,
        "K-L%": pct(kl, ab),
        # Pitching
        "IP": ip,
        "S%": clean_num(row.get("S%")),
        "FPS%": clean_num(row.get("FPS%")),
        "FPSO%": clean_num(row.get("FPSO%")),
        "LOO": loo,
        "LOO%": pct(loo, ip),
        "BB": bb1,
        "BBS": bbs,
        "BBS%": pct(bbs, bb1),
        # Fielding
        "TC": clean_num(row.get("TC")),
        "FPCT": clean_num(row.get("FPCT")),
    }


def parse_gamechanger_csv(path):
    df = pd.read_csv(path, header=1)
    df.columns = df.columns.astype(str).str.strip()
    df = df.dropna(how="all")

    totals_mask = df["Number"] == "Totals"
    team_row = df[totals_mask]
    player_rows = df[~totals_mask].copy()
    player_rows = player_rows.dropna(subset=["First", "Last"])

    players = []
    for _, row in player_rows.iterrows():
        player_name = f"{str(row['First']).strip()} {str(row['Last']).strip()}"
        metrics = extract_row(row)
        metrics["name"] = player_name
        players.append(metrics)

    team = extract_row(team_row.iloc[0]) if len(team_row) else {}
    return team, players


def build_tournaments():
    tournaments = []

    for era in ERAS:
        era_dir = os.path.join(RAW_DIR, era)
        if not os.path.isdir(era_dir):
            print(f"ℹ️  No folder yet for era '{era}' — skipping ({era_dir})")
            continue

        files = sorted(glob.glob(os.path.join(era_dir, "*.csv")))
        for path in files:
            fname = os.path.basename(path)
            m = FNAME_RE.match(fname)
            if not m:
                print(f"⚠️  Skipping (name doesn't match pattern): {era}/{fname}")
                continue
            date, raw_name = m.groups()
            name = re.sub(r"_+", " ", raw_name).strip()
            try:
                team, players = parse_gamechanger_csv(path)
                tournaments.append({
                    "id": f"{date}-{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')}",
                    "date": date,
                    "name": name,
                    "era": era,
                    "team": team,
                    "players": players,
                })
                print(f"✅ Parsed tournament [{era}]: {name} ({date}) — {len(players)} players")
            except Exception as e:
                print(f"❌ Error parsing {era}/{fname}: {e}")

    tournaments.sort(key=lambda t: (t["era"], t["date"]))

    os.makedirs("data", exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"eras": ERAS, "tournaments": tournaments}, f, indent=2)

    print(f"✅ Wrote {OUT_FILE} — {len(tournaments)} tournaments across {len(ERAS)} eras\n")


def build_season():
    snapshots = []

    for era in ERAS:
        era_dir = os.path.join(SEASON_RAW_DIR, era)
        if not os.path.isdir(era_dir):
            print(f"ℹ️  No folder yet for era '{era}' — skipping ({era_dir})")
            continue

        files = sorted(glob.glob(os.path.join(era_dir, "*.csv")))
        for path in files:
            fname = os.path.basename(path)
            m = SEASON_FNAME_RE.match(fname)
            if not m:
                print(f"⚠️  Skipping (name doesn't match pattern): {era}/{fname}")
                continue
            (date,) = m.groups()
            try:
                team, players = parse_gamechanger_csv(path)
                snapshots.append({"date": date, "era": era, "team": team, "players": players})
                print(f"✅ Parsed season snapshot [{era}]: {date} — {len(players)} players")
            except Exception as e:
                print(f"❌ Error parsing {era}/{fname}: {e}")

    snapshots.sort(key=lambda s: (s["era"], s["date"]))

    os.makedirs("data", exist_ok=True)
    with open(SEASON_OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"eras": ERAS, "snapshots": snapshots}, f, indent=2)

    print(f"✅ Wrote {SEASON_OUT_FILE} — {len(snapshots)} weekly snapshots across {len(ERAS)} eras\n")


def main():
    build_tournaments()
    build_season()


if __name__ == "__main__":
    main()
