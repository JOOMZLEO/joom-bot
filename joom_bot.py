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

# Load environment variables
load_dotenv(dotenv_path="C:/Users/Ibrahim/Desktop/JOOM/Environment/Development/.env")

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOYYIBPAY_API_KEY = os.getenv("TOYYIBPAY_API_KEY")
TOYYIBPAY_CATEGORY_CODE = os.getenv("TOYYIBPAY_CATEGORY_CODE")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
GROUP_ID = os.getenv("GROUP_ID")
TOYYIBPAY_BASE_URL = "https://toyyibpay.com"
SUCCESS_URL = os.getenv("SUCCESS_URL")
CALLBACK_URL = os.getenv("CALLBACK_URL")

# Validate critical environment variables
required_env_vars = [BOT_TOKEN, TOYYIBPAY_API_KEY, TOYYIBPAY_CATEGORY_CODE, STRIPE_API_KEY, GROUP_ID, SUCCESS_URL, CALLBACK_URL]
if not all(required_env_vars):
    raise EnvironmentError("Missing one or more required environment variables.")

# Initialize Stripe
stripe.api_key = STRIPE_API_KEY

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Telegram bot application
application = ApplicationBuilder().token(BOT_TOKEN).build()

# Generate Telegram invite link
def generate_invite_link():
    try:
        invite_link = application.bot.create_chat_invite_link(chat_id=GROUP_ID)
        logger.info(f"Generated invite link: {invite_link.invite_link}")
        return invite_link.invite_link
    except Exception as e:
        logger.error(f"Failed to generate invite link: {e}")
        return None

@app.route('/success', methods=['GET', 'POST'])
def success_callback():
    data = request.args if request.method == 'GET' else request.form.to_dict()
    logger.info(f"Received success callback: {data}")

    # Validate payment and send invite link
    if data.get("status_id") == "1":  # Assuming '1' indicates success
        order_id = data.get("order_id", "")
        if order_id.startswith("user_"):
            try:
                user_id = int(order_id.split('_')[1])
                invite_link = generate_invite_link()
                if invite_link:
                    application.bot.send_message(chat_id=user_id, text=f"Your payment was successful! Join the group: {invite_link}")
                else:
                    logger.error(f"Failed to send invite link to user {user_id}.")
            except (IndexError, ValueError) as e:
                logger.error(f"Invalid order_id format: {order_id} - {e}")
        else:
            logger.error(f"Invalid order_id: {order_id}")
    return "Success callback received", 200

@app.route('/callback', methods=['GET', 'POST'])
def payment_callback():
    data = request.get_json() if request.is_json else request.form.to_dict()
    logger.info(f"Received payment callback: {data}")
    return "Payment callback received", 200

async def start(update: Update, context):
    logger.info(f"Received /start command from {update.effective_user.username}")
    await update.message.reply_text("Welcome! Use /subscribe to start your subscription.")

async def subscribe(update: Update, context):
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
        "billReturnUrl": SUCCESS_URL,
        "billCallbackUrl": CALLBACK_URL,
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
        )
        stripe_link = session.url
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")

    # Send payment links
    if toyibpay_link or stripe_link:
        message = "Choose your payment method:\n\n"
        if toyibpay_link:
            message += f"1. [Pay with ToyyibPay]({toyibpay_link})\n"
        if stripe_link:
            message += f"2. [Pay with Stripe]({stripe_link})\n"
        await update.message.reply_text(message, parse_mode="Markdown")
    else:
        await update.message.reply_text("Failed to generate payment links. Please try again later.")

# Run Flask
def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), debug=False)

# Main function
def main():
    logger.info("Starting the application...")

    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", subscribe))

    # Start Telegram bot
    application.run_polling()

if __name__ == "__main__":
    main()
