import logging
import os
import stripe
import requests
import hmac
import hashlib
import asyncio
from quart import Quart, request, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext
from dotenv import load_dotenv
import hypercorn.asyncio
import hypercorn.config

# Load environment variables
load_dotenv(dotenv_path="C:/Users/Ibrahim/Desktop/JOOM/Environment/Development/.env")

# Required environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOYYIBPAY_API_KEY = os.getenv("TOYYIBPAY_API_KEY")
TOYYIBPAY_CATEGORY_CODE = os.getenv("TOYYIBPAY_CATEGORY_CODE")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
GROUP_ID = os.getenv("GROUP_ID")
SUCCESS_URL = os.getenv("SUCCESS_URL")
CALLBACK_URL = os.getenv("CALLBACK_URL")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Validate environment variables
required_env_vars = [BOT_TOKEN, TOYYIBPAY_API_KEY, TOYYIBPAY_CATEGORY_CODE, STRIPE_API_KEY, GROUP_ID, SUCCESS_URL, CALLBACK_URL, STRIPE_WEBHOOK_SECRET]
if not all(required_env_vars):
    raise EnvironmentError("Missing one or more required environment variables.")

# Initialize Stripe
stripe.api_key = STRIPE_API_KEY

# Logging configuration
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Quart app
app = Quart(__name__)

# Initialize Telegram bot
application = ApplicationBuilder().token(BOT_TOKEN).build()

# --- Function: Generate Invite Link ---
async def generate_invite_link():
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
    data = await request.form
    data = data.to_dict()
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
        return "Invalid request", 400
    
    return "Success callback received", 200

# --- Route: Stripe Webhook ---
@app.route('/stripe_webhook', methods=['POST'])
async def stripe_webhook():
    payload = await request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        if event["type"] == "checkout.session.completed":
            user_id = int(event["data"]["object"]["metadata"]["user_id"])
            invite_link = await generate_invite_link()
            if invite_link:
                await application.bot.send_message(chat_id=user_id, text=f"✅ Payment successful! Join the group: {invite_link}")
            else:
                await application.bot.send_message(chat_id=user_id, text="⚠ Payment successful, but we couldn't generate an invite link. Contact support.")
    except stripe.error.SignatureVerificationError:
        logger.error("Stripe webhook signature verification failed.")
        return "Unauthorized", 400
    
    return "", 200

# --- Route: Telegram Webhook ---
@app.route('/webhook', methods=['POST'])
async def telegram_webhook():
    update = Update.de_json(await request.get_json(), application.bot)
    await application.process_update(update)
    return "", 200

# --- Function: Start Command ---
async def start(update: Update, context: CallbackContext):
    logger.info(f"Received /start command from {update.effective_user.username}")
    await update.message.reply_text("Welcome! Use /subscribe to start your subscription.")

# --- Function: Subscription Command ---
async def subscribe(update: Update, context: CallbackContext):
    await update.message.reply_text("Subscription process will be implemented.")

# Add command handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("subscribe", subscribe))

# --- Main Function ---
async def main():
    # Start the Telegram bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # Start Quart server
    config = hypercorn.config.Config()
    config.bind = ["0.0.0.0:10000"]
    await hypercorn.asyncio.serve(app, config)

if __name__ == "__main__":
    asyncio.run(main())
