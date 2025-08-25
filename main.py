# main.py
import os
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import asyncio
from flask import Flask
import threading
import random
from datetime import datetime

# 環境変数読み込み
load_dotenv()
TOKEN = os.getenv("TOKEN")

# ===== Flask サーバー =====
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))  # Render用PORT
    app.run(host="0.0.0.0", port=port)

# ===== Discord Bot =====
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ===== イベント =====
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# ===== ユーティリティ系 =====
@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member}", description=f"ユーザー情報", color=0x00ff00)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="作成日", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    embed.set_thumbnail(url=member.avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"{guild.name}", description="サーバー情報", color=0x0000ff)
    embed.add_field(name="ID", value=guild.id)
    embed.add_field(name="メンバー数", value=guild.member_count)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    await ctx.send(embed=embed)

# ===== 遊び系 =====
@bot.command()
async def roll(ctx, dice: str):
    try:
        rolls, limit = map(int, dice.lower().split('d'))
    except Exception:
        await ctx.send("形式が違います。例: `!roll 2d6`")
        return
    results = [random.randint(1, limit) for _ in range(rolls)]
    await ctx.send(f"{ctx.author.mention} rolled {dice}: {results} → 合計: {sum(results)}")

# ===== リマインダー =====
@bot.command()
async def remind(ctx, time: str, *, message):
    amount = int(time[:-1])
    unit = time[-1]
    seconds = amount * 60 if unit == "m" else amount * 3600 if unit=="h" else amount
    await ctx.send(f"{ctx.author.mention} リマインダーセット: {message} (あと {time})")
    await asyncio.sleep(seconds)
    await ctx.send(f"{ctx.author.mention} リマインダー: {message}")

# ===== 管理系（自分用） =====
@bot.command()
@commands.is_owner()
async def clear(ctx, amount: int = 5):
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"{len(deleted)} 件削除しました。", delete_after=5)

# ===== メイン =====
if __name__ == "__main__":
    # Flaskを別スレッドで起動
    threading.Thread(target=run_flask).start()
    # Botを非同期で起動
    bot.run(TOKEN)
