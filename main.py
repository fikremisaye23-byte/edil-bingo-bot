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

import firebase_admin
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

# ---- Firebase setup ----
service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})

deposits_ref = db.reference("transactions/deposits")
withdrawals_ref = db.reference("transactions/withdrawals")
# Keeps track of Telebirr transaction IDs that have already been used for a
# deposit, so the same confirmation SMS can't be submitted twice.
used_deposit_ids_ref = db.reference("transactions/usedDepositIds")

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
    # Keep the parser tolerant of harmless SMS formatting differences while
    # still requiring the characteristic Telebirr transaction/reference ID.
    if not text or not isinstance(text, str):
        return None

    norm = " ".join(text.split())

    amount_match = re.search(r"([\d,]+(?:\.\d+)?)\s*ብር", norm)
    phone_match = re.search(r"\(?251\d\*+(\d{4})\)?", norm)
    txn_match = re.search(r"(?:ቁጥርዎ?|የሂሳብ እንቅስቃሴ ቁጥር|Ref(?:erence)?|Txn(?:ID)?)\s*[:\-]?\s*([A-Z0-9]{8,20})", norm, re.IGNORECASE)

    if not (amount_match and txn_match):
        return None

    try:
        amount = float(amount_match.group(1).replace(",", ""))
    except ValueError:
        return None

    return {
        "amount": amount,
        "phone_last4": phone_match.group(1) if phone_match else None,
        "txn_id": txn_match.group(1).upper(),
    }


def _verify_telebirr_receipt(txn_id, expected_amount, expected_phone):
    """Verify the public Telebirr receipt for the current Deposit only.

    The receipt is read from the official public receipt URL and the labelled
    receipt fields are checked: receipt/reference number, settled amount,
    successful transaction status, and credited-party Telebirr number.
    """
    import html as _html
    from urllib.request import Request, urlopen

    txn_id = str(txn_id or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{8,20}", txn_id, re.IGNORECASE):
        return False

    url = f"https://transactioninfo.ethiotelecom.et/receipt/{txn_id}"
    try:
        request = Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            method="GET",
        )
        with urlopen(request, timeout=15) as response:
            if getattr(response, "status", 200) != 200:
                return False
            raw_html = response.read().decode("utf-8", "ignore")
    except Exception as e:
        log.warning("Telebirr receipt verification failed for %s: %s", txn_id, e)
        return False

    # Telebirr receipts are table-based. Read the value following each known
    # label instead of depending on one exact HTML layout/spacing.
    td_values = re.findall(r"<td\b[^>]*>(.*?)</td>", raw_html, flags=re.IGNORECASE | re.DOTALL)
    values = []
    for item in td_values:
        item = re.sub(r"<br\s*/?>", " ", item, flags=re.IGNORECASE)
        item = re.sub(r"<[^>]+>", " ", item)
        item = _html.unescape(item)
        item = " ".join(item.split()).strip()
        values.append(item)

    compact_values = [re.sub(r"\s+", "", v).lower() for v in values]

    def value_after(labels):
        labels = {re.sub(r"\s+", "", x).lower() for x in labels}
        for i, value in enumerate(compact_values):
            if value in labels and i + 1 < len(values):
                return values[i + 1].strip()
        return None

    receipt_no = value_after([
        "የክፍያቁጥር/receiptno.",
        "የክፍያቁጥር/receiptno",
    ])
    settled_amount = value_after([
        "የተከፈለውመጠን/settledamount",
        "settledamount",
    ])
    status = value_after([
        "የክፍያውሁኔታ/transactionstatus",
        "transactionstatus",
    ])
    credited_account = value_after([
        "የገንዘብተቀባይቴሌብርቁ./creditedpartyaccountno",
        "creditedpartyaccountno",
    ])

    # Some receipt layouts place a value one extra table cell away for the
    # amount/status/account fields. If the direct value is absent, use the
    # normalized receipt text as a conservative fallback.
    receipt_text = " ".join(values)
    compact = re.sub(r"\s+", "", receipt_text).lower()

    if receipt_no:
        if re.sub(r"\s+", "", receipt_no).upper() != txn_id:
            return False
    elif txn_id.lower() not in compact:
        return False

    amount_text = settled_amount
    if not amount_text:
        amount_match = re.search(
            r"(?:የተከፈለውመጠን/settledamount|settledamount)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
            compact,
            re.IGNORECASE,
        )
        if not amount_match:
            return False
        amount_text = amount_match.group(1)

    amount_match = re.search(r"[\d,]+(?:\.\d+)?", amount_text)
    if not amount_match:
        return False
    try:
        receipt_amount = float(amount_match.group(0).replace(",", ""))
    except ValueError:
        return False
    if abs(receipt_amount - float(expected_amount)) > 0.000001:
        return False

    status_text = re.sub(r"\s+", "", status or "").lower()
    if not status_text:
        status_text = compact
    if not re.search(
        r"(?:success|successful|completed|successfultransaction|ተሳክቷል|ተጠናቋል)",
        status_text,
        re.IGNORECASE,
    ):
        return False

    expected_last4 = re.sub(r"\D", "", str(expected_phone or ""))[-4:]
    if not expected_last4:
        return False

    account_text = credited_account
    if not account_text:
        account_match = re.search(
            r"(?:የገንዘብተቀባይቴሌብርቁ\./creditedpartyaccountno)"
            r"\s*[:\-]?\s*([0-9*]+)",
            compact,
            re.IGNORECASE,
        )
        if account_match:
            account_text = account_match.group(1)

    if not account_text:
        return False

    account_digits = re.sub(r"\D", "", account_text)
    if account_digits[-4:] != expected_last4:
        return False

    return True


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
    await query.answer()
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


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_menu_action("withdraw", update.message, update.effective_user, context)


# ---- Deposit payment-method button handler (Telebirr / Cancel) ----
async def deposit_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
        f"የሚያጋጥማቹ የክፍያ ችግር:\n@{SUPPORT_USERNAME} ላይ ፃፉልን።\n\n"
        f"1. ከታች ባለው የቴሌብር አካውንት {amount} ብር ያስገቡ\n\n"
        f"Phone:\n{number_obj['phone']}\n\n"
        f"2. የከፈሉበትን አጭር የጹሁፍ መልዕክት(message) copy በማድረግ እዚ ላይ Paste "
        f"አድርገው ያስገቡና ይላኩት\n👇👇👇"
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
        parsed = parse_telebirr_sms(text)
        requested_amount = float(data.get("amount", -1))

        if parsed is None:
            await update.message.reply_text(
                "🚫 የTelebirr SMS መረጃው አልተረጋገጠም። እባክዎ ከTelebirr የመጣውን ትክክለኛ SMS ብቻ ይላኩ።\n\n"
                f"❓ለድጋፍ @{SUPPORT_USERNAME} ላይ ይፃፉልን"
            )
            return

        if abs(parsed["amount"] - requested_amount) > 0.000001:
            await update.message.reply_text(
                f"🚫 የTelebirr SMS መጠን ({parsed['amount']:g} ETB) ከጠየቁት {requested_amount:g} ETB ጋር አይመሳሰልም።"
            )
            return

        txn_id = parsed["txn_id"]
        if used_deposit_ids_ref.child(txn_id).get():
            await update.message.reply_text(
                "❌ ይህ Transaction ID ከዚህ በፊት ጥቅም ላይ ውሏል። ሁለት ጊዜ ሊከፈል አይችልም።"
            )
            return

        # Verify the transaction against the public Telebirr receipt before
        # reserving the ID or changing the user's wallet.
        receipt_ok = await asyncio.to_thread(
            _verify_telebirr_receipt,
            txn_id,
            requested_amount,
            data.get("payToPhone", ""),
        )
        if not receipt_ok:
            await update.message.reply_text(
                "🚫 የTelebirr transaction receipt ማረጋገጥ አልተቻለም።\n"
                "Transaction ID, amount እና የተላከበት የTelebirr ቁጥር እንደሚመሳሰሉ ያረጋግጡ።\n\n"
                f"❓ለድጋፍ @{SUPPORT_USERNAME} ላይ ይፃፉልን"
            )
            return

        # Reserve the transaction ID atomically so the same receipt cannot be
        # credited twice even if two submissions arrive almost simultaneously.
        def claim_transaction(current):
            return True if current is None else current

        claimed = used_deposit_ids_ref.child(txn_id).transaction(claim_transaction)
        if claimed is not True:
            await update.message.reply_text(
                "❌ ይህ Transaction ID ከዚህ በፊት ጥቅም ላይ ውሏል። ሁለት ጊዜ ሊከፈል አይችልም።"
            )
            return

        data["smsText"] = text
        amount = int(requested_amount) if requested_amount.is_integer() else requested_amount

        # Preserve the existing wallet behavior used by the admin approval
        # path: deposits increase Play Wallet and deposited total.
        wallet_ref = _wallet_ref(user_id)

        def credit(current):
            current = current or {"main": 0, "play": 0, "deposited": 0}
            current["play"] = current.get("play", 0) + requested_amount
            current["deposited"] = current.get("deposited", 0) + requested_amount
            return current

        try:
            wallet_ref.transaction(credit)
        except Exception as e:
            used_deposit_ids_ref.child(txn_id).delete()
            log.warning("Wallet credit failed for deposit %s: %s", txn_id, e)
            await update.message.reply_text(
                "🚫 የWallet ክሬዲት አልተሳካም። ገንዘቡ እንዳይደገም ግብይቱ አልተፈቀደም። እባክዎ ድጋፍ ያግኙ።"
            )
            return

        deposits_ref.push({
            "by": user_id,
            "name": data.get("name", "Player"),
            "amount": amount,
            "phone": data.get("payToPhone", ""),
            "smsText": text,
            "paidTo": data.get("payToPhone", ""),
            "txnId": txn_id,
            "receiptUrl": f"https://transactioninfo.ethiotelecom.et/receipt/{txn_id}",
            "status": "approved",
        })

        context.user_data["flow"] = None
        context.user_data["flow_data"] = {}
        await update.message.reply_text(
            f"✅ Your deposit of {amount} ETB is Approved.\n"
            f"🧾 Ref: {txn_id}"
        )

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


# ---- Admin-only test balance (temporary QA tool) ----
# Usage from the ADMIN account only:
#   /testbalance <telegram_user_id> [amount]
# It credits the user's Play Wallet and marks the amount as deposited
# so the real-money stake/payout paths can be tested without a real deposit.
# Remove this handler after multiplayer testing is complete.
async def testbalance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Not authorized.")
        return

    args = context.args or []
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "🧪 Test Balance\n\n"
            "Usage: /testbalance USER_ID [AMOUNT]\n"
            "Example: /testbalance 123456789 1000"
        )
        return

    target_user_id = args[0]
    amount = 1000
    if len(args) >= 2:
        try:
            amount = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ Amount must be a whole number.")
            return

    if amount <= 0:
        await update.message.reply_text("❌ Amount must be greater than 0.")
        return

    wallet_ref = _wallet_ref(target_user_id)

    def credit_test(current):
        current = current or {"main": 0, "play": 0, "deposited": 0}
        current["play"] = float(current.get("play", 0) or 0) + amount
        current["deposited"] = float(current.get("deposited", 0) or 0) + amount
        return current

    wallet = wallet_ref.transaction(credit_test)
    await update.message.reply_text(
        f"🧪 Test balance added\n"
        f"User ID: {target_user_id}\n"
        f"Added to Play Wallet: {amount} ብር\n"
        f"Play Wallet now: {wallet.get('play', 0)} ብር"
    )


# ---- Approve/Reject button handler (admin only) ----
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
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"✅ Deposit Success! {amount} ኮይን ወደ ዋሌትዎ ገብቷል።",
                )
            except Exception as e:
                log.warning(f"Could not notify depositor {user_id} of approval: {e}")
        else:
            deposits_ref.child(key).update({"status": "rejected"})
            await query.edit_message_text(f"❌ Rejected deposit ({record.get('amount')} coins) for {record.get('name')}.")
            try:
                await context.bot.send_message(
                    chat_id=int(record["by"]),
                    text=f"❌ Deposit Reject. የ{record.get('amount')} ኮይን ተቀማጭ ገንዘብ ጥያቄዎ ውድቅ ሆኗል።",
                )
            except Exception as e:
                log.warning(f"Could not notify depositor {record['by']} of rejection: {e}")

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
        f"Paid To: {record.get('paidTo', '-')}\n"
        f"Telebirr Txn ID: {record.get('txnId', '-')}\n"
        f"Request ID: {key}\n\n"
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


def main():
    global app
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("deposit", deposit_command))
    app.add_handler(CommandHandler("withdraw", withdraw_command))
    app.add_handler(CommandHandler("play", play_command))
    app.add_handler(CommandHandler("testbalance", testbalance_command))
    app.add_handler(CallbackQueryHandler(menu_handler, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(deposit_payment_handler, pattern=r"^deppay:"))
    app.add_handler(CallbackQueryHandler(handle_button, pattern=r"^(approve|reject):"))
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Start Firebase realtime listeners (each runs on its own background thread)
    deposits_ref.listen(on_deposit_change)
    withdrawals_ref.listen(on_withdrawal_change)

    # Start the keep-alive web server on a background thread
    threading.Thread(target=run_web_server, daemon=True).start()

    log.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
