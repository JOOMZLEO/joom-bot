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
import asyncio

# Load environment variables from the specified .env file
load_dotenv(dotenv_path="C:/Users/Ibrahim/Desktop/JOOM/Environment/Development/.env")

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOYYIBPAY_API_KEY = os.getenv("TOYYIBPAY_API_KEY")
TOYYIBPAY_CATEGORY_CODE = os.getenv("TOYYIBPAY_CATEGORY_CODE")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
TOYYIBPAY_BASE_URL = "https://toyyibpay.com"
SUCCESS_URL = os.getenv("SUCCESS_URL")
CALLBACK_URL = os.getenv("CALLBACK_URL")
GROUP_ID = int(os.getenv("GROUP_ID"))

# Initialize Stripe
stripe.api_key = STRIPE_API_KEY

# Logging configuration
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__)

# Telegram bot application setup
application = ApplicationBuilder().token(BOT_TOKEN).build()

# Event loop for async operations
event_loop = asyncio.new_event_loop()

@app.route('/success', methods=['GET', 'POST'])
def success_callback():
    data = request.get_json() if request.is_json else request.form.to_dict()
    logger.info(f"Received success callback: {data}")
    user_id = data.get("custom_field_user_id")  # Example custom field
    if user_id:
        asyncio.run_coroutine_threadsafe(add_user_to_group(int(user_id)), event_loop)
    return "Success callback received", 200

@app.route('/callback', methods=['GET', 'POST'])
def payment_callback():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form.to_dict()
        logger.info(f"Received payment callback: {data}")
        return "Payment callback received", 200
    return "Callback endpoint is running", 200

async def start(update: Update, context):
    logger.info(f"/start command received from user: {update.effective_user.id}")
    await update.message.reply_text("Welcome! Use /subscribe to start your subscription.")

async def subscribe(update: Update, context):
    user = update.message.from_user
    logger.info(f"/subscribe command received from user: {user.id}")

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
        "billReturnUrl": SUCCESS_URL,
        "billCallbackUrl": CALLBACK_URL,
        "billExternalReferenceNo": f"user_{user.id}_{datetime.datetime.now().timestamp()}",
        "billTo": user.username or "Anonymous",
        "billEmail": "example@example.com",
        "billPhone": "0123456789",
        "custom_field_user_id": user.id
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
            line_items=[{
                "price_data": {
                    "currency": "myr",
                    "product_data": {"name": "Group Subscription"},
                    "unit_amount": 200,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=SUCCESS_URL,
            cancel_url=CALLBACK_URL,
            metadata={"user_id": user.id},
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

# Add user to Telegram group
async def add_user_to_group(user_id):
    try:
        await application.bot.add_chat_member(chat_id=GROUP_ID, user_id=user_id)
        logger.info(f"User {user_id} added to group {GROUP_ID}.")
    except Exception as e:
        logger.error(f"Failed to add user {user_id} to group: {e}")

# Run Flask in a separate thread
def run_flask():
    app.run(host="0.0.0.0", port=8000, debug=False)

def main():
    logger.info("Starting the bot application.")

    # Start event loop in a separate thread
    threading.Thread(target=lambda: asyncio.run_coroutine_threadsafe(event_loop.run_forever(), event_loop), daemon=True).start()

    # Run Flask in a separate thread
    threading.Thread(target=run_flask, daemon=True).start()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", subscribe))

    application.run_polling()

if __name__ == "__main__":
    main()
