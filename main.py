import os  # 小文字に修正
import discord
from discord.ext import commands
from dotenv import load_dotenv
import nest_asyncio
from flask import Flask
import threading
import requests
import time
import sys

# 自身のユーティリティをインポート
from utils.data_manager import DataManager
from commands import utility, fun, reminder, todo

# --- 初期設定 ---
nest_asyncio.apply()
load_dotenv()

TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", 10000))
SELF_URL = os.getenv("SELF_URL")
DATA_CHANNEL_ID_STR = os.getenv("DATA_CHANNEL_ID", "0")

# DATA_CHANNEL_IDが数字でない場合の対策
try:
    DATA_CHANNEL_ID = int(DATA_CHANNEL_ID_STR)
except ValueError:
    DATA_CHANNEL_ID = 0

if not TOKEN:
    print("❌ ERROR: TOKENが見つかりません。環境変数を確認してください。")
    sys.exit(1)

# --- Discord Bot 設定 ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Flask Health Check (Render用) ---
app = Flask(__name__)

@app.route("/")
def health():
    return "Bot is alive!", 200

def run_flask():
    print(f"📡 Flask server starting on port {PORT}...")
    try:
        app.run(host="0.0.0.0", port=PORT)
    except Exception as e:
        print(f"❌ Flask Error: {e}")

def keep_alive():
    """スリープ防止用"""
    if not SELF_URL:
        print("⚠️ SELF_URLが設定されていないため、keep_aliveをスキップします。")
        return
    
    time.sleep(20) # 起動直後は待機
    while True:
        try:
            requests.get(SELF_URL, timeout=10)
            # print("♻️ Keep-alive ping sent.")
        except Exception as e:
            print(f"⚠️ Keep-alive Error: {e}")
        time.sleep(300)

# --- Bot Events ---
data_manager = DataManager(bot, DATA_CHANNEL_ID)
bot.initialized = False

@bot.event
async def on_ready():
    if not bot.initialized:
        print(f"⚙️ Initializing modules for {bot.user}...")
        await data_manager.load_files()
        utility.register_utility_commands(bot)
        fun.register_fun_commands(bot)
        reminder.register_reminder_commands(bot, data_manager)
        todo.register_todo_commands(bot, data_manager)

        await bot.tree.sync()
        bot.initialized = True
        print(f"✅ Logged in as {bot.user} and commands synced!")

# --- 実行 ---
if __name__ == "__main__":
    # Flaskスレッド開始
    t_flask = threading.Thread(target=run_flask, daemon=True)
    t_flask.start()
    
    # Keep-aliveスレッド開始
    t_keep = threading.Thread(target=keep_alive, daemon=True)
    t_keep.start()

    # Discord Bot 実行
    print("🚀 Starting Discord Bot...")
    bot.run(TOKEN)
