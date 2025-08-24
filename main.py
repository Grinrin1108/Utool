import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

# ====== 環境変数読み込み ======
load_dotenv()
TOKEN = os.getenv("TOKEN")  # ここに控えたトークンを貼る

intents = discord.Intents.default()
intents.message_content = True  # メッセージ読み取り用

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

bot.run(TOKEN)

