import os
import json
import requests
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timedelta
import pytz
from upstash_redis import Redis

# Environment Variables
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
KV_REST_API_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
KV_REST_API_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

# Initialize Redis Client
redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN) if UPSTASH_REDIS_REST_URL else None


def get_trading_day_identifier():
    """
    Determines the current trading day date (YYYY-MM-DD).
    Custom trading window: 3:30 AM IST to 2:15 AM IST next day.
    """
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)

    # Hours before 3:30 AM belong to the previous day's trading session
    if now.hour < 3 or (now.hour == 3 and now.minute < 30):
        trading_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        trading_date = now.strftime("%Y-%m-%d")

    return trading_date


def send_telegram_alert(message):
    """Sends notification to your Telegram bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Missing Telegram credentials.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("Telegram alert sent successfully!")
        else:
            print(f"Telegram API Error: {res.text}")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")


def check_gold_levels():
    """Fetches market data and checks if Gold hit PDH/PDL once per day."""
    if not TWELVEDATA_API_KEY:
        print("Error: Missing TwelveData API Key.")
        return "Error: Missing API key"

    if not redis:
        print("Error: Missing Upstash Redis environment variables.")
        return "Error: Missing Redis credentials"

    trading_day = get_trading_day_identifier()
    pdh_alert_key = f"xauusd:pdh_sent:{trading_day}"
    pdl_alert_key = f"xauusd:pdl_sent:{trading_day}"

    # Check state in Redis
    pdh_already_sent = redis.get(pdh_alert_key)
    pdl_already_sent = redis.get(pdl_alert_key)

    # If both PDH and PDL alerts were already sent today, skip API check to save credits
    if pdh_already_sent and pdl_already_sent:
        print(f"Both PDH and PDL alerts already sent for session {trading_day}.")
        return "Already alerted today for both PDH & PDL"

    url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=1day&outputsize=2&apikey={TWELVEDATA_API_KEY}"

    try:
        response = requests.get(url, timeout=10).json()

        if "values" not in response:
            print("API Error:", response.get("message", "Failed to retrieve data."))
            return "API Error"

        values = response["values"]

        # Today's active candle
        current_price = float(values[0]["close"])
        today_high = float(values[0]["high"])
        today_low = float(values[0]["low"])

        # Yesterday's completed candle
        pdh = float(values[1]["high"])
        pdl = float(values[1]["low"])

        print(f"Session: {trading_day} | Live: ${current_price:.2f}")
        print(f"Today High: ${today_high:.2f} | PDH: ${pdh:.2f}")
        print(f"Today Low: ${today_low:.2f} | PDL: ${pdl:.2f}")

        # 1. Check PDH Condition
        if today_high >= pdh and not pdh_already_sent:
            msg = (
                f"🚨 *XAUUSD ALERT: PDH HIT / BROKEN!*\n\n"
                f"📈 *Today's High (Wick):* `${today_high:.2f}`\n"
                f"📌 *Yesterday's High (PDH):* `${pdh:.2f}`\n"
                f"💵 *Current Live Price:* `${current_price:.2f}`\n"
                f"📅 *Trading Session:* `{trading_day}`"
            )
            send_telegram_alert(msg)
            # Set key with 24-hour expiration (86,400 seconds)
            redis.set(pdh_alert_key, "true", ex=86400)
            print("PDH alert sent and logged to Redis.")

        # 2. Check PDL Condition
        if today_low <= pdl and not pdl_already_sent:
            msg = (
                f"🚨 *XAUUSD ALERT: PDL HIT / BROKEN!*\n\n"
                f"📉 *Today's Low (Wick):* `${today_low:.2f}`\n"
                f"📌 *Yesterday's Low (PDL):* `${pdl:.2f}`\n"
                f"💵 *Current Live Price:* `${current_price:.2f}`\n"
                f"📅 *Trading Session:* `{trading_day}`"
            )
            send_telegram_alert(msg)
            # Set key with 24-hour expiration (86,400 seconds)
            redis.set(pdl_alert_key, "true", ex=86400)
            print("PDL alert sent and logged to Redis.")

        return "Check completed"

    except Exception as e:
        print(f"Execution Error: {e}")
        return f"Error: {e}"


class handler(BaseHTTPRequestHandler):
    """Vercel Serverless HTTP Handler."""

    def do_GET(self):
        status = check_gold_levels()
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(f"Cron execution finished: {status}".encode("utf-8"))
        return