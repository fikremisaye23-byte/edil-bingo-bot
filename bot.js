// Edil Bingo — Telegram Bot Backend
// This is the SEPARATE program that makes your bot actually respond.
// It does NOT contain the game itself — the game lives in your Mini App
// (index_modified.html), hosted somewhere with a public HTTPS URL.
// This bot's only real job is: reply to commands, and hand the user a
// button that opens that Mini App.

const TelegramBot = require('node-telegram-bot-api');

// --- Required settings (set these as Environment Variables on your host) ---
const BOT_TOKEN = process.env.BOT_TOKEN;       // from @BotFather
const WEBAPP_URL = process.env.WEBAPP_URL;     // the public HTTPS URL of index_modified.html

if (!BOT_TOKEN) {
    console.error('❌ Missing BOT_TOKEN environment variable. Get it from @BotFather.');
    process.exit(1);
}
if (!WEBAPP_URL) {
    console.error('❌ Missing WEBAPP_URL environment variable. This must be the public https:// link to your hosted index_modified.html.');
    process.exit(1);
}

const bot = new TelegramBot(BOT_TOKEN, { polling: true });

console.log('🤖 Edil Bingo bot is starting...');

bot.on('polling_error', (err) => {
    console.log('Polling error:', err.message);
});

// One shared "open the app" button, reused by every command below.
function openAppKeyboard() {
    return {
        reply_markup: {
            inline_keyboard: [
                [{ text: '🎮 Play Edil Bingo', web_app: { url: WEBAPP_URL } }]
            ]
        }
    };
}

bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;
    bot.sendMessage(
        chatId,
        `👋 Welcome to *Edil Bingo*!\n\nTap the button below to open the game — play, deposit, check your wallet, and withdraw all happen inside the app.`,
        { parse_mode: 'Markdown', ...openAppKeyboard() }
    );
});

// Play, Deposit, Balance, Withdraw, Register, Invite all now live INSIDE
// the Mini App itself (that's what we built together) — so every one of
// these commands just re-opens the same app. This keeps everything in one
// place instead of splitting logic between chat commands and the app.
const menuCommands = ['/play', '/register', '/deposit', '/balance', '/withdraw', '/invite'];
menuCommands.forEach((cmd) => {
    bot.onText(new RegExp('^' + cmd.replace('/', '\\/') + '$'), (msg) => {
        const chatId = msg.chat.id;
        bot.sendMessage(
            chatId,
            `👇 Tap below to open Edil Bingo — everything (play, deposit, wallet, withdraw) is inside the app now.`,
            openAppKeyboard()
        );
    });
});

// Fallback for any other text
bot.on('message', (msg) => {
    if (msg.text && msg.text.startsWith('/')) return; // already handled above
    const chatId = msg.chat.id;
    bot.sendMessage(chatId, `👇 Tap below to open Edil Bingo:`, openAppKeyboard());
});

console.log('✅ Bot is running and polling Telegram for messages.');
