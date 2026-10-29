import requests
from dotenv import load_dotenv
import os

from pathlib import Path
load_dotenv(Path(__file__).parent / "project.env")
api_key = os.environ.get("ODDS_API_KEY")

params = {'apiKey': api_key}
response = requests.get("https://api.the-odds-api.com/v4/sports/", params=params)

print("Status:", response.status_code)
data = response.json()
if not isinstance(data, list):
    print("Unexpected response:", data)
else:
    for sport in data:
        if sport.get('group', '').lower() == 'soccer':
            print(f"{sport['key']:<50} {sport['title']}")
