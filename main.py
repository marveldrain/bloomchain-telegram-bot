import asyncio
import logging
import sqlite3
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================== CONFIG ==================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"          # ← Get from @BotFather
ADMIN_ID = 123456789                        # ← Your Telegram user ID
REWARD_AMOUNT = 0.001                       # Base reward in SOL (change as needed)
REFERRAL_BONUS = 0.0005                     # Bonus for referrer when someone joins
PLATFORM_FEE = 0.20                         # 20% you keep (platform fee)
BOOST_PRICE = 0.02                          # Price for 48h 3x boost

# ================== DATABASE ==================
conn = sqlite3.connect("bloomchain.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance REAL DEFAULT 0,
    referrer_id INTEGER,
    referral_code TEXT UNIQUE,
    last_mine TIMESTAMP,
    boost_until TIMESTAMP
)
""")
conn.commit()

# ================== BOT SETUP ==================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_referral_link(user_id: int) -> str:
    return f"https://t.me/{(await bot.get_me()).username}?start={user_id}"

async def get_user(user_id: int):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

async def create_user(user_id: int, username: str, referrer_id: int = None):
    referral_code = f"bloom{user_id}"
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, username, referrer_id, referral_code, balance, last_mine)
        VALUES (?, ?, ?, ?, 0, ?)
    """, (user_id, username, referrer_id, referral_code, datetime.now() - timedelta(days=1)))
    conn.commit()

# ================== COMMANDS ==================

@dp.message(Command("start"))
async def start(message: types.Message):
    args = message.text.split()
    referrer_id = int(args[1]) if len(args) > 1 else None
    
    user = await get_user(message.from_user.id)
    
    if not user:
        await create_user(message.from_user.id, message.from_user.username or "User", referrer_id)
        user = await get_user(message.from_user.id)
        
        # Give starter reward
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", 
                      (0.0005, message.from_user.id))
        conn.commit()
        
        if referrer_id and referrer_id != message.from_user.id:
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", 
                          (REFERRAL_BONUS, referrer_id))
            conn.commit()
            
            try:
                await bot.send_message(referrer_id, 
                    f"🎉 New bloom! Someone joined through your link.\n"
                    f"You earned {REFERRAL_BONUS} SOL!")
            except:
                pass
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🌱 Mine Now", callback_data="mine")
    keyboard.button(text="🔗 My Link", callback_data="link")
    keyboard.button(text="💰 Balance", callback_data="balance")
    keyboard.button(text="🚀 Buy Boost (0.02 SOL)", callback_data="boost")
    keyboard.adjust(2)
    
    await message.answer(
        "🌸 **Welcome to BloomChain!**\n\n"
        "Plant your link → Watch your crypto forest grow.\n"
        "Every person who joins through you = real SOL in your wallet.\n\n"
        "Start mining and share your link to grow faster!",
        reply_markup=keyboard.as_markup()
    )

@dp.callback_query(F.data == "mine")
async def mine(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await callback.answer("Please /start first")
        return
    
    last_mine = datetime.fromisoformat(user[6]) if user[6] else datetime.now() - timedelta(days=1)
    
    if datetime.now() - last_mine < timedelta(hours=12):
        await callback.answer("⏳ You can mine again in 12 hours!", show_alert=True)
        return
    
    boost_until = user[7]
    multiplier = 3 if boost_until and datetime.now() < datetime.fromisoformat(boost_until) else 1
    
    reward = REWARD_AMOUNT * multiplier
    
    cursor.execute("""
        UPDATE users 
        SET balance = balance + ?, last_mine = ? 
        WHERE user_id = ?
    """, (reward, datetime.now(), user_id))
    conn.commit()
    
    await callback.message.edit_text(
        f"🌱 **Mining successful!**\n\n"
        f"You earned **{reward:.6f} SOL** {'(3x Boost Active!)' if multiplier == 3 else ''}\n\n"
        f"💰 New Balance: {user[3] + reward:.6f} SOL\n\n"
        f"Share your link to earn even more!"
    )
    
    await callback.answer()

@dp.callback_query(F.data == "link")
async def get_link(callback: types.CallbackQuery):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={callback.from_user.id}"
    
    await callback.message.answer(
        f"🔗 **Your Personal Bloom Link:**\n\n"
        f"`{link}`\n\n"
        f"Share this everywhere! Every person who joins through you gives you **{REFERRAL_BONUS} SOL** + ongoing rewards."
    )
    await callback.answer()

@dp.callback_query(F.data == "balance")
async def balance(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Start the bot first!")
        return
    
    await callback.message.answer(
        f"💰 **Your BloomChain Balance**\n\n"
        f"**{user[3]:.6f} SOL**\n\n"
        f"🌳 Referral Tree: Growing strong!\n"
        f"Keep sharing to make it bloom bigger."
    )
    await callback.answer()

@dp.callback_query(F.data == "boost")
async def boost(callback: types.CallbackQuery):
    await callback.message.answer(
        "🚀 **Bloom Booster**\n\n"
        "Pay **0.02 SOL** to get **3x rewards** for 48 hours.\n\n"
        "Send 0.02 SOL to this address:\n"
        "`YOUR_SOLANA_WALLET_ADDRESS_HERE`\n\n"
        "After sending, reply with your transaction hash and I'll activate your boost instantly."
    )
    await callback.answer()

# ================== ADMIN COMMANDS ==================
@dp.message(Command("admin_balance"))
async def admin_balance(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    cursor.execute("SELECT SUM(balance) FROM users")
    total = cursor.fetchone()[0] or 0
    await message.answer(f"📊 Total user balances: {total:.6f} SOL")

# ================== RUN BOT ==================
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())