import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import nest_asyncio
from flask import Flask
import threading
import requests
import time

# 各機能（コマンド群）のインポート
from utils.data_manager import DataManager
from commands import utility, fun, reminder, todo

# 非同期ループのネストを許可（Flaskとの共存用）
nest_asyncio.apply()
load_dotenv()

# 環境変数の読み込み
TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", 10000))
SELF_URL = os.getenv("SELF_URL")
DATA_CHANNEL_ID = int(os.getenv("DATA_CHANNEL_ID", 0))

# Discord Botの権限設定
intents = discord.Intents.default()
intents.message_content = True  # メッセージ内容の取得を許可
intents.members = True          # メンバー情報の取得を許可
bot = commands.Bot(command_prefix="!", intents=intents)

# 起動時の重複処理を防止するためのフラグ
bot.initialized = False

# --- Flask Server (Render等のスリープ防止用) ---
app = Flask(__name__)

@app.route("/")
def health():
    return "Bot is alive!"

def run_flask():
    """Flaskサーバーを別スレッドで実行"""
    app.run(host="0.0.0.0", port=PORT)

def keep_alive():
    """自分自身に定期的にアクセスしてスリープを防止"""
    while True:
        try:
            if SELF_URL:
                requests.get(SELF_URL)
        except Exception as e:
            print(f"Keep-alive ping failed: {e}")
        time.sleep(300) # 5分おきに実行

# --- データ管理クラスの初期化 ---
data_manager = DataManager(bot, DATA_CHANNEL_ID)

# --- Botのイベント ---

@bot.event
async def on_ready():
    """Bot起動時に実行される処理"""
    if not bot.initialized:
        # 保存データの読み込み
        await data_manager.load_files()
        
        # 各コマンドカテゴリーの登録
        utility.register_utility_commands(bot)
        fun.register_fun_commands(bot)
        reminder.register_reminder_commands(bot, data_manager)
        todo.register_todo_commands(bot, data_manager)

        # スラッシュコマンドをDiscord側に同期
        try:
            synced = await bot.tree.sync()
            print(f"Successfully synced {len(synced)} slash commands.")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

        bot.initialized = True
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")
        print("------")

# --- メイン処理 ---

if __name__ == "__main__":
    # Flaskサーバーをバックグラウンドで起動
    threading.Thread(target=run_flask, daemon=True).start()
    
    # 自己スリープ防止のループをバックグラウンドで起動
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Botの実行
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: TOKEN is not set in environment variables.")
