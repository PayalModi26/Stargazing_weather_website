from flask import Flask, request, jsonify, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import sqlite3
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
CORS(app)

OWM_API_KEY = os.environ.get("OWM_API_KEY", "b0bcc52937968dee85aa4fa13176bacf")
WEATHERAPI_KEY = os.environ.get("WEATHERAPI_KEY", "977e65cf240e4be3acd111954260504")

# ── Database: MySQL if configured, otherwise SQLite fallback ─────────────────
USE_MYSQL = all([
    os.environ.get("DB_HOST"),
    os.environ.get("DB_USER"),
    os.environ.get("DB_NAME"),
])

mysql_module = None
if USE_MYSQL:
    try:
        import mysql.connector
        mysql_module = mysql.connector
    except ImportError:
        USE_MYSQL = False

MYSQL_CONFIG = {
    "host": os.environ.get("DB_HOST", ""),
    "user": os.environ.get("DB_USER", ""),
    "password": os.environ.get("DB_PASS", ""),
    "database": os.environ.get("DB_NAME", ""),
}

SQLITE_PATH = os.environ.get(
    "SQLITE_PATH",
    os.path.join("/tmp" if os.path.isdir("/tmp") else os.path.dirname(__file__), "stargazer.db"),
)


def _init_sqlite():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        city_name TEXT NOT NULL,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, city_name),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )""")
    conn.commit()
    return conn


def get_db():
    if USE_MYSQL and mysql_module:
        try:
            conn = mysql_module.connect(**MYSQL_CONFIG)
            return ("mysql", conn)
        except Exception:
            pass
    return ("sqlite", _init_sqlite())


def db_execute(query, params=(), fetch=False, fetch_one=False, commit=False):
    """Unified DB executor that works with both MySQL and SQLite."""
    db_type, conn = get_db()
    try:
        if db_type == "mysql":
            cur = conn.cursor(dictionary=True)
            cur.execute(query, params)
        else:
            q = query.replace("%s", "?").replace("INSERT IGNORE", "INSERT OR IGNORE")
            cur = conn.cursor()
            cur.execute(q, params)

        if commit:
            conn.commit()
            return None
        if fetch_one:
            row = cur.fetchone()
            if db_type == "sqlite" and row:
                return dict(row)
            return row
        if fetch:
            rows = cur.fetchall()
            if db_type == "sqlite":
                return [dict(r) for r in rows]
            return rows
        return None
    finally:
        conn.close()


def calculate_stargazing_score(cloud_cover, aqi, transparency, moon_illumination):
    cloud_score = max(0, 100 - cloud_cover)
    aqi_score = max(0, 100 - (aqi / 5))
    trans_score = ((transparency - 1) / 7) * 100
    moon_score = max(0, 100 - moon_illumination)
    score = (
        cloud_score * 0.35
        + aqi_score * 0.30
        + trans_score * 0.20
        + moon_score * 0.15
    )
    return round(score)


def score_label(score):
    if score >= 80: return "Excellent Night!"
    if score >= 60: return "Good Night!"
    if score >= 40: return "Fair Night"
    if score >= 20: return "Poor Night"
    return "Not Recommended"


def best_viewing_window(sunset_hour, cloud_cover, aqi):
    start = sunset_hour + 1.5
    duration = 3 if (cloud_cover < 30 and aqi < 100) else 2
    end = start + duration
    def fmt(h):
        h = h % 24
        suffix = "AM" if h < 12 else "PM"
        h12 = h if h <= 12 else h - 12
        if h12 == 0: h12 = 12
        return f"{int(h12)}:{int((h % 1) * 60):02d} {suffix}"
    return f"{fmt(start)} – {fmt(end)}"


def visible_objects(score, moon_illumination):
    objects = []
    if score >= 60:
        objects += ["Jupiter", "Saturn", "Mars", "Venus"]
    if score >= 70 and moon_illumination < 50:
        objects += ["Andromeda Galaxy (M31)", "Orion Nebula (M42)", "Pleiades"]
    if score >= 80 and moon_illumination < 25:
        objects += ["Milky Way Core", "Globular Clusters"]
    if moon_illumination > 40:
        objects += ["Lunar craters & maria (great for Moon observation!)"]
    if not objects:
        objects = ["Bright planets only — conditions are challenging tonight"]
    return objects


def fetch_weather_aqi(city):
    geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={OWM_API_KEY}"
    geo = requests.get(geo_url, timeout=8).json()
    if not geo:
        return None, None, None
    lat, lon = geo[0]["lat"], geo[0]["lon"]
    city_name = geo[0].get("name", city)
    country = geo[0].get("country", "")

    w_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OWM_API_KEY}&units=metric"
    w = requests.get(w_url, timeout=8).json()

    a_url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={OWM_API_KEY}"
    a = requests.get(a_url, timeout=8).json()

    f_url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={OWM_API_KEY}&units=metric&cnt=40"
    f = requests.get(f_url, timeout=8).json()

    aqi_val = a["list"][0]["main"]["aqi"] * 50
    components = a["list"][0]["components"]

    sunset_ts = w.get("sys", {}).get("sunset", 0)
    sunset_hour = datetime.utcfromtimestamp(sunset_ts).hour + (w.get("timezone", 0) / 3600)

    weather_data = {
        "city": city_name,
        "country": country,
        "lat": lat,
        "lon": lon,
        "temp": round(w["main"]["temp"]),
        "feels_like": round(w["main"]["feels_like"]),
        "humidity": w["main"]["humidity"],
        "wind_speed": round(w["wind"]["speed"] * 3.6, 1),
        "cloud_cover": w["clouds"]["all"],
        "description": w["weather"][0]["description"].title(),
        "icon": w["weather"][0]["icon"],
        "sunset_hour": sunset_hour,
        "aqi": aqi_val,
        "aqi_level": aqi_level(aqi_val),
        "pm25": round(components.get("pm2_5", 0), 1),
        "pm10": round(components.get("pm10", 0), 1),
        "no2": round(components.get("no2", 0), 1),
        "forecast": parse_forecast(f),
    }
    return weather_data, lat, lon


def aqi_level(aqi):
    if aqi <= 50:
        return {"label": "Good", "color": "#00e400", "advice": "Air quality is excellent. Great for outdoor activities!"}
    if aqi <= 100:
        return {"label": "Moderate", "color": "#ffff00", "advice": "Acceptable. Unusually sensitive people should limit prolonged exertion."}
    if aqi <= 150:
        return {"label": "Unhealthy for Sensitive Groups", "color": "#ff7e00", "advice": "Sensitive groups may experience effects. General public unaffected."}
    if aqi <= 200:
        return {"label": "Unhealthy", "color": "#ff0000", "advice": "Everyone may begin to experience effects. Limit prolonged outdoor exertion."}
    if aqi <= 300:
        return {"label": "Very Unhealthy", "color": "#8f3f97", "advice": "Health alert! Everyone may experience more serious effects."}
    return {"label": "Hazardous", "color": "#7e0023", "advice": "Emergency conditions. Everyone is affected. Avoid all outdoor activity."}


def parse_forecast(f_data):
    daily = {}
    for item in f_data.get("list", []):
        date = item["dt_txt"][:10]
        if date not in daily:
            daily[date] = {"temps": [], "clouds": [], "icons": [], "desc": []}
        daily[date]["temps"].append(item["main"]["temp"])
        daily[date]["clouds"].append(item["clouds"]["all"])
        daily[date]["icons"].append(item["weather"][0]["icon"])
        daily[date]["desc"].append(item["weather"][0]["description"])

    result = []
    for date, vals in list(daily.items())[:5]:
        result.append({
            "date": date,
            "max_temp": round(max(vals["temps"])),
            "min_temp": round(min(vals["temps"])),
            "cloud_avg": round(sum(vals["clouds"]) / len(vals["clouds"])),
            "icon": vals["icons"][len(vals["icons"]) // 2],
            "desc": vals["desc"][len(vals["desc"]) // 2].title(),
        })
    return result


def fetch_astronomy(lat, lon):
    url = f"http://www.7timer.info/bin/astro.php?lon={lon}&lat={lat}&ac=0&unit=metric&output=json&tzshift=0"
    try:
        r = requests.get(url, timeout=10).json()
        d = r["dataseries"][0]
        transparency_map = {1: "Bad", 2: "Poor", 3: "Below Average", 4: "Below Average",
                            5: "Average", 6: "Above Average", 7: "Good", 8: "Excellent"}
        seeing_map = {1: "Bad", 2: "Poor", 3: "Below Average", 4: "Below Average",
                      5: "Average", 6: "Above Average", 7: "Good", 8: "Excellent"}
        return {
            "cloud_cover_7t": d.get("cloudcover", 5) * 12,
            "transparency": d.get("transparency", 4),
            "transparency_str": transparency_map.get(d.get("transparency", 4), "Average"),
            "seeing": d.get("seeing", 4),
            "seeing_str": seeing_map.get(d.get("seeing", 4), "Average"),
            "wind10m": d.get("wind10m", {}).get("speed", 0),
            "lifted_index": d.get("lifted_index", 0),
        }
    except Exception:
        return {"cloud_cover_7t": 50, "transparency": 4, "transparency_str": "Average",
                "seeing": 4, "seeing_str": "Average", "wind10m": 0, "lifted_index": 0}


def fetch_moon(lat, lon):
    url = f"http://api.weatherapi.com/v1/astronomy.json?key={WEATHERAPI_KEY}&q={lat},{lon}&dt={datetime.now().strftime('%Y-%m-%d')}"
    try:
        r = requests.get(url, timeout=8).json()
        astro = r["astronomy"]["astro"]
        return {
            "moon_phase": astro.get("moon_phase", "Unknown"),
            "moon_illumination": int(astro.get("moon_illumination", 50)),
            "moonrise": astro.get("moonrise", "N/A"),
            "moonset": astro.get("moonset", "N/A"),
            "sunrise": astro.get("sunrise", "N/A"),
            "sunset": astro.get("sunset", "N/A"),
        }
    except Exception:
        return {"moon_phase": "Unknown", "moon_illumination": 50,
                "moonrise": "N/A", "moonset": "N/A", "sunrise": "N/A", "sunset": "N/A"}


# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    city = request.args.get("city", "").strip()
    if not city:
        return jsonify({"error": "City name is required"}), 400
    if not OWM_API_KEY:
        return jsonify({"error": "OWM_API_KEY not configured. Set it in Vercel environment variables."}), 500

    weather, lat, lon = fetch_weather_aqi(city)
    if not weather:
        return jsonify({"error": f"City '{city}' not found"}), 404

    astro = fetch_astronomy(lat, lon)
    moon = fetch_moon(lat, lon)

    cloud_cover = weather["cloud_cover"]
    aqi = weather["aqi"]
    transparency = astro["transparency"]
    moon_illumination = moon["moon_illumination"]
    score = calculate_stargazing_score(cloud_cover, aqi, transparency, moon_illumination)

    return jsonify({
        "weather": weather,
        "astronomy": astro,
        "moon": moon,
        "stargazing": {
            "score": score,
            "label": score_label(score),
            "viewing_window": best_viewing_window(weather["sunset_hour"], cloud_cover, aqi),
            "visible_objects": visible_objects(score, moon_illumination),
            "score_breakdown": {
                "cloud_cover": {"weight": "35%", "value": cloud_cover, "unit": "% cloud"},
                "aqi": {"weight": "30%", "value": aqi, "unit": "AQI"},
                "transparency": {"weight": "20%", "value": transparency, "unit": "/8"},
                "moon_phase": {"weight": "15%", "value": moon_illumination, "unit": "% illuminated"},
            },
        },
    })


@app.route("/api/register", methods=["POST"])
def register():
    data = request.json
    if not data or not data.get("username") or not data.get("password") or not data.get("email"):
        return jsonify({"error": "username, email, and password required"}), 400
    try:
        db_execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
            (data["username"], data["email"], generate_password_hash(data["password"])),
            commit=True,
        )
        return jsonify({"message": "Registered successfully"})
    except Exception:
        return jsonify({"error": "Username or email already exists"}), 409


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    user = db_execute(
        "SELECT * FROM users WHERE username = %s",
        (data.get("username"),),
        fetch_one=True,
    )
    if user and check_password_hash(user["password_hash"], data.get("password", "")):
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return jsonify({"message": "Logged in", "username": user["username"]})
    return jsonify({"error": "Invalid credentials"}), 401


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@app.route("/api/favorites", methods=["GET", "POST", "DELETE"])
def favorites():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    if request.method == "GET":
        favs = db_execute(
            "SELECT * FROM favorites WHERE user_id = %s",
            (session["user_id"],),
            fetch=True,
        )
        return jsonify(favs)

    if request.method == "POST":
        city = request.json.get("city")
        db_execute(
            "INSERT IGNORE INTO favorites (user_id, city_name) VALUES (%s, %s)",
            (session["user_id"], city),
            commit=True,
        )
        return jsonify({"message": f"{city} added to favorites"})

    if request.method == "DELETE":
        city = request.json.get("city")
        db_execute(
            "DELETE FROM favorites WHERE user_id = %s AND city_name = %s",
            (session["user_id"], city),
            commit=True,
        )
        return jsonify({"message": f"{city} removed from favorites"})
