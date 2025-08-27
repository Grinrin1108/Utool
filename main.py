# main.py
import os
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import asyncio
import nest_asyncio
import random
from datetime import datetime
from flask import Flask
import threading
import requests
import time

# Render用非同期調整
nest_asyncio.apply()
load_dotenv()
TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", 10000))
SELF_URL = os.getenv("SELF_URL")  # Render URL, Ping用

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== Flaskヘルスチェック =====
app = Flask(__name__)

@app.route("/")
def health():
    return "Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ===== 自動Pingでスリープ復帰 =====
def keep_alive():
    while True:
        try:
            if SELF_URL:
                requests.get(SELF_URL)
        except:
            pass
        time.sleep(300)  # 5分おき

# ===== Botイベント =====
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def on_error(event_method, *args, **kwargs):
    import traceback
    print(f"Error in {event_method}: {traceback.format_exc()}")

# ===== ユーティリティコマンド =====
# ユーザー情報
@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member}", description=f"ユーザー情報", color=0x00ff00)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="作成日", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    embed.set_thumbnail(url=member.avatar.url)
    await ctx.send(embed=embed)
    print(f"userinfo command used by {ctx.author} for {member}")

# サーバー情報
@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"{guild.name}", description="サーバー情報", color=0x0000ff)
    embed.add_field(name="ID", value=guild.id)
    embed.add_field(name="メンバー数", value=guild.member_count)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    await ctx.send(embed=embed)
    print(f"serverinfo command used by {ctx.author}")

# アバター表示
@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member}'s Avatar")
    embed.set_image(url=member.avatar.url)
    await ctx.send(embed=embed)
    print(f"avatar command used by {ctx.author} for {member}")

# ===== 遊び系コマンド =====
# さいころ
@bot.command()
async def roll(ctx, dice: str):
    try:
        rolls, limit = map(int, dice.lower().split('d'))
    except Exception:
        await ctx.send("形式が違います。例: `!roll 2d6`")
        return
    results = [random.randint(1, limit) for _ in range(rolls)]
    await ctx.send(f"{ctx.author.mention} rolled {dice}: {results} → 合計: {sum(results)}")
    print(f"roll command used by {ctx.author}")

# 投票作成
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
    print(f"poll command used by {ctx.author}")

# リマインダー
@bot.command()
async def remind(ctx, time: str, *, message):
    amount = int(time[:-1])
    unit = time[-1]
    seconds = amount * 60 if unit == "m" else amount * 3600 if unit=="h" else amount
    await ctx.send(f"{ctx.author.mention} リマインダーセット: {message} (あと {time})")
    print(f"remind command used by {ctx.author}")
    await asyncio.sleep(seconds)
    await ctx.send(f"{ctx.author.mention} リマインダー: {message}")
    print(f"reminder sent to {ctx.author}")

# ===== 管理系 =====
@bot.command()
@commands.is_owner()
async def clear(ctx, amount: int = 5):
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"{len(deleted)} 件削除しました。", delete_after=5)
    print(f"clear command used by {ctx.author}")

# ===== 非同期でFlask & Bot同時起動 =====
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    bot.run(TOKEN)
