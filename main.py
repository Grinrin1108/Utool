import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import asyncio
import nest_asyncio
import random
from datetime import datetime, date
from flask import Flask
import threading
import requests
import time
import json

# Render用非同期調整
nest_asyncio.apply()
load_dotenv()
TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", 10000))
SELF_URL = os.getenv("SELF_URL")

# ===== Discord Bot =====
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
        time.sleep(300)

# ===== JSON永続化カレンダー =====
CAL_FILE = "calendars.json"
if os.path.exists(CAL_FILE):
    with open(CAL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
else:
    data = {}  # {guild_id: {"events": [], "todos": []}}

def save_data():
    with open(CAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_guild_data(guild_id):
    guild_id = str(guild_id)
    if guild_id not in data:
        data[guild_id] = {"events": [], "todos": []}
    return data[guild_id]

# ===== Bot Ready =====
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (slash commands synced)")

# ===== ユーティリティ系 =====
@bot.tree.command(name="userinfo", description="ユーザー情報を表示します")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"{member}", description="ユーザー情報", color=0x00ff00)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="作成日", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="サーバー情報を表示します")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"{guild.name}", description="サーバー情報", color=0x0000ff)
    embed.add_field(name="ID", value=guild.id)
    embed.add_field(name="メンバー数", value=guild.member_count)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="avatar", description="ユーザーのアバターを表示します")
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"{member}'s Avatar")
    embed.set_image(url=member.avatar.url if member.avatar else None)
    await interaction.response.send_message(embed=embed)

# ===== 遊び系 =====
@bot.tree.command(name="roll", description="サイコロを振ります (例: 2d6)")
async def roll(interaction: discord.Interaction, dice: str):
    await interaction.response.defer()
    try:
        rolls, limit = map(int, dice.lower().split('d'))
    except:
        await interaction.followup.send("形式が違います。例: `/roll 2d6`")
        return
    results = [random.randint(1, limit) for _ in range(rolls)]
    await interaction.followup.send(f"{interaction.user.mention} rolled {dice}: {results} → 合計: {sum(results)}")

@bot.tree.command(name="poll", description="投票を作成します")
async def poll(interaction: discord.Interaction, question: str, option1: str, option2: str, option3: str = None, option4: str = None):
    await interaction.response.defer()
    options = [opt for opt in [option1, option2, option3, option4] if opt]
    if len(options) < 2:
        await interaction.followup.send("選択肢は2つ以上必要です。")
        return
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣"]
    description = "\n".join(f"{emojis[i]} {opt}" for i,opt in enumerate(options))
    embed = discord.Embed(title=question, description=description, color=0xffa500)
    msg = await interaction.channel.send(embed=embed)
    for i in range(len(options)):
        await msg.add_reaction(emojis[i])
    await interaction.followup.send("✅ 投票を作成しました", ephemeral=True)

@bot.tree.command(name="remind", description="リマインダーを設定します (例: 10s / 5m / 1h)")
async def remind(interaction: discord.Interaction, time_str: str, message: str):
    await interaction.response.defer()
    try:
        amount = int(time_str[:-1])
        unit = time_str[-1]
        seconds = amount * 60 if unit == "m" else amount * 3600 if unit=="h" else amount
    except:
        await interaction.followup.send("形式が違います。例: 10s / 5m / 1h")
        return
    await interaction.followup.send(f"{interaction.user.mention} リマインダーセット: {message} (あと {time_str})")
    await asyncio.sleep(seconds)
    await interaction.channel.send(f"{interaction.user.mention} リマインダー: {message}")

@bot.tree.command(name="clear", description="チャンネルのメッセージを削除します（管理者専用）")
async def clear(interaction: discord.Interaction, amount: int = 5):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("権限がありません。", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"{len(deleted)} 件削除しました。", ephemeral=True)

# ===== カレンダー機能 =====
class Calendar(app_commands.Group):
    def __init__(self):
        super().__init__(name="cal", description="予定・Todo一括管理")

    # ---------- 予定操作 ----------
    @app_commands.command(name="add", description="予定を追加します")
    async def add(self, interaction: discord.Interaction, title: str, date: str, time_str: str = None):
        await interaction.response.defer()
        dt_str = f"{date}T{time_str}" if time_str else f"{date}T00:00"
        try:
            dt = datetime.fromisoformat(dt_str)
        except:
            await interaction.followup.send("❌ 日付形式が不正です。YYYY-MM-DD または YYYY-MM-DD HH:MM")
            return
        guild_data = get_guild_data(interaction.guild_id)
        guild_data["events"].append({"title": title, "datetime": dt_str})
        save_data()
        embed = discord.Embed(title="予定追加", description=title, color=0x00ff00)
        embed.add_field(name="日時", value=dt.strftime("%Y-%m-%d %H:%M"))
        await interaction.followup.send(embed=embed)

    async def _send_embed_list(self, interaction, items, title, is_todo=False):
        if not items:
            await interaction.followup.send("データはありません。")
            return
        embed = discord.Embed(title=title, color=0x00ff99 if not is_todo else 0x9b59b6)
        for i, item in enumerate(items, start=1):
            if is_todo:
                status = "✅" if item["done"] else "❌"
                embed.add_field(name=f"{i}. {status} {item['content']}", value=f"追加: {item['added_at']}", inline=False)
            else:
                dt = datetime.fromisoformat(item["datetime"]).strftime("%Y-%m-%d %H:%M")
                embed.add_field(name=f"{i}. {item['title']}", value=f"🗓 {dt}", inline=False)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="list", description="今後の予定を表示します")
    async def list_events(self, interaction: discord.Interaction, max_results: int = 10):
        await interaction.response.defer()
        guild_data = get_guild_data(interaction.guild_id)
        events = sorted(guild_data["events"], key=lambda x: x["datetime"])[:max_results]
        await self._send_embed_list(interaction, events, "今後の予定")

    @app_commands.command(name="today", description="今日の予定を表示します")
    async def today(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_data = get_guild_data(interaction.guild_id)
        today_str = date.today().isoformat()
        today_events = [ev for ev in guild_data["events"] if ev["datetime"].startswith(today_str)]
        today_events.sort(key=lambda x: x["datetime"])
        await self._send_embed_list(interaction, today_events, "今日の予定")

    @app_commands.command(name="remove", description="番号で予定を削除します")
    async def remove(self, interaction: discord.Interaction, index: int):
        await interaction.response.defer()
        guild_data = get_guild_data(interaction.guild_id)
        if index < 1 or index > len(guild_data["events"]):
            await interaction.followup.send("❌ 番号が不正です。")
            return
        removed = guild_data["events"].pop(index-1)
        save_data()
        dt = datetime.fromisoformat(removed["datetime"]).strftime("%Y-%m-%d %H:%M")
        embed = discord.Embed(title="予定削除", description=removed["title"], color=0xe74c3c)
        embed.add_field(name="日時", value=dt)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="clear", description="全予定を削除します（管理者用）")
    async def clear_all(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("権限がありません。", ephemeral=True)
            return
        guild_data = get_guild_data(interaction.guild_id)
        guild_data["events"] = []
        save_data()
        await interaction.response.send_message("✅ 全予定を削除しました", ephemeral=True)

    # ---------- Todo操作 ----------
    @app_commands.command(name="todo_add", description="Todoを追加します")
    async def todo_add(self, interaction: discord.Interaction, content: str):
        await interaction.response.defer()
        guild_data = get_guild_data(interaction.guild_id)
        guild_data["todos"].append({"content": content, "done": False, "added_at": datetime.now().isoformat(), "done_at": None})
        save_data()
        embed = discord.Embed(title="Todo追加", description=content, color=0x00ff00)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="todo_list", description="Todo一覧を表示します")
    async def todo_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_data = get_guild_data(interaction.guild_id)
        todos = guild_data["todos"]
        await self._send_embed_list(interaction, todos, "Todo一覧", is_todo=True)

    @app_commands.command(name="todo_done", description="Todoを完了にします")
    async def todo_done(self, interaction: discord.Interaction, index: int):
        await interaction.response.defer()
        guild_data = get_guild_data(interaction.guild_id)
        if index < 1 or index > len(guild_data["todos"]):
            await interaction.followup.send("❌ 番号が不正です。")
            return
        todo = guild_data["todos"][index-1]
        todo["done"] = True
        todo["done_at"] = datetime.now().isoformat()
        save_data()
        embed = discord.Embed(title="Todo完了", description=todo["content"], color=0x00ff00)
        embed.add_field(name="完了時刻", value=todo["done_at"])
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="todo_remove", description="Todoを削除します")
    async def todo_remove(self, interaction: discord.Interaction, index: int):
        await interaction.response.defer()
        guild_data = get_guild_data(interaction.guild_id)
        if index < 1 or index > len(guild_data["todos"]):
            await interaction.followup.send("❌ 番号が不正です。")
            return
        removed = guild_data["todos"].pop(index-1)
        save_data()
        embed = discord.Embed(title="Todo削除", description=removed["content"], color=0xe74c3c)
        await interaction.followup.send(embed=embed)

bot.tree.add_command(Calendar())

# ===== 非同期でFlask & Bot同時起動 =====
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    bot.run(TOKEN)
