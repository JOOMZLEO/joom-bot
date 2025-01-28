import sqlite3
import logging
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from flask import Flask, request
from dotenv import load_dotenv
import os
import stripe
import threading
import asyncio
import requests

# Load environment variables from the specified .env file
load_dotenv(dotenv_path="C:/Users/Ibrahim/Desktop/JOOM/Environment/Development/.env")

# Your bot token and API details from the .env file
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GROUP_ID = os.getenv("GROUP_ID")
TOYYIBPAY_API_KEY = os.getenv("TOYYIBPAY_API_KEY")
TOYYIBPAY_CATEGORY_CODE = os.getenv("TOYYIBPAY_CATEGORY_CODE")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")

# Flask app setup
app = Flask(__name__)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Initialize the Telegram bot application
application = ApplicationBuilder().token(BOT_TOKEN).build()

# Define the /start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"/start command received from user: {update.effective_user.id}")
    await update.message.reply_text("Welcome to the bot! Type /subscribe to get started.")

# Define the /subscribe command handler
async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"/subscribe command received from user: {update.effective_user.id}")
    payment_message = (
        "Choose your payment method:\n"
        "1. [Pay with ToyyibPay](https://sandbox.toyyibpay.com/{TOYYIBPAY_CATEGORY_CODE})\n"
        "2. [Pay with Stripe](https://stripe.com/paylink)\n"
        "Once payment is confirmed, you will be added to the group."
    )
    await update.message.reply_text(payment_message, parse_mode="Markdown")

# Function to handle payment confirmation
async def handle_payment_confirmation(user_id):
    try:
        bot = Bot(BOT_TOKEN)
        await bot.add_chat_members(chat_id=GROUP_ID, user_ids=[user_id])
        logging.info(f"User {user_id} added to group {GROUP_ID}")
    except Exception as e:
        logging.error(f"Failed to add user {user_id} to group {GROUP_ID}: {e}")

# Define the webhook for payment confirmation
@app.route('/toyyibpay/callback', methods=['POST'])
def toyyibpay_callback():
    try:
        data = request.json
        user_id = data.get('user_id')
        if user_id:
            asyncio.run_coroutine_threadsafe(handle_payment_confirmation(user_id), event_loop)
            return "OK", 200
        return "Invalid payload", 400
    except Exception as e:
        logging.error(f"Error in ToyyibPay callback: {e}")
        return "Internal Server Error", 500

@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    try:
        payload = request.get_data(as_text=True)
        sig_header = request.headers.get('Stripe-Signature')
        event = None

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, os.getenv("STRIPE_WEBHOOK_SECRET")
            )
        except ValueError as e:
            logging.error(f"Invalid payload: {e}")
            return "Invalid payload", 400
        except stripe.error.SignatureVerificationError as e:
            logging.error(f"Invalid signature: {e}")
            return "Invalid signature", 400

        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            user_id = session.get('metadata', {}).get('user_id')
            if user_id:
                asyncio.run_coroutine_threadsafe(handle_payment_confirmation(user_id), event_loop)
        return "OK", 200
    except Exception as e:
        logging.error(f"Error in Stripe webhook: {e}")
        return "Internal Server Error", 500

# Add command handlers to the application
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("subscribe", subscribe))

# Global event loop for running async tasks
event_loop = asyncio.new_event_loop()

# Flask route for Telegram webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        payload = request.get_json(force=True)
        if not payload or "message" not in payload or "date" not in payload["message"]:
            logging.error(f"Invalid webhook payload: {payload}")
            return "Invalid payload", 400

        update = Update.de_json(payload, application.bot)
        asyncio.run_coroutine_threadsafe(application.process_update(update), event_loop)
        return "OK", 200
    except Exception as e:
        logging.error(f"Exception during webhook processing: {e}")
        return "Internal Server Error", 500

# Function to set the webhook URL
async def set_webhook():
    await application.bot.set_webhook(url=WEBHOOK_URL)

# Function to run the Flask app
def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), debug=False)

# Function to run the Telegram bot
async def run_telegram():
    await application.initialize()
    await application.start()
    await set_webhook()

# Function to start the event loop
def start_event_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

# Main function to run Flask and Telegram bot
def main():
    logging.info("Starting the application...")

    # Start the event loop in a separate thread
    event_loop_thread = threading.Thread(target=start_event_loop, args=(event_loop,))
    event_loop_thread.start()

    # Run Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Run Telegram bot
    asyncio.run(run_telegram())

if __name__ == "__main__":
    main()
