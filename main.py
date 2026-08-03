"""
Temerachi Bingo - Admin Bot (Replit version)
---------------------------------------------
Same as bot.py, but adjusted to run 24/7 on Replit:

  1. BOT_TOKEN and the Firebase service account key are read from
     Replit "Secrets" (environment variables) instead of being written
     directly in the code or uploaded as a visible file. This keeps
     them private even if your Repl itself is public.
  2. A tiny web server runs alongside the bot, so Replit's "Always On" /
     UptimeRobot-style keep-alive pinging has something to hit.

Setup on Replit:
  1. Create a new Repl -> Python.
  2. Upload this file, requirements_replit.txt (rename to requirements.txt).
  3. In the Repl, open the "Secrets" (lock icon) tab and add:
       BOT_TOKEN = your bot token
       FIREBASE_SERVICE_ACCOUNT_JSON = the FULL content of your
         serviceAccountKey.json file (paste the whole JSON as the value)
  4. Press Run.
  5. Copy the web preview URL Replit shows you, and add it to UptimeRobot
     (https://uptimerobot.com, free) as an HTTP(s) monitor, checking every
     5 minutes, so Replit keeps the Repl awake.
"""

import asyncio
import json
import logging
import os
import threading

import firebase_admin
from firebase_admin import credentials, db
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ============================================================
# Config (safe to leave as-is; the two secrets come from env vars)
# ============================================================
BOT_TOKEN = os.environ["BOT_TOKEN"]
FIREBASE_SERVICE_ACCOUNT_JSON = os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"]
ADMIN_CHAT_ID = 7078415767  # Fikr's Telegram ID -- only this account can approve/reject
MINI_APP_URL = "https://fikremisaye23-byte.github.io/bingo-game/"
FIREBASE_DATABASE_URL = "https://edil-bingo-default-rtdb.firebaseio.com"
# ============================================================

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
# httpx logs full request URLs at INFO level, which would leak the bot token
# (it's part of the URL). Silence it so the console never shows the token.
logging.getLogger("httpx").setLevel(logging.WARNING)

# ---- Firebase setup ----
service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})

deposits_ref = db.reference("transactions/deposits")
withdrawals_ref = db.reference("transactions/withdrawals")


# ---- Tiny keep-alive web server (for UptimeRobot / Replit Always On) ----
flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "Temerachi Bingo bot is running."


def run_web_server():
    flask_app.run(host="0.0.0.0", port=8080)


# ---- /start command ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Play Temerachi Bingo", web_app=WebAppInfo(url=MINI_APP_URL))]
    ])
    await update.message.reply_text(
        "Welcome to Temerachi Bingo! 🎉\nTap below to play:",
        reply_markup=keyboard,
    )


# ---- Approve/Reject button handler ----
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_CHAT_ID:
        await query.answer("❌ You are not authorized.", show_alert=True)
        return

    action, kind, key = query.data.split(":", 2)  # e.g. "approve:deposit:ABC123"

    if kind == "deposit":
        record = deposits_ref.child(key).get()
        if not record:
            await query.edit_message_text("⚠️ Record not found (maybe already handled).")
            return
        if record.get("status") != "pending":
            await query.edit_message_text(f"ℹ️ Already {record.get('status')}.")
            return

        if action == "approve":
            deposits_ref.child(key).update({"status": "approved"})
            user_id = str(record["by"])
            amount = record["amount"]
            wallet_ref = db.reference(f"users/{user_id}/wallet")

            def credit(current):
                current = current or {"main": 0, "play": 0, "deposited": 0}
                current["play"] = current.get("play", 0) + amount
                current["deposited"] = current.get("deposited", 0) + amount
                return current

            wallet_ref.transaction(credit)
            await query.edit_message_text(f"✅ Approved deposit of {amount} coins for {record.get('name')}.")
        else:
            deposits_ref.child(key).update({"status": "rejected"})
            await query.edit_message_text(f"❌ Rejected deposit ({record.get('amount')} coins) for {record.get('name')}.")

    elif kind == "withdrawal":
        record = withdrawals_ref.child(key).get()
        if not record:
            await query.edit_message_text("⚠️ Record not found (maybe already handled).")
            return
        if record.get("status") != "pending":
            await query.edit_message_text(f"ℹ️ Already {record.get('status')}.")
            return

        if action == "approve":
            withdrawals_ref.child(key).update({"status": "approved"})
            await query.edit_message_text(
                f"✅ Approved withdrawal of {record.get('amount')} coins for {record.get('name')}.\n"
                f"⚠️ Remember to actually SEND the money via Telebirr to {record.get('phone')}."
            )
        else:
            # refund the amount back to the user's main wallet, since it was
            # deducted immediately when they submitted the request
            withdrawals_ref.child(key).update({"status": "rejected"})
            user_id = str(record["by"])
            amount = record["amount"]
            wallet_ref = db.reference(f"users/{user_id}/wallet")

            def refund(current):
                current = current or {"main": 0, "play": 0, "deposited": 0}
                current["main"] = current.get("main", 0) + amount
                return current

            wallet_ref.transaction(refund)
            await query.edit_message_text(f"❌ Rejected withdrawal, refunded {amount} coins to {record.get('name')}.")


# ---- Firebase realtime listeners: notify admin of new pending requests ----
def on_deposit_change(event):
    if event.data is None:
        return
    if event.path == "/":
        return  # skip the initial full snapshot
    key = event.path.strip("/")
    record = event.data
    if not isinstance(record, dict) or record.get("status") != "pending":
        return
    _notify_admin_deposit(key, record)


def on_withdrawal_change(event):
    if event.data is None:
        return
    if event.path == "/":
        return
    key = event.path.strip("/")
    record = event.data
    if not isinstance(record, dict) or record.get("status") != "pending":
        return
    _notify_admin_withdrawal(key, record)


def _notify_admin_deposit(key, record):
    text = (
        f"💰 New Deposit Request\n"
        f"Name: {record.get('name')}\n"
        f"Amount: {record.get('amount')} coins\n"
        f"Phone: {record.get('phone')}\n"
        f"Txn ID: {key}\n\n"
        f"SMS:\n{record.get('smsText', '')[:300]}"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve:deposit:{key}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject:deposit:{key}"),
    ]])
    _send_to_admin(text, keyboard)


def _notify_admin_withdrawal(key, record):
    text = (
        f"💸 New Withdrawal Request\n"
        f"Name: {record.get('name')}\n"
        f"Amount: {record.get('amount')} coins\n"
        f"Phone: {record.get('phone')}\n"
        f"Request ID: {key}"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve:withdrawal:{key}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject:withdrawal:{key}"),
    ]])
    _send_to_admin(text, keyboard)


def _send_to_admin(text, keyboard):
    # Firebase's .listen() callbacks run on a background thread, but sending
    # a Telegram message is an async operation that must run on the bot's
    # own event loop. run_coroutine_threadsafe bridges the two safely.
    coro = app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, reply_markup=keyboard)
    asyncio.run_coroutine_threadsafe(coro, main_loop)


def main():
    global app, main_loop
    app = Application.builder().token(BOT_TOKEN).build()
    main_loop = asyncio.get_event_loop()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))

    # Start Firebase realtime listeners (each runs on its own background thread)
    deposits_ref.listen(on_deposit_change)
    withdrawals_ref.listen(on_withdrawal_change)

    # Start the keep-alive web server on a background thread
    threading.Thread(target=run_web_server, daemon=True).start()

    log.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
