# main.py
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import nest_asyncio
from flask import Flask
import threading
import requests
import time
import json

# --------------------------------
# Bot初期化
# --------------------------------
nest_asyncio.apply()
load_dotenv()
TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", 10000))
SELF_URL = os.getenv("SELF_URL")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --------------------------------
# Flask (keep alive 用)
# --------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return "Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

def keep_alive():
    while True:
        try:
            if SELF_URL:
                requests.get(SELF_URL)
        except:
            pass
        time.sleep(300)

# --------------------------------
# JSON永続化
# --------------------------------
CAL_FILE = "calendars.json"
if os.path.exists(CAL_FILE):
    with open(CAL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
else:
    data = {}

def save_data():
    with open(CAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_guild_data(guild_id):
    guild_id = str(guild_id)
    if guild_id not in data:
        data[guild_id] = {"events": [], "todos": []}
    return data[guild_id]

# --------------------------------
# コマンドのインポート
# --------------------------------
from commands import utility, fun, calendar

# --------------------------------
# Bot ready
# --------------------------------
@bot.event
async def on_ready():
    # コマンド登録
    utility.register_utility_commands(bot)
    fun.register_fun_commands(bot)
    calendar.register_calendar_commands(bot, get_guild_data, save_data)

    await bot.tree.sync()
    activity = discord.CustomActivity(name="いたずら中😈")
    await bot.change_presence(activity=activity)
    print(f"Logged in as {bot.user} (slash commands synced)")

# --------------------------------
# Bot起動
# --------------------------------
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    bot.run(TOKEN)
