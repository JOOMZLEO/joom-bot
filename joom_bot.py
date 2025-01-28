import sqlite3
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
from flask import Flask, request
from dotenv import load_dotenv
import os
import stripe
import threading
import asyncio

# Load environment variables from the specified .env file
load_dotenv(dotenv_path="C:/Users/Ibrahim/Desktop/JOOM/Environment/Development/.env")

# Your bot token and API details from the .env file
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

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
async def start(update: Update, context):
    logging.info(f"/start command received from user: {update.effective_user.id}")
    await update.message.reply_text("Welcome to the bot! Type /subscribe to get started.")

# Define the /subscribe command handler
async def subscribe(update: Update, context):
    logging.info(f"/subscribe command received from user: {update.effective_user.id}")
    await update.message.reply_text(
        "Subscription feature is active! Please provide your details to subscribe."
    )

# Add command handlers to the application
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("subscribe", subscribe))

# Flask route for Telegram webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        payload = request.get_json(force=True)
        if not payload or "message" not in payload or "date" not in payload["message"]:
            logging.error(f"Invalid webhook payload: {payload}")
            return "Invalid payload", 400

        update = Update.de_json(payload, application.bot)
        asyncio.run(application.process_update(update))
        return "OK", 200
    except Exception as e:
        logging.error(f"Exception during webhook processing: {e}")
        return "Internal Server Error", 500

# Function to run the Flask app
def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), debug=False)

# Function to run the Telegram bot
async def run_telegram():
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

# Main function to run Flask and Telegram bot
def main():
    logging.info("Starting the application...")

    # Run Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Run Telegram bot
    asyncio.run(run_telegram())

if __name__ == "__main__":
    main()
