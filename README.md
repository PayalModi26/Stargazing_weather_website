# 🔭 StarGaze — Real-Time Weather, AQI & Astronomy Dashboard

## Quick Start

### 1. Get API Keys (free)
| Service | Key needed | Get it at |
|---|---|---|
| OpenWeatherMap | `OWM_API_KEY` | https://openweathermap.org/api (free tier) |
| WeatherAPI | `WEATHERAPI_KEY` | https://www.weatherapi.com (free tier) |
| 7Timer! | none | Works without a key! |

### 2. Set up the database
```bash
mysql -u root -p < schema.sql
```

### 3. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 4. Set environment variables
```bash
# Linux / Mac
export OWM_API_KEY="your_key_here"
export WEATHERAPI_KEY="your_key_here"
export SECRET_KEY="any_random_secret_string"
export DB_HOST="localhost"
export DB_USER="root"
export DB_PASS="your_mysql_password"
export DB_NAME="stargazer_db"

# Windows PowerShell
$env:OWM_API_KEY="your_key_here"
$env:WEATHERAPI_KEY="your_key_here"
```

### 5. Run the app
```bash
python app.py
```
Then open http://localhost:5000

---

## Project Structure
```
stargazer/
├── app.py              # Flask backend — all routes & business logic
├── schema.sql          # MySQL table definitions
├── requirements.txt    # Python dependencies
├── README.md
└── templates/
    └── index.html      # Single-page frontend dashboard
```

## Stargazing Score Formula
| Factor | Weight | Source |
|---|---|---|
| Cloud Cover | 35% | OpenWeatherMap |
| AQI | 30% | OpenWeatherMap Air Pollution API |
| Transparency | 20% | 7Timer! astronomy API |
| Moon Illumination | 15% | WeatherAPI astronomy endpoint |

Score 80–100% → Excellent  |  60–79% → Good  |  40–59% → Fair  |  <40% → Poor

## Team
- **Niva Jain** — Frontend (`templates/index.html`)
- **Payal Modi** — Backend (`app.py` — API integrations, score logic)
- **Aditya Ghorpade** — Database (`schema.sql`, auth routes)
- **Sahish Nagulwar** — Integration, testing, deployment

Guide: **Pranati Waghodekar**