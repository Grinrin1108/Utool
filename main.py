# main.py
import os
from threading import Thread
from flask import Flask
from discord.ext import commands
import discord

# ====== Flask Webサーバー ======
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ====== Discord Bot ======
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# --- コマンド例 ---
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

@bot.command()
async def hello(ctx):
    await ctx.send("Hello!")

def run_discord():
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN is None:
        raise ValueError("環境変数 DISCORD_TOKEN が設定されていません")
    bot.run(TOKEN)

# ====== 並列実行 ======
if __name__ == "__main__":
    # Flaskを別スレッドで実行
    Thread(target=run_flask).start()
    # Discord Botをメインスレッドで実行
    run_discord()
