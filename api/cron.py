from http.server import BaseHTTPRequestHandler
import requests
import os

# Fetch environment variables set in Vercel Dashboard
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_alert(message):
    """Sends notification to your Telegram bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Missing Telegram credentials in environment variables.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
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
    """Fetches market data and checks if Gold hit or wicked through PDH/PDL."""
    if not TWELVEDATA_API_KEY:
        print("Error: Missing TwelveData API Key in environment variables.")
        return

    url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=1day&outputsize=2&apikey={TWELVEDATA_API_KEY}"
    
    try:
        response = requests.get(url, timeout=10).json()

        if "values" not in response:
            print("API Error:", response.get("message", "Failed to retrieve data."))
            return

        values = response["values"]
        
        # Today's active candle
        current_price = float(values[0]["close"]) # Live spot price right now
        today_high = float(values[0]["high"])    # Highest wick today
        today_low = float(values[0]["low"])      # Lowest wick today

        # Yesterday's completed candle
        pdh = float(values[1]["high"])            # Yesterday's High
        pdl = float(values[1]["low"])             # Yesterday's Low

        print(f"Current: ${current_price:.2f} | Today High: ${today_high:.2f} | Today Low: ${today_low:.2f}")
        print(f"PDH: ${pdh:.2f} | PDL: ${pdl:.2f}")

        # Check for PDH crossing or wick spike
        if today_high >= pdh:
            msg = (
                f"🚨 *XAUUSD ALERT: PDH HIT / BROKEN!*\n\n"
                f"📈 *Today's High (Wick):* `${today_high:.2f}`\n"
                f"📌 *Yesterday's High (PDH):* `${pdh:.2f}`\n"
                f"💵 *Current Live Price:* `${current_price:.2f}`"
            )
            send_telegram_alert(msg)

        # Check for PDL crossing or wick spike
        elif today_low <= pdl:
            msg = (
                f"🚨 *XAUUSD ALERT: PDL HIT / BROKEN!*\n\n"
                f"📉 *Today's Low (Wick):* `${today_low:.2f}`\n"
                f"📌 *Yesterday's Low (PDL):* `${pdl:.2f}`\n"
                f"💵 *Current Live Price:* `${current_price:.2f}`"
            )
            send_telegram_alert(msg)

        else:
            print("Status: Price is inside yesterday's range. No alert sent.")

    except Exception as e:
        print(f"Execution Error: {e}")

class handler(BaseHTTPRequestHandler):
    """Vercel Serverless HTTP Handler."""
    def do_GET(self):
        check_gold_levels()
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write('Cron executed successfully'.encode('utf-8'))
        return