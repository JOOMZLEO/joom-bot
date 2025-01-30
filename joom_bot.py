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
from telegram.ext import Application, CommandHandler
from dotenv import load_dotenv

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

# Validate all environment variables
required_env_vars = {
    "BOT_TOKEN": BOT_TOKEN,
    "TOYYIBPAY_API_KEY": TOYYIBPAY_API_KEY,
    "TOYYIBPAY_CATEGORY_CODE": TOYYIBPAY_CATEGORY_CODE,
    "STRIPE_API_KEY": STRIPE_API_KEY,
    "GROUP_ID": GROUP_ID,
    "SUCCESS_URL": SUCCESS_URL,
    "CALLBACK_URL": CALLBACK_URL,
    "STRIPE_WEBHOOK_SECRET": STRIPE_WEBHOOK_SECRET,
}

missing_vars = [key for key, value in required_env_vars.items() if not value]
if missing_vars:
    raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Initialize Stripe
stripe.api_key = STRIPE_API_KEY

# Logging configuration
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Quart app
app = Quart(__name__)

# Telegram bot application
application = Application.builder().token(BOT_TOKEN).build()

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
    try:
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
            abort(400)

        return "Success callback received", 200
    except Exception as e:
        logger.error(f"Error in success_callback: {e}")
        abort(500)

# --- Route: Telegram Webhook ---
@app.route('/webhook', methods=['POST'])
async def telegram_webhook():
    """Handles incoming Telegram updates via webhook."""
    json_data = await request.get_json()
    update = Update.de_json(json_data, application.bot)
    await application.process_update(update)
    return "", 200

# --- Function: Start Telegram Bot ---
async def start(update: Update, context):
    logger.info(f"Received /start command from {update.effective_user.username}")
    await update.message.reply_text("Welcome! Use /subscribe to start your subscription.")

# --- Function: Subscription Command ---
async def subscribe(update: Update, context):
    user = update.message.from_user

    toyibpay_link = f"https://toyyibpay.com/sample-link/{user.id}"
    stripe_link = "https://checkout.stripe.com/pay/sample-link"

    message = "Choose your payment method:\n\n"
    message += f"1. [Pay with ToyyibPay]({toyibpay_link})\n"
    message += f"2. [Pay with Stripe]({stripe_link})\n"

    await update.message.reply_text(message, parse_mode="Markdown")

# Add command handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("subscribe", subscribe))

# Run services
async def main():
    await application.initialize()
    await application.start()

    config = hypercorn.config.Config()
    config.bind = ["0.0.0.0:10000"]
    await hypercorn.asyncio.serve(app, config)

if __name__ == "__main__":
    asyncio.run(main())
