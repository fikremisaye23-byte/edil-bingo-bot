"""
Temerachi Bingo - Admin Bot (Replit version)
---------------------------------------------
Same as bot.py, but adjusted to run 24/7 on Replit, PLUS a native
in-chat menu (Register / Check Balance / Deposit / Withdraw / Support /
Instruction / Invite) so players can do everything without leaving the
chat. "Play" still opens the Mini App, because the live bingo board
(numbers being called, marking cells in real time) needs a real
interactive screen that a Telegram chat can't render on its own.

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
import random
import re
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime

import firebase_admin
import telegram
from firebase_admin import credentials, db
from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============================================================
# Config (safe to leave as-is; the two secrets come from env vars)
# ============================================================
BOT_TOKEN = os.environ["BOT_TOKEN"]
FIREBASE_SERVICE_ACCOUNT_JSON = os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"]
ADMIN_CHAT_ID = 7078415767  # Fikr's Telegram ID -- only this account can approve/reject
MINI_APP_URL = "https://fikremisaye23-byte.github.io/bingo-game/"
SUPPORT_USERNAME = "Temerachibingosupport"
FIREBASE_DATABASE_URL = "https://edil-bingo-default-rtdb.firebaseio.com"
# ============================================================

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
# httpx logs full request URLs at INFO level, which would leak the bot token
# (it's part of the URL). Silence it so the console never shows the token.
logging.getLogger("httpx").setLevel(logging.WARNING)


async def _safe_answer(query, *args, **kwargs):
    """
    Wrapper around query.answer() that swallows the "query is too old"
    error Telegram raises when a callback query wasn't answered in time
    (e.g. the bot was momentarily slow, or Render's free tier was waking
    up from sleep). Without this, that single exception used to bubble
    up unhandled and crash the whole bot process.
    """
    try:
        await query.answer(*args, **kwargs)
    except telegram.error.BadRequest as e:
        log.warning(f"Could not answer callback query (likely expired): {e}")

# ---- Firebase setup ----
service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})

deposits_ref = db.reference("transactions/deposits")
withdrawals_ref = db.reference("transactions/withdrawals")
# Keeps track of Telebirr transaction IDs that have already been used for a
# deposit, so the same confirmation SMS can't be submitted twice.
used_deposit_ids_ref = db.reference("transactions/usedDepositIds")

# Fraud-hardening: throttle how often any one user can attempt a deposit
# submission, so someone can't brute-force-spam the verification endpoint
# (e.g. rapidly trying many receipt numbers hoping one happens to verify).
# In-memory is fine here -- worst case a restart resets everyone's cooldown,
# which is not a security issue, just occasionally more lenient.
_deposit_attempt_times = {}
_deposit_attempt_lock = threading.Lock()
DEPOSIT_RATE_LIMIT_MAX = 5       # attempts
DEPOSIT_RATE_LIMIT_WINDOW = 600  # seconds (10 minutes)
# Fraud-hardening: even a fully verified deposit above this amount is routed
# to admin review instead of being auto-credited -- an extra layer of caution
# for unusually large sums, in case the verification logic itself is ever
# wrong or the page format changes in a way we haven't caught.
AUTO_APPROVE_MAX_AMOUNT = 2000


def _deposit_rate_limited(user_id):
    """Returns True if this user should be blocked for now (too many recent attempts)."""
    now = time.time()
    with _deposit_attempt_lock:
        recent = [t for t in _deposit_attempt_times.get(user_id, []) if now - t < DEPOSIT_RATE_LIMIT_WINDOW]
        recent.append(now)
        _deposit_attempt_times[user_id] = recent
        return len(recent) > DEPOSIT_RATE_LIMIT_MAX


# Same three receiving numbers, and the same round-robin rotation counter
# (deposits/rotationIndex), as the Mini App -- so whichever channel a user
# deposits from, the numbers rotate together instead of each keeping its
# own separate count.
TELEBIRR_NUMBERS = [
    {"phone": "0923160399", "name": "Fikre"},
    {"phone": "0900619106", "name": "Fikr"},
    {"phone": "0921466712", "name": "asebechimariyam"},
]


def get_next_telebirr_number():
    rotation_ref = db.reference("deposits/rotationIndex")

    def increment(current):
        return (current + 1) if isinstance(current, int) else 0

    try:
        idx = rotation_ref.transaction(increment)
        if not isinstance(idx, int):
            idx = 0
    except Exception:
        idx = random.randrange(len(TELEBIRR_NUMBERS))
    return TELEBIRR_NUMBERS[idx % len(TELEBIRR_NUMBERS)]


# Parses a genuine Telebirr confirmation SMS, e.g.:
#   "ውድFikre ወደ Fikre Misaye(2519****9106) 20.00 ብር በ 06/08/2026 00:42:19 "
#   "ልከዋል። የሂሳብ እንቅስቃሴ ቁጥርዎ DH69K37KI1 ነዉ። ..."
# Returns a dict with amount / phone_last4 / txn_id, or None if the text
# doesn't look like a real Telebirr SMS at all.
def parse_telebirr_sms(text):
    # Amount: collect EVERY monetary figure in the message (not just the
    # first), regardless of whether the SMS wording is Amharic ("ብር") or
    # English ("Birr"/"ETB") -- Telebirr sends in whichever language the
    # recipient's SIM/handset is set to, and earlier only matching "ብር"
    # silently broke everything for English-language messages.
    amount_matches = re.findall(r"([\d,]+(?:\.\d+)?)\s*(?:ብር|Birr|ETB)", text, re.IGNORECASE)
    # Phone (last 4 digits of the masked sender number): informational only,
    # not required for the deposit to be considered valid -- we already
    # verify the depositing user via their Telegram account, so a missing or
    # differently-formatted phone snippet should not block an otherwise valid
    # deposit.
    phone_match = re.search(r"\(?251\d\*+(\d{2,4})\)?", text)
    # Transaction ID: try Amharic phrasing first (accepting both common
    # spellings/diacritics of "ነው"/"ነዉ"), then common English phrasings, then
    # fall back to any bare alphanumeric reference code -- that last fallback
    # alone is language-independent, so it still catches the ID even for SMS
    # wordings we haven't specifically seen yet.
    txn_match = (
        re.search(r"ቁጥርዎ\s*(\S+)\s*ነ[ዉው]", text)
        or re.search(
            r"(?:transaction\s*(?:number|id)|txn\s*id|ref(?:erence)?\s*(?:no\.?|number)?)\s*(?:is|:)?\s*([A-Za-z0-9]{6,20})",
            text, re.IGNORECASE,
        )
        or re.search(r"\b([A-Z0-9]{8,14})\b", text)
    )

    # NOTE: amounts and txn_id are independent -- a message can have a valid
    # txn ID even if the amount wording doesn't match anything we recognize
    # (or vice versa). Only the txn ID is actually required by callers today,
    # so we must not let a missing amount silently erase a found txn ID.
    if not txn_match:
        return None

    amounts = []
    for raw in amount_matches:
        try:
            amounts.append(float(raw.replace(",", "")))
        except ValueError:
            continue

    return {
        "amounts": amounts,
        "phone_last4": phone_match.group(1) if phone_match else "",
        "txn_id": txn_match.group(1),
    }


def fetch_telebirr_receipt(receipt_no):
    """
    Fetch Ethio Telecom's own official receipt page for a transaction and
    extract the amount + recipient phone from it. This is our automatic
    verification layer: unlike the raw SMS text a user pastes (which they
    could in principle edit before sending), this page is rendered live by
    Ethio Telecom's own servers from the real transaction record, so a match
    here is much stronger proof the deposit is genuine.

    ALWAYS returns a "debug" field describing exactly what happened (the
    network error, the HTTP status, or a snippet of the raw HTML if the
    amount couldn't be found) -- so any failure can be diagnosed from real
    evidence (sent to the admin) instead of guessed at. Never raises; the
    caller must treat ok=False as "could not auto-verify" and fall back to
    manual admin review, never as a rejection.
    """
    url = f"https://transactioninfo.ethiotelecom.et/receipt/{receipt_no}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            )
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        log.warning(f"Receipt fetch failed for {receipt_no}: {e}")
        return {"ok": False, "debug": f"fetch error: {e!r}"}

    amount_match = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:ETB|Birr|ብር)", html, re.IGNORECASE)
    if not amount_match:
        snippet = re.sub(r"\s+", " ", html).strip()[:1500]
        log.warning(f"Receipt page for {receipt_no} fetched (HTTP {status}) but amount not found")
        return {"ok": False, "debug": f"HTTP {status}, amount not found. Page snippet: {snippet}"}
    try:
        amount = float(amount_match.group(1).replace(",", ""))
    except ValueError:
        return {"ok": False, "debug": f"HTTP {status}, amount text unparseable: {amount_match.group(1)!r}"}

    # Every phone-like number on the page (there may be more than one --
    # sender and recipient both appear). The caller cross-checks these
    # against our own business numbers.
    all_phones = re.findall(r"(?:251)?0?9\d{8}", html)

    # Transaction date/time, if present on the page, so the caller can
    # reject a receipt that isn't actually recent.
    date_match = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{4}[,\s]+\d{1,2}:\d{2}(?::\d{2})?)", html)

    return {
        "ok": True,
        "amount": amount,
        "all_phones": all_phones,
        "date_text": date_match.group(1) if date_match else None,
        "debug": None,
    }


def fetch_telebirr_receipt_with_retry(receipt_no, max_wait_seconds=90, poll_interval=7):
    """
    Keep polling Ethio Telecom's receipt page for up to max_wait_seconds,
    since the page is sometimes slow to publish a brand-new transaction (or
    slow to respond at all). Stops as soon as a receipt is found, or gives
    up once the time budget runs out -- returns the LAST attempt's result
    dict either way (never None), so the caller always has debug info to
    show the admin.

    This function does blocking network calls and time.sleep(), so callers
    on the bot's event loop MUST run it via loop.run_in_executor(...) rather
    than awaiting it directly, so other users aren't blocked while it polls.
    """
    deadline = time.time() + max_wait_seconds
    attempt = 0
    last_result = {"ok": False, "debug": "no attempts made"}
    while True:
        attempt += 1
        last_result = fetch_telebirr_receipt(receipt_no)
        if last_result.get("ok"):
            return last_result
        if time.time() >= deadline:
            log.info(f"Giving up on receipt {receipt_no} after {attempt} attempts (~{max_wait_seconds}s budget)")
            return last_result
        time.sleep(poll_interval)


INSTRUCTIONS_TEXT = """🃏 መጫወቻ ካርድ

1. ጨዋታውን ለመጀመር ከሚመጣልን ከ1-600 የካርድ መምረጫ ቦርድ ውስጥ እስከ 2 የመጫወቻ ካርድ (ካርቴላ) መምረጥ ይቻላል።

2. የካርድ መምረጫ ቦርድ ላይ በቀይ ቀለም የተመረጡ ቁጥሮች የሚያሳዩት መጫወቻ ካርዱ (ካርቴላው) በሌላ ተጫዋች መመረጡን ነው።

3. የመጫወቻ ካርዱን (ካርቴላውን) ሲመርጡት ከታች የሚይዛቸውን ቁጥሮች ያሳያል።

4. ወደ ጨዋታው ለመግባት የሚፈልጉትን የመጫወቻ ካርድ (ካርቴላ) ሲመርጡና ለምዝገባ የተሰጠው ሰኮንድ ዜሮ ሲሆን ቀጥታ ወደ ጨዋታ ያስገባል።

🎮 ጨዋታ እንዴት ይካሄዳል

1. ወደ ጨዋታው ከገቡ በኋላ በመረጡት የመጫወቻ ካርድ (ካርቴላ) ከታች በቀኝ በኩል ያገኙታል።

2. ጨዋታው ሲጀምር ሲስተሙ ከ1 እስከ 75 ያሉ ቁጥሮችን Randomly መጥራት ይጀምራል።

3. ሲስተሙ ከሚጠራቸው ቁጥሮች ውስጥ በራስዎ የመጫወቻ ካርድ (ካርቴላ) ላይ ካሉ በመምረጥ ያጥቁሩ። በራሱ እንዲያጠቁር ከፈለጉ Automatic የሚለውን ያብሩት።

🏆 አሸናፊ የሚሆኑባቸው መንገዶች

1. መጫወቻ ካርድ (ካርቴላ) ላይ የተጠቆሩት ቁጥሮች፦
   • ወደጎን ወይም ወደታች መስመር ከሰሩ
   • ወደሁለቱም አግዳሚ መስመር ከሰሩ
   • አራቱ ማእዘናት (ኮርነር) ከተጠሩ አሸናፊ ይሆናሉ።

2. ሁለት ወይም ከዚያ በላይ ተጫዋቾች እኩል ቢያሸንፉ አጠቃላይ ደራሹ ብር ለአሸናፊዎች እኩል ይካፈላል።"""


# ---- Tiny keep-alive web server (for UptimeRobot / Replit Always On) ----
flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "Temerachi Bingo bot is running."


def run_web_server():
    flask_app.run(host="0.0.0.0", port=8080)


def deposit_payment_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Telebirr", callback_data="deppay:telebirr")],
        [InlineKeyboardButton("Cancel", callback_data="deppay:cancel")],
    ])


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Play", callback_data="menu:play"),
         InlineKeyboardButton("📝 Register", callback_data="menu:register")],
        [InlineKeyboardButton("💰 Check Balance", callback_data="menu:balance"),
         InlineKeyboardButton("🪙 Deposit", callback_data="menu:deposit")],
        [InlineKeyboardButton("🆘 Contact Support", callback_data="menu:support"),
         InlineKeyboardButton("📖 Instruction", callback_data="menu:instruction")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="menu:withdraw"),
         InlineKeyboardButton("🔗 Invite", callback_data="menu:invite")],
    ])


# ---- /start command ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["flow"] = None  # reset any half-finished deposit/withdraw flow
    caption = "Welcome to Temerachi Bingo ! Choose an Option below."

    try:
        photos = await context.bot.get_user_profile_photos(context.bot.id, limit=1)
        if photos.total_count > 0:
            photo_file_id = photos.photos[0][-1].file_id  # largest available size
            await update.message.reply_photo(
                photo=photo_file_id,
                caption=caption,
                reply_markup=main_menu_keyboard(),
            )
            return
    except Exception as e:
        log.warning(f"Could not fetch bot profile photo, falling back to text: {e}")

    await update.message.reply_text(caption, reply_markup=main_menu_keyboard())


def _wallet_ref(user_id):
    return db.reference(f"users/{user_id}/wallet")


def _get_wallet(user_id):
    w = _wallet_ref(user_id).get()
    return w or {"main": 0, "play": 0, "deposited": 0}


# ---- Shared menu action logic (used by both the inline-button menu and the /commands) ----
async def _run_menu_action(action, reply_target, user, context):
    user_id = str(user.id)
    name = (user.first_name or "") + (" " + user.last_name if user.last_name else "")
    name = name.strip() or "Player"

    if action == "play":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎮 Open Game", web_app=WebAppInfo(url=MINI_APP_URL))]
        ])
        await reply_target.reply_text(
            "Choose your stake to play:",
            reply_markup=keyboard,
        )

    elif action == "register":
        user_record = db.reference(f"users/{user_id}").get() or {}
        if user_record.get("registered"):
            await reply_target.reply_text("❗ You already have registered. /play")
            return

        contact_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Share Contact", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await reply_target.reply_text(
            "📝 ለምዝገባ እባክዎ ስልክ ቁጥርዎን ያጋሩ:",
            reply_markup=contact_keyboard,
        )

    elif action == "balance":
        wallet = _get_wallet(user_id)
        user_record = db.reference(f"users/{user_id}").get() or {}
        display_name = user_record.get("name", name)
        phone = user_record.get("phone", "አልተመዘገበም")
        main_bal = wallet.get("main", 0)
        play_bal = wallet.get("play", 0)
        coin_total = main_bal + play_bal
        await reply_target.reply_text(
            "💼 Account Info\n\n"
            "```\n"
            f"Name:               {display_name}\n"
            f"Phone:              {phone}\n"
            f"Main wallet:        {main_bal}\n"
            f"Play wallet:        {play_bal}\n"
            f"Coin:               {coin_total}\n"
            "```",
            parse_mode="Markdown",
        )

    elif action == "support":
        await reply_target.reply_text(
            f"🆘 Need help? Contact support here: https://t.me/{SUPPORT_USERNAME}"
        )

    elif action == "instruction":
        await reply_target.reply_text(INSTRUCTIONS_TEXT)

    elif action == "invite":
        short_id = user_id[-6:]
        link = f"https://t.me/Temerachibingo_bot?start=ref{short_id}"
        await reply_target.reply_text(f"🔗 Invite friends with your link:\n{link}")

    elif action == "deposit":
        context.user_data["flow"] = "deposit_amount"
        context.user_data["flow_data"] = {"name": name}
        await reply_target.reply_text(
            "💰 ማስገባት የሚፈልጉትን መጠን ከ10 ብር ጀምሮ ያስገቡ።"
        )

    elif action == "withdraw":
        wallet = _get_wallet(user_id)
        if wallet.get("main", 0) <= 0:
            await reply_target.reply_text("⚠️ Your main wallet is empty, there's nothing to withdraw.")
            return
        context.user_data["flow"] = "withdraw_amount"
        context.user_data["flow_data"] = {"name": name}
        await reply_target.reply_text(
            "💰 ማውጣት የሚፈልጉትን የገንዘብ መጠን ያስገቡ?"
        )


# ---- Main menu button handler ----
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    action = query.data.split(":", 1)[1]
    await _run_menu_action(action, query.message, query.from_user, context)


# ---- Slash-command versions of the same menu actions, so the Telegram "/"
# commands menu (set via BotFather) works the same as tapping the inline
# buttons, instead of just sitting there unresponsive. ----
async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_menu_action("register", update.message, update.effective_user, context)


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_menu_action("balance", update.message, update.effective_user, context)


async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_menu_action("deposit", update.message, update.effective_user, context)


async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_menu_action("play", update.message, update.effective_user, context)


async def instruction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_menu_action("instruction", update.message, update.effective_user, context)


async def contactsupport_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_menu_action("support", update.message, update.effective_user, context)


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_menu_action("invite", update.message, update.effective_user, context)


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_menu_action("withdraw", update.message, update.effective_user, context)


# ---- Deposit payment-method button handler (Telebirr / Cancel) ----
async def deposit_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    choice = query.data.split(":", 1)[1]

    if choice == "cancel":
        context.user_data["flow"] = None
        context.user_data["flow_data"] = {}
        await query.message.reply_text(
            "Choose an option below:", reply_markup=main_menu_keyboard()
        )
        return

    data = context.user_data.setdefault("flow_data", {})
    amount = data.get("amount")
    number_obj = get_next_telebirr_number()
    data["payToPhone"] = number_obj["phone"]
    data["payToName"] = number_obj["name"]
    context.user_data["flow"] = "deposit_sms"
    await query.message.reply_text(
        f"1. ከታች ባለው የቴሌብር አካውንት {amount} ብር ያስገቡ\n\n"
        f"Phone:\n`{number_obj['phone']}`\n\n"
        f"2. የከፈሉበትን አጭር የጹሁፍ መልዕክት(message) copy በማድረግ እዚ ላይ Paste "
        f"አድርገው ያስገቡና ይላኩት\n👇👇👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="deppay:cancel")]]),
    )


# ---- Contact-share handler (completes registration) ----
async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user = update.effective_user

    if contact.user_id and contact.user_id != user.id:
        await update.message.reply_text(
            "⚠️ የራስዎን ስልክ ቁጥር ብቻ ማጋራት ይችላሉ።",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    user_id = str(user.id)
    name = (user.first_name or "") + (" " + user.last_name if user.last_name else "")
    name = name.strip() or "Player"

    db.reference(f"users/{user_id}").update({
        "name": name,
        "phone": contact.phone_number,
        "registered": True,
    })
    await update.message.reply_text(
        f"✅ Registered! Welcome, {name}.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.message.reply_text(
        "Choose an option below:",
        reply_markup=main_menu_keyboard(),
    )


# ---- Multi-step text flows for Deposit / Withdraw ----
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    flow = context.user_data.get("flow")
    if not flow:
        return  # not in a flow; ignore stray text

    user = update.effective_user
    user_id = str(user.id)
    text = (update.message.text or "").strip()
    data = context.user_data.setdefault("flow_data", {})

    # ---- Deposit flow: amount -> choose Telebirr/Cancel -> SMS text ----
    if flow == "deposit_amount":
        if not text.isdigit() or int(text) < 10:
            await update.message.reply_text(
                "💰 ማስገባት የሚፈልጉትን መጠን ከ10 ብር ጀምሮ ያስገቡ።"
            )
            return
        data["amount"] = int(text)
        context.user_data["flow"] = None
        await update.message.reply_text(
            "❇️ ማስገባት የሚችሉት አሁን በተቀመጠዉ የTelebirr አካዉንት ብቻ ነዉ።\n\n"
            "🚫 ከዚህ ዉጭ የላከ አናስተናግድም 🚫\n\n"
            "👇 Telebirr የሚለዉን ይምረጡ👇",
            reply_markup=deposit_payment_keyboard(),
        )

    elif flow == "deposit_sms":
        if _deposit_rate_limited(user_id):
            log.warning(f"Deposit rate limit hit for user {user_id}")
            await update.message.reply_text(
                "🚫 በአጭር ጊዜ ውስጥ በጣም ብዙ ጥያቄ ልከዋል። እባክዎ ትንሽ ቆይተው ደግመው ይሞክሩ ወይም "
                f"@{SUPPORT_USERNAME} ላይ ይፃፉልን።"
            )
            return

        parsed = parse_telebirr_sms(text)

        # Extract a receipt/transaction reference number -- either from a
        # pasted https://transactioninfo.ethiotelecom.et/receipt/XXXX link
        # (language-independent, since it's a literal URL), or from the SMS
        # text itself via parse_telebirr_sms (now handles both Amharic and
        # English wording).
        receipt_url_match = re.search(
            r"transactioninfo\.ethiotelecom\.et/receipt/([A-Za-z0-9]+)", text
        )
        receipt_no = receipt_url_match.group(1) if receipt_url_match else (
            parsed["txn_id"] if parsed else None
        )

        # Defense in depth: whatever the source, only accept a strictly
        # alphanumeric reference of a sane length before we ever use it to
        # build a Firebase key.
        if receipt_no and not re.fullmatch(r"[A-Za-z0-9]{6,20}", receipt_no):
            receipt_no = None

        if not receipt_no:
            log.info(f"Deposit submission unparseable for user {user_id}: no receipt/txn ID found")
            await update.message.reply_text(
                "🚫 ኤስኤምኤሱ ሊነበብ አልቻለም። እባክዎ ስልክዎ ላይ የገባውን ትክክለኛ ሚሴጅ (SMS) ሙሉ በሙሉ ኮፒ አድርገው ይላኩ፡፡\n\n"
                f"❓ለድጋፍ @{SUPPORT_USERNAME} ላይ ይፃፉልን"
            )
            return

        # Atomically reserve the receipt/txn ID now, so the same SMS can't
        # be submitted twice while it's awaiting admin review. If the admin
        # rejects it, the reservation is released so the user can resubmit
        # (e.g. after correcting a typo).
        already_used_holder = {"already_used": False}

        def reserve(current):
            if current:
                already_used_holder["already_used"] = True
                return current
            return True

        used_deposit_ids_ref.child(receipt_no).transaction(reserve)

        if already_used_holder["already_used"]:
            log.info(f"Deposit duplicate for user {user_id}: receipt/txn_id={receipt_no} already reserved")
            await update.message.reply_text(
                "🚫 ይህ የደረሰኝ ቁጥር (transaction ID) ቀድሞ ጥቅም ላይ ውሏል። እያንዳንዱ ደረሰኝ አንድ ጊዜ ብቻ ጥቅም ላይ ሊውል ይችላል፡፡\n\n"
                f"❓ለድጋፍ @{SUPPORT_USERNAME} ላይ ይፃፉልን"
            )
            return

        stated_amount = data.get("amount")
        context.user_data["flow"] = None
        context.user_data["flow_data"] = {}

        # Let the user know we're checking -- the retrying verification
        # below can take up to a minute, and without this the chat would
        # look unresponsive the whole time.
        await update.message.reply_text("🔎 ደረሰኝዎን በማረጋገጥ ላይ ነው... እባክዎ ይጠብቁ (እስከ 1 ደቂቃ ሊፈጅ ይችላል)")

        # --- Automatic verification against Ethio Telecom's own official
        # receipt page. If it succeeds and matches, the deposit is credited
        # immediately with no admin step. Runs via run_in_executor so this
        # blocking network polling never freezes the bot for other users.
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, fetch_telebirr_receipt_with_retry, receipt_no
        )
        verified = False
        verified_amount = None
        if result.get("ok"):
            amount_ok = stated_amount is not None and abs(result["amount"] - float(stated_amount)) <= 0.01

            # Fraud prevention: the recipient MUST be one of our own business
            # numbers, and an unverifiable recipient (no phone found at all)
            # never auto-approves -- falls back to manual review instead.
            our_last4s = {n["phone"][-4:] for n in TELEBIRR_NUMBERS}
            found_phones = result.get("all_phones") or []
            phone_ok = any(p[-4:] in our_last4s for p in found_phones)

            # Fraud prevention: reject anything older than 60 minutes if a
            # date is present (stops reuse of an old/leaked receipt number).
            freshness_ok = True
            if result.get("date_text"):
                parsed_dt = None
                for fmt in ("%d/%m/%Y, %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y, %H:%M", "%d/%m/%Y %H:%M"):
                    try:
                        parsed_dt = datetime.strptime(result["date_text"].strip(), fmt)
                        break
                    except ValueError:
                        continue
                if parsed_dt:
                    age_seconds = (datetime.now() - parsed_dt).total_seconds()
                    freshness_ok = -300 <= age_seconds <= 3600

            ceiling_ok = result["amount"] <= AUTO_APPROVE_MAX_AMOUNT

            verified = amount_ok and phone_ok and freshness_ok and ceiling_ok
            verified_amount = result["amount"]
            if not verified:
                result["debug"] = (
                    f"amount_ok={amount_ok} phone_ok={phone_ok} freshness_ok={freshness_ok} "
                    f"ceiling_ok={ceiling_ok} stated={stated_amount} raw={result}"
                )

        if verified:
            success, err = _credit_deposit_wallet(user_id, verified_amount)
            if success:
                deposits_ref.push({
                    "by": user_id,
                    "name": data.get("name", "Player"),
                    "amount": verified_amount,
                    "smsText": text,
                    "txnId": receipt_no,
                    "status": "approved",
                    "autoVerified": True,
                })
                await update.message.reply_text(
                    f"✅ Your deposit of {verified_amount} ETB is Approved.\nRef: {receipt_no}"
                )
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"✅ Auto-approved deposit: {data.get('name', 'Player')} +{verified_amount} coins (Ref {receipt_no}). No action needed.",
                    )
                except Exception as e:
                    log.warning(f"Could not send admin FYI for auto-approved deposit: {e}")
                return
            # Verified but the wallet credit itself failed -- fall through to
            # the pending/admin path below instead of losing the deposit.
            result["debug"] = f"verified but wallet credit failed: {err}"
            log.warning(f"Auto-verified but wallet credit failed for {receipt_no}: {err}")

        # --- Could not auto-verify (or credit failed) -- hybrid fallback:
        # hand off to the admin for manual approve/reject instead of
        # dead-ending the user, and include the real debug evidence so the
        # auto-verify parser can actually be fixed based on facts.
        key = deposits_ref.push({
            "by": user_id,
            "name": data.get("name", "Player"),
            "amount": stated_amount,
            "smsText": text,
            "txnId": receipt_no,
            "status": "pending",
        }).key
        await update.message.reply_text(
            "⏳ በራስ-ሰር ማረጋገጥ አልቻልንም። ወደ አድሚን ተልኳል፣ በቅርቡ በእጅ ይረጋገጥልዎታል።"
        )
        _notify_admin_deposit(key, {
            "name": data.get("name", "Player"),
            "amount": stated_amount,
            "smsText": text,
            "txnId": receipt_no,
            "debug": result.get("debug"),
        })

    # ---- Withdraw flow: amount -> phone ----
    elif flow == "withdraw_amount":
        wallet = _get_wallet(user_id)
        if not text.isdigit() or int(text) < 20:
            await update.message.reply_text("ዝቅተኛው መጠን 20 ብር ነው። እባክዎ ትክክለኛ ቁጥር ያስገቡ።")
            return
        amount = int(text)
        if amount > wallet.get("main", 0):
            await update.message.reply_text(
                f"⚠️ You only have {wallet.get('main', 0)} withdrawable coins. Send a smaller amount."
            )
            return
        data["amount"] = amount
        context.user_data["flow"] = "withdraw_phone"
        await update.message.reply_text("Which phone number should the payout be sent to?")

    elif flow == "withdraw_phone":
        user_id_str = user_id
        amount = data["amount"]
        db.reference(f"users/{user_id_str}").update({"phone": text})

        def deduct(current):
            current = current or {"main": 0, "play": 0, "deposited": 0}
            if current.get("main", 0) < amount:
                return current  # abort — balance changed since we checked
            current["main"] = current.get("main", 0) - amount
            return current

        result = _wallet_ref(user_id_str).transaction(deduct)
        # python-firebase-admin's transaction() returns the committed value
        key = withdrawals_ref.push({
            "by": user_id_str,
            "name": data.get("name", "Player"),
            "amount": amount,
            "phone": text,
            "status": "pending",
        }).key
        context.user_data["flow"] = None
        context.user_data["flow_data"] = {}
        await update.message.reply_text(
            f"⏳ Withdrawal request of {amount} coins submitted (ID {key}). "
            f"Waiting for admin approval."
        )


def _credit_deposit_wallet(user_id, amount):
    """
    Credit a deposit amount to a user's Play Wallet. Returns (True, None) on
    success or (False, error) on failure. Shared by both the manual
    admin-approve path and the automatic receipt-verification path so both
    stay consistent.
    """
    wallet_ref = db.reference(f"users/{user_id}/wallet")

    def credit(current):
        current = current or {"main": 0, "play": 0, "deposited": 0}
        current["play"] = current.get("play", 0) + amount
        current["deposited"] = current.get("deposited", 0) + amount
        return current

    try:
        wallet_ref.transaction(credit)
        return True, None
    except Exception as e:
        log.exception(f"Wallet credit FAILED for user {user_id}, amount {amount}")
        return False, str(e)


# ---- Approve/Reject button handler (admin only) ----
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)

    if query.from_user.id != ADMIN_CHAT_ID:
        await _safe_answer(query, "❌ You are not authorized.", show_alert=True)
        return

    action, kind, key = query.data.split(":", 2)  # e.g. "approve:withdrawal:ABC123"

    if kind == "withdrawal":
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

    elif kind == "deposit":
        record = deposits_ref.child(key).get()
        if not record:
            await query.edit_message_text("⚠️ Record not found (maybe already handled).")
            return
        if record.get("status") != "pending":
            await query.edit_message_text(f"ℹ️ Already {record.get('status')}.")
            return

        user_id = str(record["by"])
        amount = record.get("amount")
        txn_id = record.get("txnId")

        if action == "approve":
            # Credit the wallet FIRST, only mark "approved" after the credit
            # actually succeeds -- if it fails, the deposit stays "pending"
            # (never silently lost) and the admin is told directly so they
            # can retry the approve.
            success, err = _credit_deposit_wallet(user_id, amount)
            if not success:
                await query.edit_message_text(
                    f"⚠️ Wallet credit FAILED for {record.get('name')} (+{amount}). "
                    f"Deposit left pending -- please retry approve. Error: {err}"
                )
                return
            deposits_ref.child(key).update({"status": "approved"})
            await query.edit_message_text(
                f"✅ Approved deposit of {amount} coins for {record.get('name')} (Ref {txn_id})."
            )
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"✅ Your deposit of {amount} ETB is Approved.\nRef: {txn_id}",
                )
            except Exception as e:
                log.warning(f"Could not notify user {user_id} of deposit approval: {e}")
        else:
            deposits_ref.child(key).update({"status": "rejected"})
            # Release the reserved receipt/txn ID so the user can resubmit
            # (e.g. after correcting a typo in the SMS text).
            if txn_id:
                used_deposit_ids_ref.child(txn_id).delete()
            await query.edit_message_text(
                f"❌ Rejected deposit of {amount} coins for {record.get('name')} (Ref {txn_id})."
            )
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=(
                        f"❌ Your deposit submission (Ref {txn_id}) could not be verified. "
                        f"እባክዎ ትክክለኛውን ደረሰኝ በድጋሚ ይላኩ ወይም @{SUPPORT_USERNAME} ላይ ይፃፉልን።"
                    ),
                )
            except Exception as e:
                log.warning(f"Could not notify user {user_id} of deposit rejection: {e}")


# ---- Firebase realtime listeners: notify admin of new pending requests ----
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


def _notify_admin_deposit(key, record):
    text = (
        f"🪙 New Deposit Request\n"
        f"Name: {record.get('name')}\n"
        f"Amount: {record.get('amount')} ETB\n"
        f"Ref/txn ID: {record.get('txnId')}\n"
        f"SMS:\n{record.get('smsText')}\n"
    )
    debug = record.get("debug")
    if debug:
        # Real evidence of why auto-verify couldn't confirm this one --
        # lets us actually fix the parser instead of guessing.
        text += f"\n🔧 Auto-verify debug: {debug}\n"
    text += f"Request ID: {key}"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve:deposit:{key}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject:deposit:{key}"),
    ]])
    _send_to_admin(text, keyboard)


def _send_to_admin(text, keyboard):
    # Firebase's .listen() callbacks run on a background thread, but sending
    # a Telegram message is an async operation that must run on the bot's
    # own event loop. run_coroutine_threadsafe bridges the two safely.
    #
    # main_loop is set once inside on_startup(), which runs *after*
    # Application.run_polling() has created and started its own internal
    # event loop. Grabbing the loop that way (instead of the old
    # asyncio.get_event_loop() call at import time) guarantees this is the
    # SAME loop the bot is actually polling on -- otherwise the coroutine
    # gets scheduled on a dead/idle loop and silently never sends.
    if main_loop is None:
        log.warning("main_loop not ready yet; dropping admin notification.")
        return
    coro = app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, reply_markup=keyboard)
    asyncio.run_coroutine_threadsafe(coro, main_loop)


# ---- Startup hook: capture the *real* running event loop ----
main_loop = None


async def on_startup(application):
    global main_loop
    main_loop = asyncio.get_running_loop()
    log.info("Event loop captured; admin notifications are now live.")


# ---- Global error handler: logs any unhandled exception instead of
# letting it crash the whole bot process (which is what was happening
# before, e.g. on "query is too old" errors from slow/expired callback
# queries). ----
async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    log.error("Unhandled exception while processing an update", exc_info=context.error)


def main():
    global app
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("deposit", deposit_command))
    app.add_handler(CommandHandler("withdraw", withdraw_command))
    app.add_handler(CommandHandler("play", play_command))
    app.add_handler(CommandHandler("instruction", instruction_command))
    app.add_handler(CommandHandler("contactsupport", contactsupport_command))
    app.add_handler(CommandHandler("invite", invite_command))
    app.add_handler(CallbackQueryHandler(menu_handler, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(deposit_payment_handler, pattern=r"^deppay:"))
    app.add_handler(CallbackQueryHandler(handle_button, pattern=r"^(approve|reject):"))
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Start Firebase realtime listeners (each runs on its own background thread)
    withdrawals_ref.listen(on_withdrawal_change)

    # Start the keep-alive web server on a background thread
    threading.Thread(target=run_web_server, daemon=True).start()

    log.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
