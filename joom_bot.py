import sqlite3
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
from flask import Flask, request
from dotenv import load_dotenv
import os
import stripe
import requests
import threading
import datetime
import asyncio
import gunicorn

# Load environment variables
load_dotenv(dotenv_path="C:/Users/Ibrahim/Desktop/JOOM/Environment/Development/.env")

# Required environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOYYIBPAY_API_KEY = os.getenv("TOYYIBPAY_API_KEY")
TOYYIBPAY_CATEGORY_CODE = os.getenv("TOYYIBPAY_CATEGORY_CODE")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
GROUP_ID = os.getenv("GROUP_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Added webhook URL
SUCCESS_URL = os.getenv("SUCCESS_URL")
CALLBACK_URL = os.getenv("CALLBACK_URL")

# Ensure all required environment variables are set
if not all([BOT_TOKEN, TOYYIBPAY_API_KEY, TOYYIBPAY_CATEGORY_CODE, STRIPE_API_KEY, GROUP_ID, WEBHOOK_URL, SUCCESS_URL, CALLBACK_URL]):
    raise EnvironmentError("Missing one or more required environment variables.")

# Initialize Stripe
stripe.api_key = STRIPE_API_KEY

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app for webhooks
app = Flask(__name__)

# Initialize Telegram bot
application = ApplicationBuilder().token(BOT_TOKEN).build()

# Function to generate and send group invite link
def generate_invite_link():
    try:
        invite_link = application.bot.create_chat_invite_link(chat_id=GROUP_ID)
        return invite_link.invite_link
    except Exception as e:
        logger.error(f"Failed to generate invite link: {e}")
        return None

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        payload = request.get_json(force=True)
        update = Update.de_json(payload, application.bot)
        asyncio.run(application.process_update(update))
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Internal Server Error", 500

@app.route('/success', methods=['POST'])
def success_callback():
    data = request.form.to_dict()
    logger.info(f"Received success callback: {data}")

    if data.get("status_id") == "1":
        user_id = data.get("order_id").split('_')[1]
        invite_link = generate_invite_link()
        if invite_link:
            application.bot.send_message(chat_id=user_id, text=f"Payment successful! Join the group here: {invite_link}")
        else:
            application.bot.send_message(chat_id=user_id, text="Payment successful, but failed to generate invite link. Contact support.")
    return "Success callback received", 200

async def start(update: Update, context):
    logger.info(f"Received /start command from {update.effective_user.username}")
    await update.message.reply_text("Welcome! Use /subscribe to start your subscription.")

async def subscribe(update: Update, context):
    user = update.message.from_user

    # Generate ToyyibPay Payment Link
    payment_details = {
        "userSecretKey": TOYYIBPAY_API_KEY,
        "categoryCode": TOYYIBPAY_CATEGORY_CODE,
        "billName": "Group Subscription",
        "billDescription": "Subscription for Telegram Group Access",
        "billAmount": "200",  # Amount in cents (RM2.00)
        "billReturnUrl": SUCCESS_URL,
        "billCallbackUrl": CALLBACK_URL,
        "billExternalReferenceNo": f"user_{user.id}_{datetime.datetime.now().timestamp()}",
        "billTo": user.username or "Anonymous",
        "billEmail": "example@example.com",
        "billPhone": "0123456789",
    }
    
    response = requests.post(f"{TOYYIBPAY_BASE_URL}/index.php/api/createBill", data=payment_details)
    toyibpay_link = response.json()[0]["BillCode"] if response.status_code == 200 else None

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
            success_url=SUCCESS_URL,
            cancel_url=os.getenv("CANCEL_URL"),
        )
        stripe_link = session.url
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")

    # Send payment options
    if toyibpay_link or stripe_link:
        message = "Choose your payment method:\n\n"
        if toyibpay_link:
            message += f"1. [Pay with ToyyibPay]({toyibpay_link})\n"
        if stripe_link:
            message += f"2. [Pay with Stripe]({stripe_link})\n"
        await update.message.reply_text(message, parse_mode="Markdown")
    else:
        await update.message.reply_text("Failed to generate payment links. Please try again later.")

# Function to start the bot using webhooks
async def set_webhook():
    await application.bot.set_webhook(url=WEBHOOK_URL)

def run_flask():
    app.run(host='0.0.0.0', port=10000)

def main():
    logging.info("Starting the application...")
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", subscribe))
    asyncio.run(set_webhook())
    application.run_webhook(listen='0.0.0.0', port=10000, webhook_url=WEBHOOK_URL)

if __name__ == "__main__":
    main()
