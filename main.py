import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import nest_asyncio
from flask import Flask
import threading
import requests
import time

from utils.data_manager import DataManager
from commands import utility, fun, calendar, reminder, todo

# --------------------------------
# 初期化
# --------------------------------
nest_asyncio.apply()
load_dotenv()
TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", 10000))
SELF_URL = os.getenv("SELF_URL")
DATA_CHANNEL_ID = int(os.getenv("DATA_CHANNEL_ID", 0))

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
# DataManager
# --------------------------------
data_manager = DataManager(bot, DATA_CHANNEL_ID)

# --------------------------------
# Bot ready
# --------------------------------
@bot.event
async def on_ready():
    # データをロード
    await data_manager.load_files()

    # コマンド登録
    utility.register_utility_commands(bot)
    fun.register_fun_commands(bot)
    calendar.register_calendar_commands(bot, data_manager)
    reminder.register_reminder_commands(bot, data_manager)
    todo.register_todo_commands(bot, data_manager)

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
