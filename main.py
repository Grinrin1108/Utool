import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import nest_asyncio
from flask import Flask
import threading
import requests
import time
import sys

# ユーティリティ
from utils.data_manager import DataManager
from commands import help, utility, fun, reminder

load_dotenv()
nest_asyncio.apply()

TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", 10000))
SELF_URL = os.getenv("SELF_URL")
DATA_CHANNEL_ID = int(os.getenv("DATA_CHANNEL_ID", "0"))

if not TOKEN or DATA_CHANNEL_ID == 0:
    print("❌ ERROR: TOKEN または DATA_CHANNEL_ID が設定されていません。")
    sys.exit(1)

# Discord Bot 設定
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Flask (Koyeb/Render スリープ防止用)
app = Flask(__name__)
@app.route('/')
def health(): return "Bot is running!", 200

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

def keep_alive():
    if not SELF_URL: return
    time.sleep(20)
    while True:
        try: requests.get(SELF_URL, timeout=10)
        except: pass
        time.sleep(300)

data_manager = DataManager(bot, DATA_CHANNEL_ID)
bot.initialized = False

@bot.event
async def on_ready():
    if not bot.initialized:
        print(f"🚀 {bot.user} としてログインしました。モジュールを初期化します...")
        await data_manager.load_files()
        
        # コマンド登録 (Todoは削除)
        utility.register_utility_commands(bot)
        fun.register_fun_commands(bot)
        reminder.register_reminder_commands(bot, data_manager)
        help.register_help_command(bot)

        await bot.tree.sync()
        bot.initialized = True
        print(f"✅ すべてのコマンドを同期しました！")

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    bot.run(TOKEN)