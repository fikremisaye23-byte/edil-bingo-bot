"""
Temerachi Bingo - Admin Bot (Production Version - Fixed)
---------------------------------------------
የተሻሻለ ስሪት ከተሻሻለ የገንዘብ አያያዝ፣ የተሻሻለ ስህተት አያያዝ እና ከindex.html ጋር የተጣጣመ
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
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

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


def _debit_withdrawal(user_id: str, amount: float) -> Tuple[bool, Optional[str]]:
    return _update_wallet(user_id, main_delta=-amount)


def _refund_withdrawal(user_id: str, amount: float) -> Tuple[bool, Optional[str]]:
    return _update_wallet(user_id, main_delta=amount)


# ============================================================
# Rate Limiting
# ============================================================
_deposit_attempt_times = {}
_deposit_attempt_lock = threading.Lock()
DEPOSIT_RATE_LIMIT_MAX = 5
DEPOSIT_RATE_LIMIT_WINDOW = 600
AUTO_APPROVE_MAX_AMOUNT = 2000


def _deposit_rate_limited(user_id: str) -> bool:
    now = time.time()
    with _deposit_attempt_lock:
        recent = [t for t in _deposit_attempt_times.get(user_id, []) if now - t < DEPOSIT_RATE_LIMIT_WINDOW]
        recent.append(now)
        _deposit_attempt_times[user_id] = recent
        return len(recent) > DEPOSIT_RATE_LIMIT_MAX


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
    
    phone_patterns = [
        r'\(?251\d\*+(\d{2,4})\)?',
        r'0?9\d{8}',
        r'2519\d{8}',
    ]
    phone_match = None
    for pattern in phone_patterns:
        match = re.search(pattern, text)
        if match:
            phone_match = match
            break
    
    txn_patterns = [
        r'ቁጥርዎ\s*(\S+)\s*ነ[ዉው]',
        r'የሂሳብ እንቅስቃሴ ቁጥርዎ\s*(\S+)',
        r'Transaction\s*(?:ID|No|Number)[:\s]*([A-Z0-9]+)',
        r'Ref(?:erence)?[:\s]*([A-Z0-9]+)',
        r'([A-Z0-9]{8,14})\s*(?:ነዉ|ነው|is|$)',
    ]
    
    txn_match = None
    for pattern in txn_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            txn_match = match
            break
    
    receipt_match = re.search(r'transactioninfo\.ethiotelecom\.et/receipt/([A-Za-z0-9]+)', text)
    
    if not amounts and not txn_match:
        return None
    
    return {
        "amounts": amounts,
        "phone": phone_match.group(1) if phone_match else "",
        "txn_id": txn_match.group(1) if txn_match else None,
        "receipt_id": receipt_match.group(1) if receipt_match else None,
        "raw_text": text,
    }


def fetch_telebirr_receipt_improved(receipt_no: str) -> Optional[Dict[str, Any]]:
    url = f"https://transactioninfo.ethiotelecom.et/receipt/{receipt_no}"
    
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    
    for ua in user_agents:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                break
        except Exception as e:
            log.warning(f"User-Agent {ua[:30]}... failed: {e}")
            continue
    else:
        log.warning(f"All User-Agents failed for {receipt_no}")
        return None
    
    result = {"amount": None, "all_phones": [], "date_text": None, "status": "unknown"}
    
    amount_patterns = [
        r'([\d,]+(?:\.\d+)?)\s*(?:ETB|Birr|ብር)',
        r'Amount[:\s]*([\d,]+(?:\.\d+)?)',
        r'ብር[:\s]*([\d,]+(?:\.\d+)?)',
        r'([\d,]+(?:\.\d+)?)\s*ETB',
    ]
    
    for pattern in amount_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            try:
                result["amount"] = float(match.group(1).replace(",", ""))
                break
            except ValueError:
                continue
    
    phone_patterns = [
        r'(?:251)?0?9\d{8}',
        r'\+\d{1,3}0?9\d{8}',
    ]
    all_phones = []
    for pattern in phone_patterns:
        phones = re.findall(pattern, html)
        all_phones.extend(phones)
    result["all_phones"] = list(set(all_phones))
    
    date_patterns = [
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{4}[,\s]+\d{1,2}:\d{2}(?::\d{2})?)',
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',
        r'(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2})',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, html)
        if match:
            result["date_text"] = match.group(1)
            break
    
    if "successful" in html.lower() or "completed" in html.lower() or "confirmed" in html.lower():
        result["status"] = "success"
    elif "failed" in html.lower() or "rejected" in html.lower():
        result["status"] = "failed"
    else:
        result["status"] = "unknown"
    
    if result["amount"] is None:
        log.warning(f"Could not extract amount from receipt page for {receipt_no}")
        return None
    
    return result


def fetch_telebirr_receipt_with_retry_improved(
    receipt_no: str, max_wait_seconds: int = 120, poll_interval: int = 5
) -> Optional[Dict[str, Any]]:
    deadline = time.time() + max_wait_seconds
    attempt = 0
    while True:
        attempt += 1
        log.info(f"Fetching receipt {receipt_no} attempt {attempt}")
        receipt = fetch_telebirr_receipt_improved(receipt_no)
        if receipt is not None:
            log.info(f"Receipt {receipt_no} found on attempt {attempt}")
            return receipt
        if time.time() >= deadline:
            log.info(f"Giving up on receipt {receipt_no} after {attempt} attempts")
            return None
        time.sleep(poll_interval)


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
        if main_bal <= 0:
            await reply_target.reply_text(
                "⚠️ Your main wallet is empty, there's nothing to withdraw.\n\n"
                f"💰 Main wallet: {main_bal:.2f} ብር"
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
            amount = record.get("amount", 0)
            user_id = record.get("by")
            name = record.get("name", "Player")
            
            success, err = _credit_deposit_wallet(user_id, amount)
            if not success:
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
                
        else:
            pending_deposits_ref.child(key).update({
                "status": "rejected",
                "rejected_at": datetime.now().isoformat(),
                "rejected_by": "admin"
            })
            
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
            withdrawals_ref.child(key).update({
                "status": "approved",
                "approved_at": datetime.now().isoformat(),
                "approved_by": "admin"
            })
            
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
            
            success, err = _refund_withdrawal(user_id, amount)
            
            withdrawals_ref.child(key).update({
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

    db.reference(f"users/{user_id}").update({
        "name": name,
        "phone": contact.phone_number,
        "registered": True,
        "registered_at": datetime.now().isoformat(),
    })
    await update.message.reply_text(
        f"✅ Registered! Welcome, {name}.",
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
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    f"🪙 New Deposit Request\n"
                    f"Name: {data.get('name', 'Player')}\n"
                    f"Amount: {stated_amount} ብር\n"
                    f"Txn ID: {receipt_no}\n"
                    f"Phone: {data.get('payToPhone', '')}\n\n"
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

    app.add_handler(CallbackQueryHandler(menu_handler, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(deposit_payment_handler, pattern=r"^deppay:"))
    app.add_handler(CallbackQueryHandler(handle_button, pattern=r"^(approve|reject):"))

    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    threading.Thread(target=run_web_server, daemon=True).start()

    log.info("Bot starting with improved wallet & withdraw system...")
    app.run_polling()


if __name__ == "__main__":
    main()
