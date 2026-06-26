import sqlite3
from math import radians, sin, cos, sqrt, atan2
from ground_truth_validator import load_walker_sites

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

walker = [(s['lat'], s['lon']) for s in load_walker_sites()]
db = sqlite3.connect("tfg.db")
rows = db.execute("SELECT h.lat, h.lon FROM hypotheses h WHERE h.status='candidate'").fetchall()
db.close()

for t in [25, 50, 75, 100]:
    hits = sum(1 for lat, lon in rows if min(haversine(lat, lon, w[0], w[1]) for w in walker) < t)
    print(f"<{t} km:  {hits}/{len(rows)}  ({hits/len(rows)*100:.1f}%)")