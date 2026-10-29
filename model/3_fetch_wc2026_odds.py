import json
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parent / "project.env")
API_KEY = os.environ.get("ODDS_API_KEY")

url = "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds/"

params = {
    'regions': 'eu',
    'markets': 'h2h',
    'oddsFormat': 'decimal',
    'apiKey': API_KEY
}

response = requests.get(url, params=params)
data = response.json()

rows = []
for match in data:
    home_team = match['home_team']
    away_team = match['away_team']
    bookmakers = match.get('bookmakers', [])

    if not bookmakers:
        continue

    pinnacle = next((b for b in bookmakers if b['key'] == 'pinnacle'), None)
    markets = pinnacle['markets'] if pinnacle else bookmakers[0]['markets']

    odds_dict = {outcome['name']: outcome['price'] for outcome in markets[0]['outcomes']}

    home_odds = odds_dict.get(home_team)
    away_odds = odds_dict.get(away_team)
    draw_odds = odds_dict.get('Draw')

    if None in (home_odds, away_odds, draw_odds):
        continue

    rows.append({
        'Home Team': home_team,
        'Away Team': away_team,
        'Home': home_odds,
        'Draw': draw_odds,
        'Away': away_odds
    })

df = pd.DataFrame(rows)
out = Path("./datasets/world_cup_2026/wc2026_odds.csv")
out.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(out, sep=';', index=False)
print(f"Saved {len(df)} matches to {out}")
