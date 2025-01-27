import sqlite3
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
from flask import Flask, request
from dotenv import load_dotenv
import os
import stripe
import datetime
import threading

# Load environment variables from the specified .env file
load_dotenv(dotenv_path="C:/Users/Ibrahim/Desktop/JOOM/Environment/Development/.env")

# Your bot token and API details from the .env file
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOYYIBPAY_API_KEY = os.getenv("TOYYIBPAY_API_KEY")
TOYYIBPAY_CATEGORY_CODE = os.getenv("TOYYIBPAY_CATEGORY_CODE")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
TOYYIBPAY_BASE_URL = "https://toyyibpay.com"  # Base URL for ToyyibPay API

# Initialize Stripe
stripe.api_key = STRIPE_API_KEY

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app for handling webhooks
app = Flask(__name__)

@app.route('/success', methods=['GET', 'POST'])
def success_callback():
    data = request.get_json() if request.is_json else request.form.to_dict()
    logger.info(f"Received success callback: {data}")
    return "Success callback received", 200

@app.route('/callback', methods=['GET', 'POST'])
def payment_callback():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form.to_dict()
        logger.info(f"Received payment callback: {data}")
        # Add logic to validate and process the payment
        return "Payment callback received", 200
    return "Callback endpoint is running", 200

async def start(update: Update, context):
    logger.info(f"Received /start command from {update.effective_user.username}")
    await update.message.reply_text("Welcome! Use /subscribe to start your subscription.")

async def subscribe(update, context):
    user = update.message.from_user

    # Step 1: Generate ToyyibPay Payment Link
    toyibpay_link = None
    payment_details = {
        "userSecretKey": TOYYIBPAY_API_KEY,
        "categoryCode": TOYYIBPAY_CATEGORY_CODE,
        "billName": "Group Subscription",
        "billDescription": "Subscription for Telegram Group Access",
        "billPriceSetting": 1,
        "billPayorInfo": 1,
        "billAmount": "200",  # Amount in cents (e.g., RM2.00)
        "billReturnUrl": os.getenv("SUCCESS_URL"),
        "billCallbackUrl": os.getenv("CALLBACK_URL"),
        "billExternalReferenceNo": f"user_{user.id}_{datetime.datetime.now().timestamp()}",
        "billTo": user.username or "Anonymous",
        "billEmail": "example@example.com",
        "billPhone": "0123456789",
    }

    response = requests.post(f"{TOYYIBPAY_BASE_URL}/index.php/api/createBill", data=payment_details)

    if response.status_code == 200:
        try:
            payment_data = response.json()
            if payment_data and isinstance(payment_data, list) and "BillCode" in payment_data[0]:
                bill_code = payment_data[0]["BillCode"]
                toyibpay_link = f"{TOYYIBPAY_BASE_URL}/{bill_code}"
            else:
                logger.error("Unexpected ToyyibPay response.")
        except Exception as e:
            logger.error(f"Error parsing ToyyibPay response: {e}")

    # Step 2: Generate Stripe Payment Link
    stripe_link = None
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "myr",
                        "product_data": {"name": "Group Subscription"},
                        "unit_amount": 200,  # Amount in cents (e.g., RM2.00)
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=os.getenv("SUCCESS_URL"),
            cancel_url=os.getenv("CANCEL_URL"),
        )
        stripe_link = session.url
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")

    # Step 3: Reply with Both Payment Links
    if toyibpay_link or stripe_link:
        message = "Choose your payment method:\n\n"
        if toyibpay_link:
            message += f"1. [Pay with ToyyibPay]({toyibpay_link})\n"
        if stripe_link:
            message += f"2. [Pay with Stripe]({stripe_link})\n"

        await update.message.reply_text(message, parse_mode="Markdown")
    else:
        await update.message.reply_text("Failed to generate payment links. Please try again later.")

# Database setup
def setup_database():
    conn = sqlite3.connect("subscriptions.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            subscription_expiry DATE
        )
    """)
    conn.commit()
    conn.close()

def add_user_to_db(user_id, username):
    conn = sqlite3.connect("subscriptions.db")
    cursor = conn.cursor()
    expiry_date = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    cursor.execute("REPLACE INTO users (user_id, username, subscription_expiry) VALUES (?, ?, ?)",
                   (user_id, username, expiry_date))
    conn.commit()
    conn.close()

def remove_expired_users(bot, group_id):
    conn = sqlite3.connect("subscriptions.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, subscription_expiry FROM users")
    rows = cursor.fetchall()

    for user_id, expiry_date in rows:
        if datetime.datetime.strptime(expiry_date, "%Y-%m-%d") < datetime.datetime.now():
            bot.kick_chat_member(chat_id=group_id, user_id=user_id)
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# Run Flask and Telegram bot concurrently
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=False)

async def run_telegram():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    setup_database()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", subscribe))

    # Set webhook
    logger.info("Setting webhook...")
    await application.bot.set_webhook(url=WEBHOOK_URL)

    logger.info("Running Telegram bot...")
    await application.start()
    await application.updater.start_polling()
    await application.idle()

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_telegram())

if __name__ == "__main__":
    logger.info("Starting the application...")
    main()
