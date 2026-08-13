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
    # Normalise whitespace to make regexes simpler
    txt = (text or "").strip()

    # Amount: collect EVERY monetary figure in the message (not just the
    # first), regardless of whether the SMS wording is Amharic ("ብር") or
    # English ("Birr"/"ETB") -- Telebirr sends in whichever language the
    # recipient's SIM/handset is set to, and earlier only matching "ብር"
    # silently broke everything for English-language messages.
    amount_matches = re.findall(r"([\d,]+(?:\.\d+)?)\s*(?:ብር|Birr|ETB)", txt, re.IGNORECASE)

    # Phone (last 4 digits of the masked sender number): informational only.
    # Support formats like (2519****9106), 09****9106, or plain numbers.
    phone_match = re.search(r"(?:251)?0?9\*+?(\d{2,4})", txt)

    # Transaction ID: try several common patterns (Amharic phrasing first,
    # then common English phrases) and finally a generic alphanumeric
    # fallback. Accept lowercase/uppercase and hyphens. Strip punctuation
    # around the captured token to avoid trailing punctuation/errors.
    txn_match = (
        re.search(r"ቁጥርዎ\s*([A-Za-z0-9\-]{4,30})\s*ነ[ዉው]", txt)
        or re.search(
            r"(?:transaction\s*(?:number|id)|txn\s*id|ref(?:erence)?\s*(?:no\.?|number)?)\s*(?:is|:)?\s*([A-Za-z0-9\-]{4,30})",
            txt, re.IGNORECASE,
        )
        or re.search(r"\b([A-Za-z0-9\-]{6,30})\b", txt, re.IGNORECASE)
    )

    if not txn_match:
        return None

    # Sanitize captured values
    raw_txn = txn_match.group(1).strip()
    # strip common trailing punctuation that might get captured
    txn_id = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", raw_txn)

    amounts = []
    for raw in amount_matches:
        try:
            amounts.append(float(raw.replace(",", "")))
        except ValueError:
            continue

    return {
        "amounts": amounts,
        "phone_last4": phone_match.group(1) if phone_match else "",
        "txn_id": txn_id,
    }


def fetch_telebirr_receipt(receipt_no):
    """
    Fetch Ethio Telecom's own official receipt page for a transaction and
    extract the amount + recipient phone from it. This is our automatic
    verification layer. ALWAYS return a dict with debug info on failure.
    """
    url = f"https://transactioninfo.ethiotelecom.et/receipt/{receipt_no}"
    req = urllib.request.Request(
        url,
        headers={
            # Use a realistic browser UA and accept headers so the site
            # is less likely to return a minimal/blocked page.
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = getattr(resp, "status", None) or 200
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        log.warning(f"Receipt fetch failed for {receipt_no}: {e}")
        return {"ok": False, "debug": f"fetch error: {e!r}"}

    # Sometimes the site wraps currency in non-breaking spaces or HTML tags;
    # make the regex tolerant by allowing HTML entities and tags between the
    # number and the currency word.
    amount_match = re.search(r"([\d,]+(?:\.\d+)?)(?:\s|&nbsp;|<[^>]*>){0,6}(?:ETB|Birr|ብር)", html, re.IGNORECASE)
    if not amount_match:
        snippet = re.sub(r"\s+", " ", html).strip()[:1500]
        log.warning(f"Receipt page for {receipt_no} fetched (HTTP {status}) but amount not found")
        return {"ok": False, "debug": f"HTTP {status}, amount not found. Page snippet: {snippet}"}
    try:
        amount = float(amount_match.group(1).replace(",", ""))
    except ValueError:
        return {"ok": False, "debug": f"HTTP {status}, amount text unparseable: {amount_match.group(1)!r}"}

    # Every phone-like number on the page (there may be more than one).
    # Accept formats both with and without country code.
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
    Keep polling Ethio Telecom's receipt page for up to max_wait_seconds.
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

2. የካርድ መምረጫ ቦርድ ላይ በቀይ ቀለም የተመረጡ ቁጥሮች የሚያሳዩት መጫወቻ ካርዱ (ካርቴላው) በሌላ ተጫዋች መመረጡን �[...]

3. የመጫወቻ ካርዱን (ካርቴላውን) ሲመርጡት ከታች የሚይዛቸውን ቁጥሮች ያሳያል።

4. ወደ ጨዋታው ለመግባት የሚፈልጉትን የመጫወቻ ካርድ (ካርቴላ) ሲመርጡና ለምዝገባ የተሰጠው ሰኮንድ ዜሮ ሲሆን ቀጥታ ወ��[...]

🎮 ጨዋታ እንዴት ይካሄዳል

1. ወደ ጨዋታው ከገቡ በኋላ በመረጡት የመጫወቻ ካርድ (ካርቴላ) ከታች በቀኝ በኩል ያገኙታል።

2. ጨዋታው ሲጀምር ሲስተሙ ከ1 እስከ 75 ያሉ ቁጥሮችን Randomly መጥራት ይጀምራል።

3. ሲስተሙ ከሚጠራቸው ቁጥሮች ውስጥ በራስዎ የመጫወቻ ካርድ (ካርቴላ) ላይ ካሉ በመምረጥ ያጥቁሩ። በራሱ እንዲያጠቁር ከፈለ�[...]

🎮 ጨዋታ እንዴት ይካሄዳል

... (truncated for brevity in this message)