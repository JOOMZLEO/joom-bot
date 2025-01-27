import sqlite3
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
from flask import Flask, request
from dotenv import load_dotenv
import os
import requests
import stripe
import datetime
import threading

# Load environment variables
load_dotenv(dotenv_path="C:/Users/Ibrahim/Desktop/JOOM/Environment/Development/.env")

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOYYIBPAY_API_KEY = os.getenv("TOYYIBPAY_API_KEY")
TOYYIBPAY_CATEGORY_CODE = os.getenv("TOYYIBPAY_CATEGORY_CODE")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
TOYYIBPAY_BASE_URL = "https://toyyibpay.com"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Debug: Log whether the bot token is loaded
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not loaded from .env file. Check the .env file path and ensure it contains the token.")
else:
    print(f"Loaded BOT_TOKEN: {BOT_TOKEN}")

# Initialize Stripe
stripe.api_key = STRIPE_API_KEY

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app for webhook handling
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    """Handle incoming updates from Telegram."""
    if request.method == "POST":
        update_data = request.get_json()
        logger.info(f"Received update: {update_data}")
        application.process_update(Update.de_json(update_data, application.bot))
        return "OK", 200
    return "Invalid request method", 400

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return "OK", 200

async def start(update: Update, context):
    logger.info(f"Received /start command from {update.effective_user.username}")
    await update.message.reply_text("Welcome! Use /subscribe to start your subscription.")

async def subscribe(update, context):
    user = update.message.from_user

    # Generate ToyyibPay Payment Link
    toyibpay_link = None
    payment_details = {
        "userSecretKey": TOYYIBPAY_API_KEY,
        "categoryCode": TOYYIBPAY_CATEGORY_CODE,
        "billName": "Group Subscription",
        "billDescription": "Subscription for Telegram Group Access",
        "billPriceSetting": 1,
        "billPayorInfo": 1,
        "billAmount": "200",
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

    # Generate Stripe Payment Link
    stripe_link = None
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "myr",
                        "product_data": {"name": "Group Subscription"},
                        "unit_amount": 200,
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

    # Reply with Payment Links
    if toyibpay_link or stripe_link:
        message = "Choose your payment method:\n\n"
        if toyibpay_link:
            message += f"1. [Pay with ToyyibPay]({toyibpay_link})\n"
        if stripe_link:
            message += f"2. [Pay with Stripe]({stripe_link})\n"
        await update.message.reply_text(message, parse_mode="Markdown")
    else:
        await update.message.reply_text("Failed to generate payment links. Please try again later.")

def run_flask():
    port = int(os.environ.get("PORT", 8000))  # Use Render's PORT or default to 8000
    app.run(host="0.0.0.0", port=port, debug=False)

async def main():
    # Initialize bot
    logger.info("Initializing bot...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", subscribe))

    # Set webhook
    logger.info("Setting webhook...")
    await application.bot.set_webhook(url=WEBHOOK_URL)

    # Run Flask for webhook handling
    threading.Thread(target=run_flask, daemon=True).start()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
