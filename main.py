import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import nest_asyncio
from flask import Flask
import threading
import requests
import time

# -----------------------------
# 環境変数ロード
# -----------------------------
nest_asyncio.apply()
load_dotenv()
TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", 10000))
SELF_URL = os.getenv("SELF_URL")

# -----------------------------
# Bot 初期化
# -----------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------
# Flaskサーバー（ヘルスチェック）
# -----------------------------
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

# -----------------------------
# Cogロード
# -----------------------------
async def load_cogs():
    await bot.load_extension("commands.calendar")
    await bot.load_extension("commands.utility")
    await bot.load_extension("commands.fun")

# -----------------------------
# Bot ready
# -----------------------------
@bot.event
async def on_ready():
    await load_cogs()
    await bot.tree.sync()
    activity = discord.CustomActivity(name="いたずら中😈")
    await bot.change_presence(activity=activity)
    print(f"Logged in as {bot.user} (slash commands synced)")

# -----------------------------
# Bot起動
# -----------------------------
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    bot.run(TOKEN)
