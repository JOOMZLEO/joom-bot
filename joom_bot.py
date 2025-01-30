import logging
import os
import stripe
import hmac
import asyncio
from quart import Quart, request, abort
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
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
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

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
    "WEBHOOK_URL": WEBHOOK_URL,
}

missing_vars = [name for name, value in required_env_vars.items() if not value]
if missing_vars:
    raise EnvironmentError(f"Missing or empty environment variables: {', '.join(missing_vars)}")

# Initialize Stripe
stripe.api_key = STRIPE_API_KEY

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Quart app
app = Quart(__name__)

# Telegram bot application
application = ApplicationBuilder().token(BOT_TOKEN).build()

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
                    await application.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ Payment successful! Join the group: {invite_link}"
                    )
                else:
                    await application.bot.send_message(
                        chat_id=user_id,
                        text="⚠ Payment successful, but we couldn't generate an invite link. Contact support."
                    )
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
        if event["type"] == "checkout.session.completed":
            user_id = int(event["data"]["object"]["metadata"]["user_id"])
            invite_link = await generate_invite_link()
            if invite_link:
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Payment successful! Join the group: {invite_link}"
                )
            else:
                await application.bot.send_message(
                    chat_id=user_id,
                    text="⚠ Payment successful, but we couldn't generate an invite link. Contact support."
                )
    except stripe.error.SignatureVerificationError:
        logger.error("Stripe webhook signature verification failed.")
        abort(400)

    return "", 200

# --- Route: ToyyibPay Callback ---
@app.route('/callback', methods=['POST'])
async def payment_callback():
    """Handles ToyyibPay payment callback securely."""
    data = await request.form
    logger.info(f"Received payment callback: {data}")

    if not hmac.compare_digest(data.get("userSecretKey", ""), TOYYIBPAY_API_KEY):
        logger.error("Unauthorized callback request.")
        abort(403)

    return "Payment callback received", 200

# --- Function: Start Telegram Bot ---
async def start(update: Update, context):
    """Handles the /start command."""
    logger.info(f"Received /start command from {update.effective_user.username}")
    await update.message.reply_text("Welcome! Use /subscribe to start your subscription.")

# --- Function: Subscription Command ---
async def subscribe(update: Update, context):
    """Handles the /subscribe command."""
    user = update.message.from_user
    toyibpay_link = f"https://toyyibpay.com/{TOYYIBPAY_CATEGORY_CODE}"
    stripe_link = "https://your_stripe_payment_link_here"

    await update.message.reply_text(
        f"Choose a payment method:\n\n"
        f"1️⃣ [Pay with ToyyibPay]({toyibpay_link})\n"
        f"2️⃣ [Pay with Stripe]({stripe_link})",
        parse_mode="Markdown"
    )

# Add Telegram bot handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("subscribe", subscribe))

# --- Main Function ---
async def main():
    logging.info("Starting the bot with webhook...")
    await application.bot.set_webhook(url=WEBHOOK_URL)
    await application.start()
    await application.run_webhook(listen='0.0.0.0', port=10000, webhook_url=WEBHOOK_URL)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    app.run(port=10000)
