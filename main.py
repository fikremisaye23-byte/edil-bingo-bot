"""
Temerachi Bingo - Admin Bot (Production Version - Fixed)
---------------------------------------------
የተሻሻለ ስሪት ከተሻሻለ የገንዘብ አያያዝ፣ የተሻሻለ ስህተት አያያዝ እና ከindex.html ጋር የተጣጣመ
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
from urllib.parse import parse_qsl

import firebase_admin
import telegram
from firebase_admin import auth as firebase_auth, credentials, db
from flask import Flask, jsonify, request
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
# Configuration
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
FIREBASE_SERVICE_ACCOUNT_JSON = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
ADMIN_CHAT_ID = 7078415767
MINI_APP_URL = "https://fikremisaye23-byte.github.io/bingo-game/?v=2"
SUPPORT_USERNAME = "Temerachibingosupport"
FIREBASE_DATABASE_URL = "https://edil-bingo-default-rtdb.firebaseio.com"

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")
if not FIREBASE_SERVICE_ACCOUNT_JSON:
    raise ValueError("FIREBASE_SERVICE_ACCOUNT_JSON environment variable is required")

# ============================================================

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("firebase_admin").setLevel(logging.WARNING)

# ============================================================
# Firebase Setup
# ============================================================
service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})

deposits_ref = db.reference("transactions/deposits")
withdrawals_ref = db.reference("transactions/withdrawals")
used_deposit_ids_ref = db.reference("transactions/usedDepositIds")
pending_deposits_ref = db.reference("transactions/pendingDeposits")
deposit_rate_limits_ref = db.reference("transactions/depositRateLimits")

# ============================================================
# Wallet Functions (FIXED)
# ============================================================

def _wallet_ref(user_id: str):
    return db.reference(f"users/{user_id}/wallet")


def _get_wallet(user_id: str) -> Dict[str, float]:
    w = _wallet_ref(user_id).get()
    if w is None:
        _wallet_ref(user_id).set({"main": 0, "play": 0, "deposited": 0})
        return {"main": 0, "play": 0, "deposited": 0}
    return {
        "main": w.get("main", 0),
        "play": w.get("play", 0),
        "deposited": w.get("deposited", 0)
    }


def _get_wallet_safe(user_id: str) -> Dict[str, float]:
    try:
        return _get_wallet(user_id)
    except Exception as e:
        log.error(f"Error getting wallet for {user_id}: {e}")
        return {"main": 0, "play": 0, "deposited": 0}


def _update_wallet(user_id: str, main_delta: float = 0, play_delta: float = 0, deposited_delta: float = 0) -> Tuple[bool, Optional[str]]:
    wallet_ref = _wallet_ref(user_id)
    abort_holder = {"aborted": False}

    def update(current):
        if current is None:
            current = {"main": 0, "play": 0, "deposited": 0}
        new_main = current.get("main", 0) + main_delta
        new_play = current.get("play", 0) + play_delta
        new_deposited = current.get("deposited", 0) + deposited_delta
        if new_main < 0 or new_play < 0 or new_deposited < 0:
            abort_holder["aborted"] = True
            return current  # abort — insufficient balance, leave unchanged
        current["main"] = new_main
        current["play"] = new_play
        current["deposited"] = new_deposited
        return current
    
    try:
        result = wallet_ref.transaction(update)
        if result is None:
            return False, "Transaction failed"
        if abort_holder["aborted"]:
            return False, "Insufficient balance"
        return True, None
    except Exception as e:
        log.error(f"Wallet update failed for {user_id}: {e}")
        return False, str(e)


def _credit_deposit_wallet(user_id: str, amount: float) -> Tuple[bool, Optional[str]]:
    return _update_wallet(user_id, play_delta=amount, deposited_delta=amount)


def _sms_amount_mismatch(record: Dict[str, Any]) -> Optional[float]:
    """Compares the amount the user stated in-chat against the amount the
    bot parsed out of their pasted Telebirr SMS (stored on the pending
    record as parsed_data.transfer_amount at submission time). Returns the
    SMS amount if it differs from the stated amount by more than a small
    rounding tolerance, so the caller can hold off crediting and ask the
    admin to confirm; returns None if they match (or the SMS amount could
    not be read, in which case there's nothing to compare against)."""
    parsed = record.get("parsed_data") or {}
    sms_amount_raw = parsed.get("transfer_amount")
    if not sms_amount_raw:
        return None
    try:
        sms_amount = float(sms_amount_raw)
    except (TypeError, ValueError):
        return None
    try:
        stated_amount = float(record.get("amount", 0) or 0)
    except (TypeError, ValueError):
        return None
    if abs(sms_amount - stated_amount) > 1:  # >1 ብር tolerance for rounding
        return sms_amount
    return None


def _debit_withdrawal(user_id: str, amount: float) -> Tuple[bool, Optional[str]]:
    return _update_wallet(user_id, main_delta=-amount)


def _refund_withdrawal(user_id: str, amount: float) -> Tuple[bool, Optional[str]]:
    return _update_wallet(user_id, main_delta=amount)


# ============================================================
# Rate Limiting
# ============================================================
# Persisted in Firebase (transactions/depositRateLimits/{user_id}) rather
# than kept in a plain in-memory dict, so the limit survives a bot
# restart/redeploy on Render instead of silently resetting to zero.
DEPOSIT_RATE_LIMIT_MAX = 5
DEPOSIT_RATE_LIMIT_WINDOW = 600


def _deposit_rate_limited(user_id: str) -> bool:
    now = time.time()
    limited_holder = {"limited": False}

    def update(current):
        recent = [t for t in (current or []) if now - t < DEPOSIT_RATE_LIMIT_WINDOW]
        recent.append(now)
        limited_holder["limited"] = len(recent) > DEPOSIT_RATE_LIMIT_MAX
        return recent

    try:
        deposit_rate_limits_ref.child(str(user_id)).transaction(update)
    except Exception as e:
        # Fail open on infra errors, same spirit as the old in-memory
        # version -- a rate-limit outage shouldn't block real deposits.
        log.error(f"Rate limit check failed for {user_id}: {e}")
        return False

    return limited_holder["limited"]


# ============================================================
# Telebirr Functions
# ============================================================
TELEBIRR_NUMBERS = [
    {"phone": "0923160399", "name": "Fikre"},
    {"phone": "0900619106", "name": "Fikr"},
    {"phone": "0921466712", "name": "asebechimariyam"},
]


def get_next_telebirr_number() -> Dict[str, str]:
    rotation_ref = db.reference("deposits/rotationIndex")
    try:
        idx = rotation_ref.transaction(lambda current: (current + 1) if isinstance(current, int) else 0)
        if not isinstance(idx, int):
            idx = 0
    except Exception:
        idx = random.randrange(len(TELEBIRR_NUMBERS))
    return TELEBIRR_NUMBERS[idx % len(TELEBIRR_NUMBERS)]


def parse_telebirr_sms_improved(text: str) -> Optional[Dict[str, Any]]:
    if not text or len(text.strip()) < 10:
        return None
    
    amount_patterns = [
        r'([\d,]+(?:\.\d+)?)\s*ብር',
        r'([\d,]+(?:\.\d+)?)\s*ETB',
        r'([\d,]+(?:\.\d+)?)\s*Birr',
        r'([\d,]+(?:\.\d+)?)\s*Br',
        r'ETB\s*([\d,]+(?:\.\d+)?)',
        r'Birr\s*([\d,]+(?:\.\d+)?)',
        r'amount[:\s]*([\d,]+(?:\.\d+)?)',
    ]
    
    amounts = []
    for pattern in amount_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                amt = float(match.replace(',', ''))
                amounts.append(amt)
            except ValueError:
                continue
    
    # Find a phone-like substring (masked like "251*...0399" or a plain
    # 10-digit number), then normalize to just its last 4 digits. Doing the
    # digit-suffix extraction here in Python — instead of relying on each
    # regex to capture the right group — avoids a crash: two of these
    # patterns have no capturing group at all, so calling .group(1) on a
    # match from them raises IndexError and would take the whole handler
    # down for any SMS with an unmasked phone number.
    phone_patterns = [
        r'\(?251\d\*+\d{2,4}\)?',
        r'0?9\d{8}',
        r'2519\d{8}',
    ]
    phone_suffix = ""
    for pattern in phone_patterns:
        match = re.search(pattern, text)
        if match:
            digits_only = re.sub(r'\D', '', match.group(0))
            phone_suffix = digits_only[-4:] if len(digits_only) >= 4 else digits_only
            break
    
    txn_patterns = [
        r'ቁጥርዎ\s*(\S+)\s*ነ[ዉው]',
        r'የሂሳብ እንቅስቃሴ ቁጥርዎ\s*(\S+)',
        r'Transaction\s*(?:ID|No|Number)[:\s]*(?:is[:\s]*)?([A-Z0-9]{6,20})',
        r'Ref(?:erence)?[:\s]*([A-Z0-9]{6,20})',
        r'([A-Z0-9]{8,14})\s*(?:ነዉ|ነው|is|$)',
    ]
    
    txn_match = None
    for pattern in txn_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            txn_match = match
            break
    
    receipt_match = re.search(r'transactioninfo\.ethiotelecom\.et/receipt/([A-Za-z0-9]+)', text)

    name_match = re.search(r'\bto\s+([A-Za-z][A-Za-z\.\s]{1,40}?)\s*\(', text)

    # The actual amount the person sent — not the service fee, VAT, or
    # resulting account balance that also appear (and also match) elsewhere
    # in the same SMS. Look specifically at the figure tied to "transferred".
    transferred_match = re.search(
        r'transferred\s+(?:ETB|Birr|ብር)?\s*([\d,]+(?:\.\d+)?)', text, re.IGNORECASE
    )
    if transferred_match:
        transfer_amount = transferred_match.group(1).replace(',', '')
    elif amounts:
        transfer_amount = str(amounts[0])
    else:
        transfer_amount = None

    if not amounts and not txn_match:
        return None
    
    return {
        "amounts": amounts,
        "transfer_amount": transfer_amount,
        "phone": phone_suffix,
        "txn_id": txn_match.group(1) if txn_match else None,
        "receipt_id": receipt_match.group(1) if receipt_match else None,
        "recipient_name": name_match.group(1).strip() if name_match else "",
        "raw_text": text,
    }


# ============================================================
# Keyboard Definitions
# ============================================================
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


def main_menu_keyboard() -> InlineKeyboardMarkup:
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


def deposit_payment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Telebirr", callback_data="deppay:telebirr")],
        [InlineKeyboardButton("Cancel", callback_data="deppay:cancel")],
    ])


def admin_deposit_keyboard(deposit_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:deposit:{deposit_key}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:deposit:{deposit_key}"),
        ]
    ])


def admin_deposit_force_keyboard(deposit_key: str) -> InlineKeyboardMarkup:
    # Shown only after an amount mismatch warning — requires a deliberate
    # second tap so a mismatched deposit is never credited by the same
    # single tap as a normal, matching one.
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ Approve Anyway", callback_data=f"approveforce:deposit:{deposit_key}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:deposit:{deposit_key}"),
        ]
    ])


# ============================================================
# Flask Keep-Alive Server
# ============================================================
flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "Temerachi Bingo bot is running."


@flask_app.route("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ============================================================
# Mini App Authentication
# ------------------------------------------------------------
# The Mini App used to sign into Firebase anonymously, then trust whatever
# Telegram.WebApp.initDataUnsafe.user.id it read client-side as the
# identity for every wallet read/write. initDataUnsafe is exactly that --
# unsafe -- it isn't cryptographically checked, so it can be edited in the
# browser before the page reads it. Combined with open Firebase rules
# (any authenticated client, including an anonymous one, could read/write
# any path), this meant anyone could act as any user's wallet.
#
# This endpoint verifies initData the way Telegram documents: recompute
# the HMAC-SHA256 hash Telegram signs it with (using the bot token as the
# secret) and compare. Only if that matches do we mint a Firebase custom
# token for that exact Telegram user id, which the Mini App then signs in
# with instead of anonymous auth. Firebase rules (updated separately, in
# the Firebase console) can then require auth.uid == the wallet's own
# path, which anonymous auth could never satisfy.
# ============================================================
def _verify_telegram_init_data(init_data: str, max_age_seconds: int = 86400) -> Optional[str]:
    """Returns the Telegram user id (as a string) if init_data is a
    genuine, sufficiently-recent payload from Telegram for this bot;
    None if the signature is missing/wrong or the data is stale."""
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    auth_date = parsed.get("auth_date")
    try:
        if not auth_date or (time.time() - int(auth_date)) > max_age_seconds:
            return None
    except (TypeError, ValueError):
        return None

    try:
        user_obj = json.loads(parsed.get("user", "{}"))
        user_id = user_obj.get("id")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

    return str(user_id) if user_id else None


def _cors(resp):
    # Mini App is hosted on GitHub Pages, this bot on Render -- different
    # origins, so the browser needs this to allow the fetch() call at all.
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@flask_app.route("/webapp-auth", methods=["POST", "OPTIONS"])
def webapp_auth():
    if request.method == "OPTIONS":
        return _cors(flask_app.make_default_options_response())

    body = request.get_json(silent=True) or {}
    user_id = _verify_telegram_init_data(body.get("initData", ""))
    if not user_id:
        resp = jsonify({"error": "invalid or expired initData"})
        resp.status_code = 401
        return _cors(resp)

    try:
        token = firebase_auth.create_custom_token(user_id)
        token_str = token.decode("utf-8") if isinstance(token, bytes) else token
    except Exception as e:
        log.error(f"Failed to mint custom token for {user_id}: {e}")
        resp = jsonify({"error": "token mint failed"})
        resp.status_code = 500
        return _cors(resp)

    return _cors(jsonify({"token": token_str, "userId": user_id}))


def run_web_server():
    flask_app.run(host="0.0.0.0", port=8080)


# ============================================================
# Helper Functions
# ============================================================
async def _safe_answer(query, *args, **kwargs):
    try:
        await query.answer(*args, **kwargs)
    except telegram.error.BadRequest as e:
        log.warning(f"Could not answer callback query (likely expired): {e}")


async def _run_menu_action(action: str, reply_target, user, context):
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
        wallet = _get_wallet_safe(user_id)
        user_record = db.reference(f"users/{user_id}").get() or {}
        display_name = user_record.get("name", name)
        phone = user_record.get("phone", "አልተመዘገበም")
        main_bal = wallet.get("main", 0)
        play_bal = wallet.get("play", 0)
        deposited_bal = wallet.get("deposited", 0)
        coin_total = main_bal + play_bal
        
        await reply_target.reply_text(
            "💼 Account Info\n\n"
            "```\n"
            f"Name:               {display_name}\n"
            f"Phone:              {phone}\n"
            f"Main wallet:        {main_bal:.2f}\n"
            f"Play wallet:        {play_bal:.2f}\n"
            f"Deposited total:    {deposited_bal:.2f}\n"
            f"Total:              {coin_total:.2f}\n"
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
        wallet = _get_wallet_safe(user_id)
        main_bal = wallet.get("main", 0)
        deposited_bal = wallet.get("deposited", 0)
        if main_bal <= 0:
            await reply_target.reply_text(
                "⚠️ Your main wallet is empty, there's nothing to withdraw.\n\n"
                f"💰 Main wallet: {main_bal:.2f} ብር"
            )
            return
        # Bonus-only players (never made a real Telebirr deposit) cannot
        # withdraw winnings won purely off the free registration bonus --
        # they must deposit first. Mirrors the same check added in
        # index.html's handleWithdraw(), here too so it can't be bypassed
        # by going through the bot chat directly instead of the Mini App's
        # Withdraw button.
        if deposited_bal <= 0:
            await reply_target.reply_text(
                "🚫 Withdraw ለማድረግ መጀመሪያ ቢያንስ አንድ ጊዜ ዲፖዚት ማድረግ አለብዎት።",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🪙 Deposit", callback_data="menu:deposit")]]),
            )
            return
        context.user_data["flow"] = "withdraw_amount"
        context.user_data["flow_data"] = {"name": name}
        await reply_target.reply_text(
            f"💰 ማውጣት የሚፈልጉትን የገንዘብ መጠን ያስገቡ?\n\n"
            f"📊 Available: {main_bal:.2f} ብር\n"
            f"⚠️ Minimum: 20 ብር"
        )


# ============================================================
# Command Handlers
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["flow"] = None
    caption = "Welcome to Temerachi Bingo! Choose an Option below."

    try:
        photos = await context.bot.get_user_profile_photos(context.bot.id, limit=1)
        if photos.total_count > 0:
            photo_file_id = photos.photos[0][-1].file_id
            await update.message.reply_photo(
                photo=photo_file_id,
                caption=caption,
                reply_markup=main_menu_keyboard(),
            )
            return
    except Exception as e:
        log.warning(f"Could not fetch bot profile photo, falling back to text: {e}")

    await update.message.reply_text(caption, reply_markup=main_menu_keyboard())


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    action = query.data.split(":", 1)[1]
    await _run_menu_action(action, query.message, query.from_user, context)


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


async def _finalize_deposit_approval(context, query, record: Dict[str, Any], key: str):
    """Credits the wallet, records the approved deposit, and notifies both
    the admin and the user. Shared by the normal 'approve' path and the
    'approveforce' path (used after an amount-mismatch warning) so the
    crediting logic only exists once.

    Guarded by a Firebase transaction that atomically flips status from
    "pending" to "processing" before any money moves -- a double-tap on the
    Approve button, or Telegram redelivering the same callback (which does
    happen on flaky connections), would otherwise both pass the earlier
    plain "if status == pending" check and credit the wallet twice."""
    amount = record.get("amount", 0)
    user_id = record.get("by")
    name = record.get("name", "Player")

    record_ref = pending_deposits_ref.child(key)
    claim = record_ref.transaction(
        lambda current: {**current, "status": "processing"}
        if current and current.get("status") == "pending"
        else current
    )
    if not claim or claim.get("status") != "processing":
        await query.edit_message_text("ℹ️ Already handled (double tap or duplicate action ignored).")
        return

    success, err = _credit_deposit_wallet(user_id, amount)
    if not success:
        # Roll the claim back to pending so a retry (or the admin approving
        # again) is still possible after a transient wallet-write failure.
        record_ref.update({"status": "pending"})
        await query.edit_message_text(f"❌ Failed to credit wallet: {err}")
        return

    pending_deposits_ref.child(key).update({
        "status": "approved",
        "approved_at": datetime.now().isoformat(),
        "approved_by": "admin"
    })

    deposits_ref.push({
        "by": user_id,
        "name": name,
        "amount": amount,
        "phone": record.get("phone", ""),
        "txnId": record.get("txnId", ""),
        "status": "approved",
        "autoVerified": False,
        "adminApproved": True,
        "timestamp": datetime.now().isoformat(),
    })

    await query.edit_message_text(
        f"✅ Approved deposit of {amount:.2f} ብር for {name}.\n"
        f"Ref: {record.get('txnId', 'N/A')}"
    )

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ የ {amount:.2f} ብር ዲፖዚት ጥያቄዎ ጸድቋል!\n"
                 f"በ Play Wallet ውስጥ ገንዘብዎ ተጨምሯል።\n\n"
                 f"Ref: {record.get('txnId', 'N/A')}"
        )
    except Exception as e:
        log.warning(f"Could not notify user of deposit approval: {e}")


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)

    if query.from_user.id != ADMIN_CHAT_ID:
        await _safe_answer(query, "❌ You are not authorized.", show_alert=True)
        return

    parts = query.data.split(":")
    if len(parts) < 3:
        await query.edit_message_text("⚠️ Invalid action format.")
        return

    action, kind, key = parts[0], parts[1], parts[2]

    # ==================== DEPOSIT APPROVAL ====================
    if kind == "deposit":
        record = pending_deposits_ref.child(key).get()
        if not record:
            await query.edit_message_text("⚠️ Deposit record not found (maybe already handled).")
            return
        
        if record.get("status") != "pending":
            await query.edit_message_text(f"ℹ️ Already {record.get('status')}.")
            return

        if action == "approve":
            # Don't credit yet if the stated amount and the SMS-parsed amount
            # disagree -- that mismatch is exactly the case a human reviewer
            # exists to catch. Surface it and require a deliberate second
            # tap ("Approve Anyway") instead of crediting on the first tap.
            mismatched_sms_amount = _sms_amount_mismatch(record)
            if mismatched_sms_amount is not None:
                stated_amount = record.get("amount", 0)
                await query.edit_message_text(
                    f"⚠️ Amount mismatch for {record.get('name', 'Player')}!\n\n"
                    f"Stated (by user): {stated_amount} ብር\n"
                    f"Parsed from SMS: {mismatched_sms_amount:.2f} ብር\n"
                    f"Ref: {record.get('txnId', 'N/A')}\n\n"
                    f"Double-check the SMS before approving.",
                    reply_markup=admin_deposit_force_keyboard(key),
                )
                return

            await _finalize_deposit_approval(context, query, record, key)

        elif action == "approveforce":
            # Admin already saw the mismatch warning and confirmed -- credit
            # using the stated amount, same as a normal approval.
            await _finalize_deposit_approval(context, query, record, key)

        else:
            record_ref = pending_deposits_ref.child(key)
            claimed = record_ref.transaction(
                lambda current: {**current, "status": "rejected", "rejected_at": datetime.now().isoformat(), "rejected_by": "admin"}
                if current and current.get("status") == "pending"
                else current
            )
            if not claimed or claimed.get("status") != "rejected":
                await query.edit_message_text("ℹ️ Already handled (double tap or duplicate action ignored).")
                return

            await query.edit_message_text(
                f"❌ Rejected deposit for {record.get('name', 'User')}.\n"
                f"Ref: {record.get('txnId', 'N/A')}"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=record.get("by"),
                    text=f"❌ የ {record.get('amount', 0):.2f} ብር ዲፖዚት ጥያቄዎ ተሰርዟል።\n"
                         f"እባክዎ ደረሰኝዎን አረጋግጠው እንደገና ይሞክሩ።\n\n"
                         f"Ref: {record.get('txnId', 'N/A')}"
                )
            except Exception as e:
                log.warning(f"Could not notify user of deposit rejection: {e}")

    # ==================== WITHDRAWAL APPROVAL ====================
    elif kind == "withdrawal":
        record = withdrawals_ref.child(key).get()
        if not record:
            await query.edit_message_text("⚠️ Record not found (maybe already handled).")
            return
        if record.get("status") != "pending":
            await query.edit_message_text(f"ℹ️ Already {record.get('status')}.")
            return

        if action == "approve":
            record_ref = withdrawals_ref.child(key)
            claimed = record_ref.transaction(
                lambda current: {**current, "status": "approved", "approved_at": datetime.now().isoformat(), "approved_by": "admin"}
                if current and current.get("status") == "pending"
                else current
            )
            if not claimed or claimed.get("status") != "approved":
                await query.edit_message_text("ℹ️ Already handled (double tap or duplicate action ignored).")
                return

            await query.edit_message_text(
                f"✅ Approved withdrawal of {record.get('amount', 0):.2f} ብር for {record.get('name')}.\n"
                f"📞 Send to: {record.get('phone')}\n"
                f"⚠️ Remember to actually SEND the money via Telebirr!"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=record["by"],
                    text=f"✅ የ {record.get('amount', 0):.2f} ብር ማውጫ ጥያቄዎ ጸድቋል!\n"
                         f"📞 ገንዘቡ ወደ {record.get('phone')} በቴሌብር ይላካል።\n\n"
                         f"📋 Ref: {key}"
                )
            except Exception as e:
                log.warning(f"Could not notify user of withdrawal approval: {e}")
                
        else:
            user_id = str(record["by"])
            amount = record.get("amount", 0)
            name = record.get("name", "User")

            record_ref = withdrawals_ref.child(key)
            claimed = record_ref.transaction(
                lambda current: {**current, "status": "processing"}
                if current and current.get("status") == "pending"
                else current
            )
            if not claimed or claimed.get("status") != "processing":
                await query.edit_message_text("ℹ️ Already handled (double tap or duplicate action ignored).")
                return

            success, err = _refund_withdrawal(user_id, amount)
            
            record_ref.update({
                "status": "rejected",
                "rejected_at": datetime.now().isoformat(),
                "rejected_by": "admin",
                "refunded": success
            })
            
            if success:
                await query.edit_message_text(
                    f"❌ Rejected withdrawal for {name}.\n"
                    f"💰 {amount:.2f} ብር refunded to Main Wallet."
                )
            else:
                await query.edit_message_text(
                    f"❌ Rejected withdrawal for {name}.\n"
                    f"⚠️ BUT refund FAILED: {err}\n"
                    f"Please check manually!"
                )
            
            try:
                refund_msg = "✅ ገንዘብዎ ወደ Main Wallet ተመልሷል።" if success else "⚠️ እባክዎ ድጋፍ ያግኙ።"
                await context.bot.send_message(
                    chat_id=record["by"],
                    text=f"❌ የ {amount:.2f} ብር ማውጫ ጥያቄዎ ተሰርዟል።\n"
                         f"{refund_msg}\n\n"
                         f"📋 Ref: {key}"
                )
            except Exception as e:
                log.warning(f"Could not notify user of withdrawal rejection: {e}")


# ============================================================
# Message Handlers
# ============================================================
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

    # The 10-birr registration bonus used to only be granted by the Mini
    # App's own handleRegister(). A player who registers here in the bot
    # chat first (sharing their contact) never got it, and the Mini App
    # would then see registered=true already and skip granting it too --
    # leaving them with a real "registered" account but a 0 balance. Grant
    # it here as well, guarded on the same "registered" flag both paths
    # already share, so it's still only ever given once no matter which
    # path a player registers through first.
    existing_record = db.reference(f"users/{user_id}").get() or {}
    already_registered = bool(existing_record.get("registered"))

    db.reference(f"users/{user_id}").update({
        "name": name,
        "phone": contact.phone_number,
        "registered": True,
        "registered_at": existing_record.get("registered_at") or datetime.now().isoformat(),
    })

    bonus_note = ""
    if not already_registered:
        success, err = _update_wallet(user_id, play_delta=10)
        if success:
            bonus_note = "\n🎉 10 free fun coins have been added to your balance."
        else:
            log.error(f"Failed to grant registration bonus to {user_id}: {err}")

    await update.message.reply_text(
        f"✅ Registered! Welcome, {name}.{bonus_note}",
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.message.reply_text(
        "Choose an option below:",
        reply_markup=main_menu_keyboard(),
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    flow = context.user_data.get("flow")
    if not flow:
        return

    user = update.effective_user
    user_id = str(user.id)
    text = (update.message.text or "").strip()
    data = context.user_data.setdefault("flow_data", {})

    # ==================== DEPOSIT FLOW ====================
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
            await update.message.reply_text(
                "🚫 በአጭር ጊዜ ውስጥ በጣም ብዙ ጥያቄ ልከዋል። እባክዎ ትንሽ ቆይተው ደግመው ይሞክሩ ወይም "
                f"@{SUPPORT_USERNAME} ላይ ይፃፉልን።"
            )
            return

        parsed = parse_telebirr_sms_improved(text)
        
        if not parsed:
            await update.message.reply_text(
                "🚫 ኤስኤምኤሱ ሊነበብ አልቻለም። እባክዎ ስልክዎ ላይ የገባውን ትክክለኛ ሚሴጅ (SMS) ሙሉ በሙሉ ኮፒ አድርገው ይላኩ፡፡\n\n"
                f"❓ለድጋፍ @{SUPPORT_USERNAME} ላይ ይፃፉልን"
            )
            return

        receipt_no = parsed.get("txn_id") or parsed.get("receipt_id")

        # Defense in depth: whatever the source, only accept a strictly
        # alphanumeric reference of a sane length before we ever use it to
        # build a URL or as a Firebase key.
        if receipt_no and not re.fullmatch(r"[A-Za-z0-9]{6,20}", receipt_no):
            receipt_no = None

        if not receipt_no:
            await update.message.reply_text(
                "🚫 የግብይት መለያ (Transaction ID) በኤስኤምኤስ ውስጥ አልተገኘም።\n\n"
                "ሙሉውን ኤስኤምኤስ ኮፒ አድርገው ይላኩ።\n\n"
                f"❓ለድጋፍ @{SUPPORT_USERNAME} ላይ ይፃፉልን"
            )
            return

        # Check whether the SMS shows the money was sent to one of our three
        # registered Telebirr numbers (matched on the masked suffix digits
        # Telebirr includes in the SMS, e.g. "0399" for "...0399"). This does
        # NOT block the deposit — our phone-format detection can't cover
        # every SMS wording, so a false negative here would wrongly reject a
        # legitimate deposit. Instead we surface the result to the admin
        # (below) so the human reviewer makes the final call.
        sms_phone_suffix = (parsed.get("phone") or "").strip()
        phone_ok = False
        if sms_phone_suffix:
            for num in TELEBIRR_NUMBERS:
                if num["phone"].endswith(sms_phone_suffix):
                    phone_ok = True
                    break

        # Atomically check-and-reserve this receipt/transaction ID before doing
        # anything else. A plain .get() read-then-decide here would leave a race
        # window: two near-simultaneous submissions of the same SMS (or the same
        # SMS resent while the first submission is still auto-verifying, which
        # can take up to 2 minutes) could both pass the check. Reserving it now,
        # up front -- and keeping the reservation even if auto-verify later fails
        # and the deposit falls back to admin review -- means the same receipt
        # can never end up as two separate pending/approved entries.
        already_used_holder = {"already_used": False}

        def reserve(current):
            if current:
                already_used_holder["already_used"] = True
                return current  # no-op — leave the existing reservation as-is
            return True

        used_deposit_ids_ref.child(receipt_no).transaction(reserve)

        if already_used_holder["already_used"]:
            await update.message.reply_text(
                "🚫 ይህ የደረሰኝ ቁጥር (transaction ID) ቀድሞ ጥቅም ላይ ውሏል።\n\n"
                f"❓ለድጋፍ @{SUPPORT_USERNAME} ላይ ይፃፉልን"
            )
            return

        stated_amount = data.get("amount")
        data["smsText"] = text
        data["txnId"] = receipt_no

        # No auto-approval at all: every deposit is routed to the admin for
        # manual approve/reject. Two reasons this is deliberate, not a
        # fallback: (1) the Ethio Telecom receipt page (the only real
        # third-party check we had) is unreachable from this host — every
        # request times out (confirmed via Render logs), so any "auto"
        # verification here could only ever be self-reported data (the SMS
        # text and amount both come from the same user submitting the
        # deposit) rather than an independent check; (2) the user weighed
        # that trade-off and explicitly chose full manual review over
        # auto-approving on self-reported data alone. The txn ID is still
        # atomically reserved above so the same receipt can never create two
        # separate pending requests, and rate limiting still applies.
        context.user_data["flow"] = None
        context.user_data["flow_data"] = {}

        pending_key = pending_deposits_ref.push({
            "by": user_id,
            "name": data.get("name", "Player"),
            "amount": stated_amount,
            "phone": data.get("payToPhone", ""),
            "smsText": text,
            "paidTo": data.get("payToPhone", ""),
            "txnId": receipt_no,
            "status": "pending",
            "timestamp": datetime.now().isoformat(),
            "parsed_data": parsed,
        }).key

        try:
            keyboard = admin_deposit_keyboard(pending_key)
            sms_amount_str = parsed.get("transfer_amount") or "N/A"
            sms_name = parsed.get("recipient_name") or "N/A"
            phone_flag = "✅ Match" if phone_ok else "⚠️ No match / not detected"
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    f"🪙 New Deposit Request\n"
                    f"Name (registered): {data.get('name', 'Player')}\n"
                    f"Amount (stated): {stated_amount} ብር\n"
                    f"Amount (from SMS): {sms_amount_str} ብር\n"
                    f"Recipient name (from SMS): {sms_name}\n"
                    f"Txn ID: {receipt_no}\n"
                    f"Phone: {data.get('payToPhone', '')}\n"
                    f"Phone match check: {phone_flag}\n\n"
                    f"📝 SMS:\n{text[:500]}"
                ),
                reply_markup=keyboard,
            )
        except Exception as e:
            log.warning(f"Could not notify admin: {e}")

        await update.message.reply_text(
            f"⏳ የዲፖዚት ጥያቄዎ ለአስተዳዳሪ ተልኳል።\n"
            f"📋 የደረሰኝ ቁጥር: {receipt_no}\n\n"
            f"እባክዎ ትንሽ ይጠብቁ፣ አስተዳዳሪው ያረጋግጥልዎታል።\n"
            f"ጥያቄ ካለዎት @{SUPPORT_USERNAME} ላይ ይፃፉልን።"
        )

    # ==================== WITHDRAW FLOW ====================
    elif flow == "withdraw_amount":
        wallet = _get_wallet_safe(user_id)
        main_bal = wallet.get("main", 0)
        
        if not text.isdigit():
            await update.message.reply_text(
                "⚠️ እባክዎ ትክክለኛ ቁጥር ያስገቡ።\n\n"
                f"📊 Available: {main_bal:.2f} ብር"
            )
            return
        
        amount = int(text)
        if amount < 20:
            await update.message.reply_text(
                f"⚠️ ዝቅተኛው መጠን 20 ብር ነው።\n\n"
                f"📊 Available: {main_bal:.2f} ብር"
            )
            return
        
        if amount > main_bal:
            await update.message.reply_text(
                f"⚠️ በቂ ገንዘብ የለህም!\n\n"
                f"📊 Available: {main_bal:.2f} ብር\n"
                f"💰 Requested: {amount} ብር"
            )
            return
        
        data["amount"] = amount
        context.user_data["flow"] = "withdraw_phone"
        await update.message.reply_text(
            f"✅ Amount {amount} ብር accepted.\n\n"
            f"📞 ገንዘቡ ወደ የትኛው የቴሌብር ቁጥር ይላክ?\n"
            f"ለምሳሌ: 0911223344"
        )

    elif flow == "withdraw_phone":
        user_id_str = user_id
        amount = data.get("amount", 0)
        phone = text.strip()
        
        if not phone or len(phone) < 8:
            await update.message.reply_text(
                "⚠️ እባክዎ ትክክለኛ የቴሌብር ቁጥር ያስገቡ።\n"
                "ለምሳሌ: 0911223344"
            )
            return
        
        db.reference(f"users/{user_id_str}").update({"phone": phone})
        
        success, err = _debit_withdrawal(user_id_str, amount)
        
        if not success:
            await update.message.reply_text(
                f"❌ ማውጫ ጥያቄ ሳይሳካ ቀረ: {err}\n\n"
                f"እባክዎ እንደገና ይሞክሩ ወይም @{SUPPORT_USERNAME} ያግኙ።"
            )
            context.user_data["flow"] = None
            context.user_data["flow_data"] = {}
            return
        
        key = withdrawals_ref.push({
            "by": user_id_str,
            "name": data.get("name", "Player"),
            "amount": amount,
            "phone": phone,
            "status": "pending",
            "timestamp": datetime.now().isoformat(),
        }).key
        
        context.user_data["flow"] = None
        context.user_data["flow_data"] = {}
        
        await update.message.reply_text(
            f"⏳ ማውጫ ጥያቄ ተልኳል!\n\n"
            f"💰 Amount: {amount:.2f} ብር\n"
            f"📞 Phone: {phone}\n"
            f"📋 Request ID: {key[:8]}\n\n"
            f"እባክዎ አስተዳዳሪው እስኪያረጋግጥ ይጠብቁ።"
        )
        
        try:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:withdrawal:{key}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject:withdrawal:{key}"),
            ]])
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    f"💸 New Withdrawal Request\n"
                    f"Name: {data.get('name', 'Player')}\n"
                    f"Amount: {amount:.2f} ብር\n"
                    f"Phone: {phone}\n"
                    f"Request ID: {key}"
                ),
                reply_markup=keyboard,
            )
        except Exception as e:
            log.warning(f"Could not notify admin of withdrawal: {e}")


# ============================================================
# Slash Commands
# ============================================================
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


# ============================================================
# Daily Report
# ============================================================
# What time to send the automatic daily report, in UTC (Render's server
# clock is UTC). 16:00 UTC = 19:00 East Africa Time (UTC+3) — "ማታ 1 ሰዓት".
# Change this single number to move the report time.
REPORT_HOUR_UTC = 16


def _sum_today(ref, day_str: str) -> Tuple[float, int]:
    """Sums the 'amount' field of every child record under `ref` whose
    'timestamp' falls on `day_str` (YYYY-MM-DD). Used for deposits/withdrawals,
    which are both stored the same way (one push() per transaction)."""
    records = ref.get() or {}
    total = 0.0
    count = 0
    for rec in records.values():
        if not isinstance(rec, dict):
            continue
        ts = rec.get("timestamp", "") or ""
        if ts.startswith(day_str):
            try:
                total += float(rec.get("amount", 0) or 0)
            except (TypeError, ValueError):
                pass
            count += 1
    return total, count


def _count_new_users_today(day_str: str) -> int:
    users = db.reference("users").get() or {}
    count = 0
    for rec in users.values():
        if not isinstance(rec, dict):
            continue
        ts = rec.get("registered_at", "") or ""
        if ts.startswith(day_str):
            count += 1
    return count


def _list_deposits_today(day_str: str) -> list:
    """Returns a list of every deposit record under deposits_ref (i.e. every
    admin-approved deposit) whose 'timestamp' falls on day_str (YYYY-MM-DD),
    each as a dict with name/phone/by(user id)/amount — for the detailed
    per-deposit section of the daily report."""
    records = deposits_ref.get() or {}
    result = []
    for rec in records.values():
        if not isinstance(rec, dict):
            continue
        ts = rec.get("timestamp", "") or ""
        if ts.startswith(day_str):
            result.append({
                "name": rec.get("name", "N/A"),
                "phone": rec.get("phone", "N/A"),
                "by": rec.get("by", "N/A"),
                "amount": rec.get("amount", 0),
            })
    return result


def _chunk_text(text: str, limit: int = 4000) -> list:
    """Splits text into chunks under Telegram's 4096-char message limit,
    breaking on line boundaries so no single deposit entry gets cut in half."""
    lines = text.split("\n")
    chunks = []
    current = ""
    for line in lines:
        candidate = (current + "\n" + line) if current else line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def send_daily_report(bot, chat_id: int = ADMIN_CHAT_ID, day_str: Optional[str] = None):
    day_str = day_str or datetime.now().strftime("%Y-%m-%d")
    total_deposits, deposit_count = _sum_today(deposits_ref, day_str)
    total_withdrawals, withdrawal_count = _sum_today(withdrawals_ref, day_str)
    new_users = _count_new_users_today(day_str)

    text = (
        f"📊 የዕለት ሪፖርት - {day_str}\n\n"
        f"💰 ዲፖዚት ጠቅላላ: {total_deposits:.2f} ብር ({deposit_count} ግብይቶች)\n"
        f"💸 ማውጫ ጠቅላላ: {total_withdrawals:.2f} ብር ({withdrawal_count} ግብይቶች)\n"
        f"📈 ተጣራ (Net): {total_deposits - total_withdrawals:.2f} ብር\n"
        f"👤 አዲስ የተመዘገቡ ተጠቃሚዎች: {new_users}"
    )
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        log.error(f"Failed to send daily report: {e}")

    # Follow-up message: detailed list of every deposit made today.
    deposits_today = _list_deposits_today(day_str)
    if not deposits_today:
        return

    lines = [f"📋 ዝርዝር ዲፖዚት - {day_str}\n"]
    for i, d in enumerate(deposits_today, start=1):
        lines.append(
            f"{i}. ስም: {d['name']}\n"
            f"   ስልክ: {d['phone']}\n"
            f"   ID: {d['by']}\n"
            f"   የብር መጠን: {d['amount']:.2f} ብር\n"
        )
    detail_text = "\n".join(lines)

    for chunk in _chunk_text(detail_text):
        try:
            await bot.send_message(chat_id=chat_id, text=chunk)
        except Exception as e:
            log.error(f"Failed to send detailed deposit report chunk: {e}")


async def dailyreport_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Manual trigger, admin-only — mainly for testing the report on demand
    # instead of waiting for the scheduled time.
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    await send_daily_report(context.bot, chat_id=update.effective_chat.id)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Admin-only: sends a message to every registered user (users/{user_id}
    # in Firebase). Usage: /broadcast <message text>
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    # Use the raw message text (not context.args) so multi-line messages
    # keep their line breaks — context.args whitespace-splits on newlines
    # too and " ".join() would collapse everything onto one line.
    raw_text = update.message.text or ""
    message_text = raw_text[len("/broadcast"):].strip()
    if not message_text:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    users_snapshot = db.reference("users").get() or {}
    if not users_snapshot:
        await update.message.reply_text("No registered users found.")
        return

    sent, failed = 0, 0
    for user_id in users_snapshot.keys():
        try:
            await context.bot.send_message(chat_id=int(user_id), text=message_text)
            sent += 1
        except Exception as e:
            failed += 1
            log.warning(f"Broadcast failed for {user_id}: {e}")
        await asyncio.sleep(0.05)  # avoid hitting Telegram rate limits

    await update.message.reply_text(f"✅ Sent: {sent}  ✗ Failed: {failed}")


def _daily_report_scheduler(loop):
    """Runs in a background thread; sleeps until the next REPORT_HOUR_UTC and
    sends the report, forever, once a day."""
    while True:
        now_utc = datetime.utcnow()
        target = now_utc.replace(hour=REPORT_HOUR_UTC, minute=0, second=0, microsecond=0)
        if target <= now_utc:
            target += timedelta(days=1)
        sleep_seconds = (target - now_utc).total_seconds()
        time.sleep(sleep_seconds)
        try:
            asyncio.run_coroutine_threadsafe(send_daily_report(app.bot), loop)
        except Exception as e:
            log.error(f"Daily report scheduler failed to send report: {e}")
        # small buffer so we don't immediately re-trigger if the send was slow
        time.sleep(5)


# ============================================================
# Server-side Bingo Round Caller
# ------------------------------------------------------------
# Previously, number-calling was driven entirely by whichever player's
# phone/browser got elected "caller" in index.html. If that player
# locked their screen or backgrounded Telegram, mobile browsers
# throttle background timers and calling would stall for up to ~20s
# until another player's device took over. This background thread
# replaces that with a single, always-on server-side caller so calling
# never depends on any individual player's device.
#
# index.html's own acquireRoundCaller()/attemptCallNextNumber() have
# been disabled to match -- only this loop now writes to
# room/calledNumbers and room/prizePool. Winner detection and payout
# stay exactly as they were, client-side.
# ============================================================
ROUND_CARD_SELECTION_SECONDS = 45  # must match CARD_SELECTION_SECONDS in index.html
ROUND_CALL_INTERVAL_SECONDS = 3    # must match the 3000ms cadence in index.html

# Play 10 and Play 20 are separate games -- separate round, card selection,
# caller and prize pool -- each living under its own "room_<stake>" path
# (see roomRef() in index.html). Must match the stakes chooseStake() offers.
GAME_STAKES = [10, 20]


def _compute_and_publish_prize_pool(room_ref, stake):
    """Reads room/takenCards, computes 80% of (number of taken cards × the
    room's own fixed stake), writes room/prizePool if it hasn't already
    been set for this round. Uses the room's own known stake -- not the
    "stake" field stored on each card, which is written by the same
    client-side code a tampered browser could also tamper with -- so a
    manipulated takenCards entry can no longer inflate the announced
    pool."""
    taken = room_ref.child("takenCards").get() or {}
    pool = len(taken) * stake * 0.8

    def txn(current):
        if current and current > 0:
            return current
        return pool

    room_ref.child("prizePool").transaction(txn)


def _deduct_stake_for_card(user_id, amount, deduction_round_key):
    """Mirrors index.html's proceedWithDeduction() wallet transaction
    exactly (play-wallet drawn down first, main covers the remainder,
    deposited-fraction bookkeeping preserved) using the same
    lastStakeDeductionRound idempotency key on users/{uid}/wallet that the
    client already writes. Whichever side -- this server-side safety net
    or the player's own browser -- reaches Firebase first for a given
    round wins that transaction; the other sees the key already set and
    leaves the wallet untouched, so a card can never be paid for twice.
    This exists to catch the case where a player's browser skipped or was
    tampered to skip its own deduction -- not to replace it."""
    wallet_ref = _wallet_ref(user_id)
    outcome = {"paid": False, "insufficient": False}

    def txn(current):
        current = dict(current) if current else {"main": 0, "play": 0, "deposited": 0}
        if current.get("lastStakeDeductionRound") == deduction_round_key:
            outcome["paid"] = True
            return current
        play = current.get("play", 0) or 0
        main = current.get("main", 0) or 0
        deposited = current.get("deposited", 0) or 0
        if (play + main) < amount:
            outcome["insufficient"] = True
            return current  # abort -- leave the wallet untouched
        before_play = play
        from_play = min(play, amount)
        from_main = amount - from_play
        play -= from_play
        main -= from_main
        real_fraction = min(1, deposited / before_play) if before_play > 0 else 0
        deposited = max(0, deposited - (from_play * real_fraction))
        current["play"] = play
        current["main"] = main
        current["deposited"] = deposited
        current["lastStakeDeductionRound"] = deduction_round_key
        outcome["paid"] = True
        return current

    try:
        wallet_ref.transaction(txn)
    except Exception as e:
        log.error(f"Server-side stake deduction failed for {user_id}: {e}")
    return outcome


def _deduct_stakes_for_round(room_ref, stake, round_id):
    """Server-side safety net for stake collection: runs once per round,
    right as calling begins, and charges every taken card's owner the
    room's fixed stake per card they hold -- independently of whether
    their own browser already did (or was tampered to skip) its own
    deduction. Shares the exact lastStakeDeductionRound idempotency key
    with the client's proceedWithDeduction(), so a player who was already
    correctly charged client-side (the normal case) is never charged
    again here; this only catches the case where that never happened."""
    taken = room_ref.child("takenCards").get() or {}
    deduction_round_key = f"{stake}_{round_id}"

    cards_per_user = {}
    for card in taken.values():
        user_id = (card or {}).get("by")
        if user_id:
            cards_per_user[user_id] = cards_per_user.get(user_id, 0) + 1

    for user_id, card_count in cards_per_user.items():
        outcome = _deduct_stake_for_card(user_id, card_count * stake, deduction_round_key)
        if outcome["insufficient"]:
            log.warning(
                f"Player {user_id} held {card_count} card(s) in room_{stake} "
                f"round {round_id} without enough combined balance -- their "
                f"own client-side deduction may have failed too; flagged, "
                f"not removed from the round."
            )


def _firebase_now_ms(room_ref) -> int:
    """Returns Firebase Realtime Database's own current server time (ms),
    by writing a server-timestamp sentinel to a scratch path and reading
    back what the server stamped it with. Clients compute their round
    countdowns against this same Firebase server clock (via a client-side
    offset probe) -- comparing against it here too, instead of against this
    machine's own system clock, means a few seconds of clock drift between
    this server and Firebase can no longer make calling start early/late or
    make a round look stale/not-stale incorrectly."""
    probe_ref = room_ref.child("_serverTimeProbe")
    probe_ref.set({".sv": "timestamp"})
    return int(probe_ref.get() or int(time.time() * 1000))


def _call_next_number(room_ref):
    """Adds one new unique number (1-75) to room/calledNumbers via a
    Firebase transaction -- same algorithm attemptCallNextNumber() used
    to run client-side."""
    def txn(current):
        current_list = list(current or [])
        if len(current_list) >= 75:
            return current_list
        next_num = random.randint(1, 75)
        attempts = 0
        while next_num in current_list and attempts < 200:
            next_num = random.randint(1, 75)
            attempts += 1
        if next_num in current_list:
            return current_list
        current_list.append(next_num)
        return current_list

    result = room_ref.child("calledNumbers").transaction(txn)
    if result is not None:
        # Written as a server-timestamp sentinel (not this machine's own
        # time.time()) so clients' staleness checks compare against the
        # same Firebase server clock they're already synced to.
        room_ref.child("lastCallAt").set({".sv": "timestamp"})


def _matrix_has_win(matrix, called_set):
    """Same five win patterns as index.html's getWinningPattern(): any full
    row, any full column, either diagonal, or all four corners -- with
    'FREE' always counting as already-marked."""
    def hit(v):
        return v == "FREE" or v in called_set

    for row in matrix:
        if all(hit(v) for v in row):
            return True
    for c in range(5):
        if all(hit(matrix[r][c]) for r in range(5)):
            return True
    if all(hit(matrix[i][i]) for i in range(5)):
        return True
    if all(hit(matrix[i][4 - i]) for i in range(5)):
        return True
    corners = [matrix[0][0], matrix[0][4], matrix[4][0], matrix[4][4]]
    if all(hit(v) for v in corners):
        return True
    return False


def _credit_payout(user_id, prize, payout_key, num_winners):
    """Mirrors index.html's own payout-crediting transaction (line ~1372)
    exactly: credits wallet.main and records bingoPayouts/{payout_key} as
    the idempotency guard. Uses the SAME field and key format the client
    already checks, so whichever side -- this server-side pass or the
    winner's own browser -- reaches Firebase first for this round wins;
    the other sees bingoPayouts[payout_key] already set and leaves the
    wallet untouched, so nobody is ever paid twice."""
    wallet_ref = _wallet_ref(user_id)

    def txn(current):
        current = dict(current) if current else {"main": 0, "play": 0, "deposited": 0}
        payouts = dict(current.get("bingoPayouts") or {})
        if payouts.get(payout_key):
            return current  # already paid -- by this call or the client's own
        current["main"] = (current.get("main", 0) or 0) + prize
        payouts[payout_key] = {"amount": prize, "winners": num_winners, "ts": int(time.time() * 1000)}
        current["bingoPayouts"] = payouts
        return current

    try:
        wallet_ref.transaction(txn)
    except Exception as e:
        log.error(f"Server-side payout failed for {user_id}: {e}")


def _distribute_payout(room_ref, stake, round_id, winners):
    """Splits room/prizePool across winners and credits each one -- same
    equal-split-with-remainder-to-earliest-card-number math as index.html's
    own payout code, so a player sees the exact same amount whichever side
    ends up crediting them first."""
    prize_pool = room_ref.child("prizePool").get() or 0
    payout_key = f"{stake}_{round_id}"
    sorted_winners = sorted(winners.items(), key=lambda kv: int(kv[0]))
    num_winners = len(sorted_winners)
    if num_winners == 0:
        return
    pool_cents = round(prize_pool * 100)
    base_cents = pool_cents // num_winners
    remainder_cents = pool_cents - (base_cents * num_winners)
    for idx, (_card_num_str, winner) in enumerate(sorted_winners):
        user_id = (winner or {}).get("by")
        if not user_id:
            continue
        prize_cents = base_cents + (1 if idx < remainder_cents else 0)
        _credit_payout(user_id, prize_cents / 100.0, payout_key, num_winners)


def _check_and_finalize_winners(room_ref, stake, round_id):
    """Independently checks every taken card against the numbers called so
    far and, if any card has a live win, atomically finalizes the round
    (winnerCards + roundEnded) -- using the exact same room/roundFinalizing
    transaction lock the client's finalizeRoundWinners() uses, so whichever
    side (this server thread or a player's browser) gets there first simply
    wins the race safely; the other's attempt is a harmless no-op. Returns
    True if this call finalized the round."""
    taken = room_ref.child("takenCards").get() or {}
    if not taken:
        return False
    called_set = set(room_ref.child("calledNumbers").get() or [])
    if not called_set:
        return False

    winners = {}
    for card_num_str, card in taken.items():
        matrix = (card or {}).get("matrix")
        if not matrix:
            continue
        try:
            if _matrix_has_win(matrix, called_set):
                winners[card_num_str] = {
                    "by": card.get("by"),
                    "name": card.get("name"),
                }
        except Exception as e:
            log.warning(f"Win check failed for card {card_num_str}: {e}")

    if not winners:
        return False

    lock = room_ref.child("roundFinalizing").transaction(
        lambda current: True if current is not True else current
    )
    if not lock:
        return False  # a client (or this check on a re-run) already won the lock

    room_ref.child("winnerCards").set(winners)
    room_ref.child("roundEnded").set(True)
    _distribute_payout(room_ref, stake, round_id, winners)
    log.info(f"Server-side winner check finalized round with {len(winners)} winner(s).")
    return True


def _finalize_no_winner(room_ref):
    """Called once all 75 numbers have been called and no taken card ever
    matched a winning pattern. Uses the same roundFinalizing lock as
    _check_and_finalize_winners, so if a winner is somehow found in the
    same instant (e.g. a client-side check racing this one) that finalize
    wins and this becomes a harmless no-op. Sets roundEnded with no
    winnerCards, which every connected client's roundEnded listener picks
    up immediately -- instead of each client only discovering the round is
    dead later via its own staleness timeout -- so both the 10-birr and
    20-birr rooms return their players to card selection the same way."""
    lock = room_ref.child("roundFinalizing").transaction(
        lambda current: True if current is not True else current
    )
    if not lock:
        return False  # a winner was already finalized for this round
    room_ref.child("roundEnded").set(True)
    log.info("Round ended with no winner after 75 calls.")
    return True


def _run_one_round(room_ref, round_id, stake):
    """Blocks the calling thread for the lifetime of one round: waits out
    the shared card-selection window, publishes the prize pool and
    collects stakes once, then calls numbers every few seconds until 75
    numbers are out or a winner ends the round."""
    try:
        # Prefer the exact deadline clients are already counting down to
        # (written once, in Firebase server time, by whoever's device
        # started the round) over recomputing it from round_id -- and
        # measure "now" from Firebase's own clock too, so this doesn't
        # depend on this server's system clock matching Firebase's at all.
        deadline_ms = room_ref.child("cardSelectionEndTime").get()
        if not deadline_ms:
            deadline_ms = round_id + ROUND_CARD_SELECTION_SECONDS * 1000
        now_ms = _firebase_now_ms(room_ref)
        remaining_s = (deadline_ms - now_ms) / 1000.0
        if remaining_s > 0:
            time.sleep(remaining_s + 0.5)  # small buffer past the client deadline

        if room_ref.child("roundEnded").get() is True:
            return  # round already wrapped up (e.g. no cards were taken)

        _compute_and_publish_prize_pool(room_ref, stake)
        _deduct_stakes_for_round(room_ref, stake, round_id)

        while True:
            loop_start = time.time()
            if room_ref.child("roundEnded").get() is True:
                return
            called = room_ref.child("calledNumbers").get() or []
            if len(called) >= 75:
                _finalize_no_winner(room_ref)
                return
            _call_next_number(room_ref)
            # Check independently, right after the new number lands, whether
            # any taken card now has a live win -- don't rely solely on a
            # player's own browser to report it.
            if _check_and_finalize_winners(room_ref, stake, round_id):
                return
            # Each Firebase read/transaction above takes real network time
            # (often a few hundred ms, sometimes more under load). Sleeping
            # a full ROUND_CALL_INTERVAL_SECONDS on top of that -- instead of
            # accounting for time already spent -- made the gap between
            # calls slowly grow past 3s over the course of a round. Sleeping
            # only for what's left of the interval keeps calls landing on a
            # steady ~3s cadence regardless of network latency.
            elapsed = time.time() - loop_start
            time.sleep(max(0.0, ROUND_CALL_INTERVAL_SECONDS - elapsed))
    except Exception as e:
        log.error(f"Round caller failed for round {round_id}: {e}")


def _round_watcher_loop(stake):
    """Runs for the lifetime of the process -- one instance per stake,
    started in on_startup() so Play 10 and Play 20 run as fully
    independent, concurrent games. Polls room_<stake>/roundId and starts a
    new calling cycle whenever a new round begins for that stake."""
    room_ref = db.reference(f"room_{stake}")
    last_handled_round_id = None
    round_calling = False
    while True:
        try:
            if not round_calling:
                round_id = room_ref.child("roundId").get()
                if round_id and round_id != last_handled_round_id:
                    last_handled_round_id = round_id
                    round_calling = True
                    try:
                        _run_one_round(room_ref, round_id, stake)
                    finally:
                        round_calling = False
        except Exception as e:
            log.error(f"Round watcher loop error (stake {stake}): {e}")
        time.sleep(1)


# ============================================================
# Error Handler
# ============================================================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.error("Unhandled exception while processing an update", exc_info=context.error)


# ============================================================
# Main Application
# ============================================================
main_loop = None


async def on_startup(application):
    global main_loop
    main_loop = asyncio.get_running_loop()
    log.info("Event loop captured; admin notifications are now live.")
    threading.Thread(target=_daily_report_scheduler, args=(main_loop,), daemon=True).start()
    log.info(f"Daily report scheduler started (sends at {REPORT_HOUR_UTC}:00 UTC).")

    for stake in GAME_STAKES:
        threading.Thread(target=_round_watcher_loop, args=(stake,), daemon=True).start()
    log.info(f"Bingo round callers started for stakes {GAME_STAKES} (server-side number calling).")


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
    app.add_handler(CommandHandler("dailyreport", dailyreport_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))

    app.add_handler(CallbackQueryHandler(menu_handler, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(deposit_payment_handler, pattern=r"^deppay:"))
    app.add_handler(CallbackQueryHandler(handle_button, pattern=r"^(approve|approveforce|reject):"))

    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    threading.Thread(target=run_web_server, daemon=True).start()

    log.info("Bot starting with improved wallet & withdraw system...")
    app.run_polling()


if __name__ == "__main__":
    main()
