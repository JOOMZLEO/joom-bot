import datetime
import logging
import os
import stripe
import requests
import hmac
import hashlib
import asyncio
from quart import Quart, request, abort
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
from dotenv import load_dotenv
from hypercorn.asyncio import serve
from hypercorn.config import Config

# Load environment variables
load_dotenv()

# Required environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOYYIBPAY_API_KEY = os.getenv("TOYYIBPAY_API_KEY")
TOYYIBPAY_CATEGORY_CODE = os.getenv("TOYYIBPAY_CATEGORY_CODE")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
GROUP_ID = os.getenv("GROUP_ID")
TOYYIBPAY_BASE_URL = "https://toyyibpay.com"
SUCCESS_URL = os.getenv("SUCCESS_URL")
CALLBACK_URL = os.getenv("CALLBACK_URL")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Validate all environment variables
required_env_vars = [BOT_TOKEN, TOYYIBPAY_API_KEY, TOYYIBPAY_CATEGORY_CODE, STRIPE_API_KEY, GROUP_ID, SUCCESS_URL, CALLBACK_URL, STRIPE_WEBHOOK_SECRET]
if not all(required_env_vars):
    raise EnvironmentError("Missing one or more required environment variables.")

# Initialize Stripe
stripe.api_key = STRIPE_API_KEY

# Logging configuration
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Quart app
app = Quart(__name__)

# Telegram bot application
application = ApplicationBuilder().token(BOT_TOKEN).build()

# --- Route: Telegram Webhook ---
@app.route('/webhook', methods=['POST'])
async def telegram_webhook():
    """Handles incoming Telegram updates via webhook."""
    try:
        data = await request.get_json()
        logger.info(f"Received Telegram webhook data: {data}")
        
        if not data:
            logger.error("No data received in webhook.")
            return "No data received", 400
        
        # Process in background
        asyncio.create_task(application.process_update(Update.de_json(data, application.bot)))
        
        return "", 200
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
        return "Internal Server Error", 500

# --- Function: Generate Invite Link ---
async def generate_invite_link():
    """Generate a Telegram invite link for the group."""
    try:
        invite_link = await application.bot.create_chat_invite_link(chat_id=GROUP_ID)
        logger.info(f"Generated invite link: {invite_link.invite_link}")
        return invite_link.invite_link
    except Exception as e:
        logger.error(f"Failed to generate invite link: {e}")
        return None

# --- Route: ToyyibPay Success Callback ---
@app.route('/success', methods=['POST'])
async def success_callback():
    """Handles ToyyibPay success callbacks securely."""
    data = await request.form
    logger.info(f"Received success callback: {data}")

    if data.get("status_id") == "1" and data.get("billExternalReferenceNo"):
        order_id = data["billExternalReferenceNo"]
        if order_id.startswith("user_"):
            try:
                user_id = int(order_id.split('_')[1])
                invite_link = await generate_invite_link()
                if invite_link:
                    await application.bot.send_message(chat_id=user_id, text=f"✅ Payment successful! Join the group: {invite_link}")
                else:
                    await application.bot.send_message(chat_id=user_id, text="⚠ Payment successful, but we couldn't generate an invite link. Contact support.")
            except (IndexError, ValueError) as e:
                logger.error(f"Invalid order_id format: {order_id} - {e}")
        else:
            logger.error(f"Invalid order_id: {order_id}")
    else:
        logger.error("Failed payment validation.")
        abort(400)
    
    return "Success callback received", 200

# --- Route: Stripe Webhook ---
@app.route('/stripe_webhook', methods=['POST'])
async def stripe_webhook():
    """Handles Stripe webhook securely with signature verification."""
    payload = await request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (stripe.error.SignatureVerificationError, ValueError) as e:
        logger.error(f"Stripe webhook verification failed: {e}")
        abort(400)
    
    if event["type"] == "checkout.session.completed":
        user_id = int(event["data"]["object"]["metadata"]["user_id"])
        invite_link = await generate_invite_link()
        if invite_link:
            await application.bot.send_message(chat_id=user_id, text=f"✅ Payment successful! Join the group: {invite_link}")
        else:
            await application.bot.send_message(chat_id=user_id, text="⚠ Payment successful, but we couldn't generate an invite link. Contact support.")
    
    return "", 200

# --- Run Quart app with Hypercorn ---
if __name__ == "__main__":
    config = Config()
    config.bind = [f"0.0.0.0:{os.getenv('PORT', '8080')}"]
    
    logger.info("Starting Quart app on assigned port...")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(serve(app, config))
