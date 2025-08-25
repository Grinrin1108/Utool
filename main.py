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

# ====== イベント定義 ======
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# ====== コマンド定義 ======
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

@bot.command()
async def hello(ctx):
    await ctx.send("Hello!")

@bot.command()
async def add(ctx, a: int, b: int):
    res = a + b
    await ctx.send(f"{a}+{b}={res}")

bot.run(TOKEN)

