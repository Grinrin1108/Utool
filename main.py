# main.py (Render対応・Flask組み込み・機能モリモリ版)
import os
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import asyncio
import nest_asyncio
import random
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

# ===== Render対応のFlask設定 =====
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_flask).start()

# ===== Discord Bot設定 =====
nest_asyncio.apply()  # Renderで非同期対応

load_dotenv()
TOKEN = os.getenv("TOKEN")  # Render Environment Secretに設定済みを想定

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ===== イベント =====
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# ===== ユーティリティ系コマンド =====
@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member}", description="ユーザー情報", color=0x00ff00)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="作成日", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    embed.set_thumbnail(url=member.avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=guild.name, description="サーバー情報", color=0x0000ff)
    embed.add_field(name="ID", value=guild.id)
    embed.add_field(name="メンバー数", value=guild.member_count)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    await ctx.send(embed=embed)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member}'s Avatar")
    embed.set_image(url=member.avatar.url)
    await ctx.send(embed=embed)

# ===== 遊び・便利系コマンド =====
@bot.command()
async def roll(ctx, dice: str):
    """例: !roll 2d6"""
    try:
        rolls, limit = map(int, dice.lower().split('d'))
    except Exception:
        await ctx.send("形式が違います。例: `!roll 2d6`")
        return
    results = [random.randint(1, limit) for _ in range(rolls)]
    await ctx.send(f"{ctx.author.mention} rolled {dice}: {results} → 合計: {sum(results)}")

@bot.command()
async def poll(ctx, question: str, *options):
    if len(options) < 2:
        await ctx.send("選択肢は2つ以上必要です。")
        return
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    description = "\n".join(f"{emojis[i]} {opt}" for i,opt in enumerate(options))
    embed = discord.Embed(title=question, description=description, color=0xffa500)
    msg = await ctx.send(embed=embed)
    for i in range(len(options)):
        await msg.add_reaction(emojis[i])

@bot.command()
async def remind(ctx, time: str, *, message):
    """例: !remind 10m メッセージ"""
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

# ===== Bot起動 =====
bot.run(TOKEN)
