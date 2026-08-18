"""
NHL team arena reference data.
Used for computing travel distance and timezone-shift jet lag between games.

tz_offset is STANDARD UTC offset (winter, no DST) in hours, since NHL season
runs Oct-Jun and most of the season is on standard time anyway. Close enough
for a fatigue signal -- not trying to be a routing engine.
"""

# team tri-code -> (lat, lon, utc_offset_hours, arena name)
TEAM_ARENAS = {
    "ANA": (33.8078, -117.8765, -8, "Honda Center"),
    "ARI": (33.5722, -112.0910, -7, "Mullett Arena"),      # update if relocated
    "BOS": (42.3662, -71.0621, -5, "TD Garden"),
    "BUF": (42.8750, -78.8765, -5, "KeyBank Center"),
    "CGY": (51.0374, -114.0519, -7, "Scotiabank Saddledome"),
    "CAR": (35.8033, -78.7219, -5, "Lenovo Center"),
    "CHI": (41.8807, -87.6742, -6, "United Center"),
    "COL": (39.7487, -105.0077, -7, "Ball Arena"),
    "CBJ": (39.9692, -83.0061, -5, "Nationwide Arena"),
    "DAL": (32.7905, -96.8103, -6, "American Airlines Center"),
    "DET": (42.3411, -83.0553, -5, "Little Caesars Arena"),
    "EDM": (53.5469, -113.4973, -7, "Rogers Place"),
    "FLA": (26.1585, -80.3255, -5, "Amerant Bank Arena"),
    "LAK": (34.0430, -118.2673, -8, "Crypto.com Arena"),
    "MIN": (44.9448, -93.1011, -6, "Xcel Energy Center"),
    "MTL": (45.4961, -73.5693, -5, "Bell Centre"),
    "NSH": (36.1593, -86.7784, -6, "Bridgestone Arena"),
    "NJD": (40.7336, -74.1710, -5, "Prudential Center"),
    "NYI": (40.7229, -73.5904, -5, "UBS Arena"),
    "NYR": (40.7505, -73.9934, -5, "Madison Square Garden"),
    "OTT": (45.2969, -75.9271, -5, "Canadian Tire Centre"),
    "PHI": (39.9012, -75.1720, -5, "Wells Fargo Center"),
    "PIT": (40.4392, -79.9895, -5, "PPG Paints Arena"),
    "SEA": (47.6221, -122.3540, -8, "Climate Pledge Arena"),
    "SJS": (37.3327, -121.9012, -8, "SAP Center"),
    "STL": (38.6266, -90.2026, -6, "Enterprise Center"),
    "TBL": (27.9427, -82.4518, -5, "Amalie Arena"),
    "TOR": (43.6435, -79.3791, -5, "Scotiabank Arena"),
    "VAN": (49.2778, -123.1088, -8, "Rogers Arena"),
    "VGK": (36.1028, -115.1786, -8, "T-Mobile Arena"),
    "WSH": (38.8981, -77.0209, -5, "Capital One Arena"),
    "WPG": (49.8926, -97.1436, -6, "Canada Life Centre"),
    "UTA": (40.7683, -111.9011, -7, "Delta Center"),
}
