import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import nest_asyncio
import random
from datetime import datetime
from flask import Flask
import threading
import requests
import time
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Render用非同期調整
nest_asyncio.apply()
load_dotenv()
TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", 10000))
SELF_URL = os.getenv("SELF_URL")  # Render URL, Ping用

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
        time.sleep(300)  # 5分おき

# ===== Google Calendar設定 =====
SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_INFO = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
credentials = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO, scopes=SCOPES
)
calendar_service = build('calendar', 'v3', credentials=credentials)
CALENDAR_ID = os.getenv("CALENDAR_ID")  # サービスアカウント共有済みカレンダーのメール

# ===== Botイベント =====
@bot.event
async def on_ready():
    await bot.tree.sync()  # スラッシュコマンド同期
    print(f"Logged in as {bot.user} (slash commands synced)")

# ===== スラッシュコマンド =====
# ユーザー情報表示
@bot.tree.command(name="userinfo", description="ユーザー情報を表示します")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"{member}", description="ユーザー情報", color=0x00ff00)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="作成日", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
    await interaction.response.send_message(embed=embed)

# サーバー情報表示
@bot.tree.command(name="serverinfo", description="サーバー情報を表示します")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"{guild.name}", description="サーバー情報", color=0x0000ff)
    embed.add_field(name="ID", value=guild.id)
    embed.add_field(name="メンバー数", value=guild.member_count)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    await interaction.response.send_message(embed=embed)

# アバター表示
@bot.tree.command(name="avatar", description="ユーザーのアバターを表示します")
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"{member}'s Avatar")
    embed.set_image(url=member.avatar.url if member.avatar else None)
    await interaction.response.send_message(embed=embed)

# さいころをふる
@bot.tree.command(name="roll", description="サイコロを振ります (例: 2d6)")
async def roll(interaction: discord.Interaction, dice: str):
    try:
        rolls, limit = map(int, dice.lower().split('d'))
    except Exception:
        await interaction.response.send_message("形式が違います。例: `/roll 2d6`")
        return
    results = [random.randint(1, limit) for _ in range(rolls)]
    await interaction.response.send_message(f"{interaction.user.mention} rolled {dice}: {results} → 合計: {sum(results)}")

# 投票作成
@bot.tree.command(name="poll", description="投票を作成します")
async def poll(interaction: discord.Interaction, question: str, option1: str, option2: str, option3: str = None, option4: str = None):
    options = [opt for opt in [option1, option2, option3, option4] if opt]
    if len(options) < 2:
        await interaction.response.send_message("選択肢は2つ以上必要です。")
        return
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣"]
    description = "\n".join(f"{emojis[i]} {opt}" for i,opt in enumerate(options))
    embed = discord.Embed(title=question, description=description, color=0xffa500)
    msg = await interaction.channel.send(embed=embed)
    for i in range(len(options)):
        await msg.add_reaction(emojis[i])
    await interaction.response.send_message("✅ 投票を作成しました", ephemeral=True)

# リマインダー作成
@bot.tree.command(name="remind", description="リマインダーを設定します (例: 10s / 5m / 1h)")
async def remind(interaction: discord.Interaction, time_str: str, message: str):
    amount = int(time_str[:-1])
    unit = time_str[-1]
    seconds = amount * 60 if unit == "m" else amount * 3600 if unit=="h" else amount
    await interaction.response.send_message(f"{interaction.user.mention} リマインダーセット: {message} (あと {time_str})")
    await asyncio.sleep(seconds)
    await interaction.channel.send(f"{interaction.user.mention} リマインダー: {message}")

# メッセージ削除（管理者用）
@bot.tree.command(name="clear", description="チャンネルのメッセージを削除します（管理者専用）")
async def clear(interaction: discord.Interaction, amount: int = 5):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("権限がありません。", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"{len(deleted)} 件削除しました。", ephemeral=True)

# ===== Googleカレンダー =====
# カレンダーの予定一覧表示
@bot.tree.command(name="cal_list", description="カレンダーの今後の予定を表示します")
async def cal_list(interaction: discord.Interaction, max_results: int = 5):
    now = datetime.utcnow().isoformat() + 'Z'
    events_result = calendar_service.events().list(
        calendarId=CALENDAR_ID, timeMin=now,
        maxResults=max_results, singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])
    if not events:
        await interaction.response.send_message("予定はありません。")
        return
    msg = ""
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        msg += f"{start}: {event['summary']}\n"
    await interaction.response.send_message(msg)

# カレンダーに予定追加
@bot.tree.command(name="cal_add", description="カレンダーに新しい予定を追加します")
async def cal_add(interaction: discord.Interaction, summary: str, date: str, time: str = None):
    start_dt = f"{date}T{time}:00" if time else f"{date}T00:00:00"
    event = {
        'summary': summary,
        'start': {'dateTime': start_dt, 'timeZone': 'Asia/Tokyo'},
        'end': {'dateTime': start_dt, 'timeZone': 'Asia/Tokyo'},
    }
    created_event = calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    await interaction.response.send_message(f"予定を追加しました: {created_event.get('summary')}")

# ===== 非同期でFlask & Bot同時起動 =====
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    bot.run(TOKEN)
