import datetime
import logging
import os
import stripe
import requests
import threading
import hmac
import hashlib
from flask import Flask, request, abort
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

# Flask app
app = Flask(__name__)

# Telegram bot application
application = ApplicationBuilder().token(BOT_TOKEN).build()

# --- Function: Generate Invite Link ---
def generate_invite_link():
    """Generate a Telegram invite link for the group."""
    try:
        invite_link = application.bot.create_chat_invite_link(chat_id=GROUP_ID)
        logger.info(f"Generated invite link: {invite_link.invite_link}")
        return invite_link.invite_link
    except Exception as e:
        logger.error(f"Failed to generate invite link: {e}")
        return None

# --- Route: ToyyibPay Success Callback ---
@app.route('/success', methods=['POST'])
def success_callback():
    """Handles ToyyibPay success callbacks securely."""
    data = request.form.to_dict()
    logger.info(f"Received success callback: {data}")

    # Validate payment with userSecretKey
    if data.get("status_id") == "1" and data.get("billExternalReferenceNo"):
        order_id = data["billExternalReferenceNo"]
        if order_id.startswith("user_"):
            try:
                user_id = int(order_id.split('_')[1])
                invite_link = generate_invite_link()
                if invite_link:
                    application.bot.send_message(chat_id=user_id, text=f"✅ Payment successful! Join the group: {invite_link}")
                else:
                    application.bot.send_message(chat_id=user_id, text="⚠ Payment successful, but we couldn't generate an invite link. Contact support.")
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
def stripe_webhook():
    """Handles Stripe webhook securely with signature verification."""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        if event["type"] == "checkout.session.completed":
            user_id = int(event["data"]["object"]["metadata"]["user_id"])
            invite_link = generate_invite_link()
            if invite_link:
                application.bot.send_message(chat_id=user_id, text=f"✅ Payment successful! Join the group: {invite_link}")
            else:
                application.bot.send_message(chat_id=user_id, text="⚠ Payment successful, but we couldn't generate an invite link. Contact support.")
    except stripe.error.SignatureVerificationError:
        logger.error("Stripe webhook signature verification failed.")
        abort(400)
    
    return "", 200

# --- Route: ToyyibPay Callback ---
@app.route('/callback', methods=['POST'])
def payment_callback():
    """Handles ToyyibPay payment callback securely."""
    data = request.form.to_dict()
    logger.info(f"Received payment callback: {data}")
    
    if not hmac.compare_digest(data.get("userSecretKey", ""), TOYYIBPAY_API_KEY):
        logger.error("Unauthorized callback request.")
        abort(403)
    
    return "Payment callback received", 200

# --- Function: Start Telegram Bot ---
async def start(update: Update, context):
    logger.info(f"Received /start command from {update.effective_user.username}")
    await update.message.reply_text("Welcome! Use /subscribe to start your subscription.")

# --- Function: Subscription Command ---
async def subscribe(update: Update, context):
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
            bill_code = payment_data[0]["BillCode"]
            toyibpay_link = f"{TOYYIBPAY_BASE_URL}/{bill_code}"
        except Exception as e:
            logger.error(f"Error parsing ToyyibPay response: {e}")

    # Step 2: Generate Stripe Payment Link
    stripe_link = None
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price_data": {"currency": "myr", "product_data": {"name": "Group Subscription"}, "unit_amount": 200}, "quantity": 1}],
            mode="payment",
            success_url=SUCCESS_URL,
            cancel_url=CALLBACK_URL,
            metadata={"user_id": user.id},
        )
        stripe_link = session.url
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")

    # Send Payment Links
    if toyibpay_link or stripe_link:
        message = "Choose your payment method:\n\n"
        if toyibpay_link:
            message += f"1. [Pay with ToyyibPay]({toyibpay_link})\n"
        if stripe_link:
            message += f"2. [Pay with Stripe]({stripe_link})\n"
        await update.message.reply_text(message, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Payment link generation failed. Please try again later.")

# Run Flask
def run_flask():
    app.run(host='0.0.0.0', port=10000)

# Start Telegram bot
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("subscribe", subscribe))

# Run services separately
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    application.run_polling()
