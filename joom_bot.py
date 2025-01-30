import logging
import os
import stripe
import asyncio
from quart import Quart, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
GROUP_ID = os.getenv("GROUP_ID")
SUCCESS_URL = os.getenv("SUCCESS_URL")
CALLBACK_URL = os.getenv("CALLBACK_URL")

# Validate required environment variables
if not all([BOT_TOKEN, STRIPE_API_KEY, GROUP_ID, SUCCESS_URL, CALLBACK_URL, STRIPE_WEBHOOK_SECRET]):
    raise EnvironmentError("Missing one or more required environment variables.")

# Initialize Stripe
stripe.api_key = STRIPE_API_KEY

# Logging configuration
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Quart app
app = Quart(__name__)

# Telegram bot application
telegram_app = Application.builder().token(BOT_TOKEN).build()

# --- Route: Webhook for Telegram Bot ---
@app.route('/webhook', methods=['POST'])
async def telegram_webhook():
    update = Update.de_json(await request.json, telegram_app.bot)
    await telegram_app.process_update(update)
    return jsonify({"status": "ok"})

# --- Route: Stripe Webhook ---
@app.route('/stripe_webhook', methods=['POST'])
async def stripe_webhook():
    payload = await request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        if event["type"] == "checkout.session.completed":
            user_id = int(event["data"]["object"]["metadata"]["user_id"])
            invite_link = await generate_invite_link()
            if invite_link:
                await telegram_app.bot.send_message(chat_id=user_id, text=f"✅ Payment successful! Join the group: {invite_link}")
    except stripe.error.SignatureVerificationError:
        logger.error("Stripe webhook signature verification failed.")
        return jsonify({"error": "Invalid signature"}), 400

    return jsonify({"status": "ok"})

# --- Function: Generate Invite Link ---
async def generate_invite_link():
    try:
        invite_link = await telegram_app.bot.create_chat_invite_link(chat_id=GROUP_ID)
        logger.info(f"Generated invite link: {invite_link.invite_link}")
        return invite_link.invite_link
    except Exception as e:
        logger.error(f"Failed to generate invite link: {e}")
        return None

# --- Telegram Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /subscribe to start your subscription.")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Group Subscription"},
                    "unit_amount": 500,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=SUCCESS_URL,
            cancel_url=CALLBACK_URL,
            metadata={"user_id": user.id},
        )
        await update.message.reply_text(f"Pay here: {session.url}")
    except Exception as e:
        logger.error(f"Error creating Stripe session: {e}")
        await update.message.reply_text("Failed to create payment link. Try again later.")

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("subscribe", subscribe))

if __name__ == "__main__":
    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    # Set up webhook for Telegram
    loop = asyncio.get_event_loop()
    loop.run_until_complete(telegram_app.bot.set_webhook(url=f"{CALLBACK_URL}/webhook"))

    # Run Quart with Hypercorn
    config = Config()
    config.bind = ["0.0.0.0:10000"]
    loop.run_until_complete(serve(app, config))
