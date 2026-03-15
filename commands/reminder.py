# commands/reminder.py
from discord import app_commands
import discord
from discord import ui
import asyncio
import os
import json
import requests
from datetime import datetime, timezone, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- 基本設定 (前回同様) ---
JST = timezone(timedelta(hours=9))
SCOPES = ['https://www.googleapis.com/auth/calendar']
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
WEEKDAY_MAP = {"月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6}

# --- 解析ユーティリティ ---
def parse_date_string(date_str):
    now = datetime.now(JST)
    if date_str == "今日": return now.strftime('%Y-%m-%d')
    if date_str == "明日": return (now + timedelta(days=1)).strftime('%Y-%m-%d')
    if "週の" in date_str:
        target_name = date_str[-3]
        offset = 7 if "来週" in date_str else 0
        days_ahead = WEEKDAY_MAP[target_name] - now.weekday() + offset
        return (now + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    return date_str

# --- UIパーツ: 予定追加用フォーム ---
class AddEventModal(ui.Modal, title='予定の詳細入力'):
    title_input = ui.TextInput(label='タイトル', placeholder='例: 会議, 飲み会', required=True)
    start_input = ui.TextInput(label='開始時間', placeholder='例: 14:00 (終日の場合は空欄)', required=False)
    end_input = ui.TextInput(label='終了時間', placeholder='例: 15:30', required=False)

    def __init__(self, gcal, calendar_id, selected_date):
        super().__init__()
        self.gcal = gcal
        self.calendar_id = calendar_id
        self.selected_date = selected_date

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            self.gcal.add_event(
                self.calendar_id, 
                self.title_input.value, 
                self.selected_date, 
                self.start_input.value or None, 
                self.end_input.value or None
            )
            await interaction.followup.send(f"✅ **{self.title_input.value}** を {self.selected_date} に登録しました！", ephemeral=True)
        except:
            await interaction.followup.send("❌ 登録に失敗しました。時間の形式を確認してください。", ephemeral=True)

# --- UIパーツ: メインメニューView ---
class ReminderMenuView(ui.View):
    def __init__(self, gcal, data_manager):
        super().__init__(timeout=None)
        self.gcal = gcal
        self.dm = data_manager

    @ui.button(label="➕ 予定を追加", style=discord.ButtonStyle.success, custom_id="rem_add")
    async def add_button(self, interaction: discord.Interaction, button: ui.Button):
        # 日付選択メニューを表示
        view = ui.View()
        select = ui.Select(placeholder="どの日付に予定を入れますか？")
        dates = ["今日", "明日"] + [f"今週の{d}曜日" for d in WEEKDAYS] + [f"来週の{d}曜日" for d in WEEKDAYS]
        for d in dates[:25]: # Discord制限
            select.add_option(label=d, value=d)
        
        async def select_callback(it: discord.Interaction):
            cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
            await it.response.send_modal(AddEventModal(self.gcal, cid, select.values[0]))

        select.callback = select_callback
        view.add_item(select)
        await interaction.response.send_message("日付を選んでください：", view=view, ephemeral=True)

    @ui.button(label="📅 予定を確認", style=discord.ButtonStyle.primary, custom_id="rem_list")
    async def list_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        cid = self.dm.get_guild_data(interaction.guild_id).get("google_calendar_id")
        events = self.gcal.get_events(cid, days=7)
        # format_list は以前のロジックを使用 (省略箇所は以前のコードを再利用)
        from .reminder import format_list, get_weather 
        embed = format_list(events, get_weather(), "直近1週間の予定")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="⚙️ 設定 (ON/OFF)", style=discord.ButtonStyle.secondary, custom_id="rem_config")
    async def config_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("カレンダーIDを設定するには `/rem on [ID]` を入力してください。", ephemeral=True)

# --- メインロジック ---
def register_reminder_commands(bot, data_manager):
    from .reminder import GoogleCalendarManager # 既存のManagerクラス
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self): super().__init__(name="rem", description="カレンダー操作")

        @app_commands.command(name="menu", description="操作パネルを開きます")
        async def menu(self, interaction: discord.Interaction):
            embed = discord.Embed(
                title="🗓️ リマインダー操作パネル",
                description="下のボタンから操作を選んでください。\nコマンドを覚える必要はありません！",
                color=0x4285F4
            )
            await interaction.response.send_message(embed=embed, view=ReminderMenuView(gcal, data_manager))

        @app_commands.command(name="on", description="初期設定")
        async def on(self, interaction: discord.Interaction, calendar_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            guild_data["google_calendar_id"] = calendar_id
            guild_data["reminder"] = {"enabled": True, "channel_id": interaction.channel_id}
            await data_manager.save_all()
            await interaction.response.send_message(f"✅ 設定しました！")

    bot.tree.add_command(Reminder())
    # 通知ループなどは以前のものをそのまま維持
