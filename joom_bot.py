import sqlite3
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, JobQueue
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

# Your bot token and API details from the .env file
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOYYIBPAY_API_KEY = os.getenv("TOYYIBPAY_API_KEY")
TOYYIBPAY_CATEGORY_CODE = os.getenv("TOYYIBPAY_CATEGORY_CODE")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
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

# Global event loop for running async tasks
event_loop = asyncio.new_event_loop()

# Thread-safe queue for updates
update_queue = queue.Queue()

# Background task to process updates
async def process_updates():
    while True:
        try:
            # Get the next update from the queue
            update = update_queue.get()
            if update is None:
                break  # Exit if None is received

            # Process the update
            await application.process_update(update)
        except Exception as e:
            logging.error(f"Exception during update processing: {e}")

# Flask route for Telegram webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        payload = request.get_json(force=True)
        if not payload or "message" not in payload or "date" not in payload["message"]:
            logging.error(f"Invalid webhook payload: {payload}")
            return "Invalid payload", 400

        update = Update.de_json(payload, application.bot)
        # Add the update to the queue for processing
        update_queue.put(update)
        return "OK", 200
    except Exception as e:
        logging.error(f"Exception during webhook processing: {e}")
        return "Internal Server Error", 500

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
