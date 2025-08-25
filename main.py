# main.py
import os
import discord
from discord.ext import commands, tasks
import asyncio
from dotenv import load_dotenv
from flask import Flask
import threading

# 環境変数読み込み
load_dotenv()
TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", 10000))  # RenderのPORT環境変数

# ===== Discord Bot 設定 =====
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== イベント =====
@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")

# ===== ユーティリティコマンド =====
@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member}", description="ユーザー情報", color=0x00ff00)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="作成日", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    embed.set_thumbnail(url=member.avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def roll(ctx, dice: str):
    """例: !roll 2d6"""
    try:
        rolls, limit = map(int, dice.lower().split('d'))
    except Exception:
        await ctx.send("形式が違います。例: `!roll 2d6`")
        return
    results = [discord.utils.randint(1, limit) for _ in range(rolls)]
    await ctx.send(f"{ctx.author.mention} rolled {dice}: {results} → 合計: {sum(results)}")

# ===== Flask ヘルスチェック =====
app = Flask("Utool HealthCheck")

@app.route("/")
def home():
    return "Bot is running!", 200

def run_flask():
    # RenderのPORTでバインド
    app.run(host="0.0.0.0", port=PORT)

# ===== メイン処理 =====
if __name__ == "__main__":
    # Flaskをスレッドで軽く立ち上げる
    threading.Thread(target=run_flask).start()
    # Discord Botを非同期で起動
    bot.run(TOKEN)
