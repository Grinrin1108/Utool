# commands/reminder.py
from discord import app_commands, ui
import discord
import asyncio
import os
import json
import requests
from datetime import datetime, timezone, timedelta
import re

# --- 基本設定 ---
JST = timezone(timedelta(hours=9))
SCOPES = ['https://www.googleapis.com/auth/calendar']
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

# --- 時間解析ユーティリティ ---
def parse_extended_datetime(date_str, time_str):
    """
    "2024-05-20" と "25:30" を受け取り、
    "2024-05-21 01:30" の datetime オブジェクトを返す
    """
    base_dt = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=JST)
    
    # 区切り文字を統一 (25:30 or 25.30)
    time_str = time_str.replace('.', ':')
    match = re.match(r"(\d{1,2}):(\d{2})", time_str)
    if not match:
        raise ValueError("Invalid time format")
        
    hours, minutes = map(int, match.groups())
    
    # 24時間以上の加算処理
    actual_dt = base_dt + timedelta(days=(hours // 24))
    return actual_dt.replace(hour=(hours % 24), minute=minutes)

# --- Google Calendar Manager ---
class GoogleCalendarManager:
    def __init__(self):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            try:
                info = json.loads(creds_json)
                self.creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
                self.service = build('calendar', 'v3', credentials=self.creds)
            except: self.service = None
        else: self.service = None

    def add_event(self, calendar_id, title, date_str, start_time_str=None, end_time_str=None):
        if not self.service: return
        
        if start_time_str:
            # 25時表記などに対応した開始時間
            s_dt = parse_extended_datetime(date_str, start_time_str)
            
            if end_time_str:
                # 終了時間の解析
                e_dt = parse_extended_datetime(date_str, end_time_str)
                # 開始より終了が前なら、翌日として扱う（23:00〜01:00など）
                if e_dt <= s_dt:
                    e_dt += timedelta(days=1)
            else:
                e_dt = s_dt + timedelta(hours=1)
                
            body = {
                'summary': title,
                'start': {'dateTime': s_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
                'end': {'dateTime': e_dt.isoformat(), 'timeZone': 'Asia/Tokyo'}
            }
        else:
            # 終日の予定
            body = {
                'summary': title,
                'start': {'date': date_str},
                'end': {'date': (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')}
            }
        return self.service.events().insert(calendarId=calendar_id, body=body).execute()

    def get_events(self, calendar_id, days=7):
        if not self.service: return []
        now = datetime.now(JST)
        time_min = now.replace(hour=0, minute=0, second=0).isoformat()
        time_max = (now + timedelta(days=days)).replace(hour=23, minute=59, second=59).isoformat()
        try:
            res = self.service.events().list(calendarId=calendar_id, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
            return res.get('items', [])
        except: return []

# --- UIパーツ ---

class UniversalAddModal(ui.Modal, title="予定の登録"):
    # 日付入力欄（デフォルト値を設定可能にする）
    date_input = ui.TextInput(label="日付 (YYYY-MM-DD)", placeholder="例: 2024-12-25", min_length=10, max_length=10)
    title_input = ui.TextInput(label="タイトル", placeholder="例: 深夜の作業", required=True)
    start_input = ui.TextInput(label="開始時間 (25:00対応)", placeholder="23:00", required=False)
    end_input = ui.TextInput(label="終了時間 (26:30対応)", placeholder="01:30", required=False)

    def __init__(self, gcal, cid, default_date=""):
        super().__init__()
        self.gcal, self.cid = gcal, cid
        if default_date:
            self.date_input.default = default_date

    async def on_submit(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        try:
            self.gcal.add_event(
                self.cid, 
                self.title_input.value, 
                self.date_input.value, 
                self.start_input.value or None, 
                self.end_input.value or None
            )
            await it.followup.send(f"✅ **{self.title_input.value}** を登録しました！", ephemeral=True)
        except Exception as e:
            await it.followup.send(f"❌ 登録に失敗しました。形式を確認してください。\n日付: `2024-05-20` / 時間: `25:30`", ephemeral=True)

class ReminderMenuView(ui.View):
    def __init__(self, gcal, dm):
        super().__init__(timeout=None)
        self.gcal, self.dm = gcal, dm

    @ui.button(label="➕ 2週間以内の予定", style=discord.ButtonStyle.success, emoji="📅")
    async def quick_add(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        if not cid: return await it.response.send_message("❌ 先に設定が必要です。", ephemeral=True)

        view = ui.View()
        select = ui.Select(placeholder="日付を選択...")
        now = datetime.now(JST)
        for i in range(14):
            target = now + timedelta(days=i)
            val = target.strftime('%Y-%m-%d')
            label = target.strftime('%m/%d') + f" ({WEEKDAYS[target.weekday()]})"
            select.add_option(label=label, value=val)

        async def callback(sit: discord.Interaction):
            await sit.response.send_modal(UniversalAddModal(self.gcal, cid, default_date=select.values[0]))
        
        select.callback = callback
        view.add_item(select)
        await it.response.send_message("日付を選んでください：", view=view, ephemeral=True)

    @ui.button(label="🚀 日付を指定して追加", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def manual_add(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        # デフォルト日付なしでModalを開く
        await it.response.send_modal(UniversalAddModal(self.gcal, cid))

    @ui.button(label="🔍 予定確認", style=discord.ButtonStyle.primary)
    async def list_events(self, it: discord.Interaction, button: ui.Button):
        await it.response.defer(ephemeral=True)
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        events = self.gcal.get_events(cid)
        embed = discord.Embed(title="🗓️ 近日の予定", color=0x4285F4)
        if not events:
            embed.description = "予定はありません。"
        else:
            for e in events:
                start = e['start'].get('dateTime', e['start'].get('date'))
                time_disp = f"`{start[11:16]}`" if 'T' in start else "☀️ `終日`"
                embed.add_field(name=f"{start[:10]} {time_disp}", value=f"**{e['summary']}**\nID: `{e['id']}`", inline=False)
        await it.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="🗑️ 削除", style=discord.ButtonStyle.danger)
    async def delete_event(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        class DelModal(ui.Modal, title="削除"):
            ev_id = ui.TextInput(label="イベントID")
            async def on_submit(self, sit: discord.Interaction):
                self.gcal.service.events().delete(calendarId=cid, eventId=self.ev_id.value).execute()
                await sit.response.send_message("🗑️ 削除完了", ephemeral=True)
        await it.response.send_modal(DelModal())

# --- コマンド登録 ---
def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self): super().__init__(name="rem", description="カレンダー管理")

        @app_commands.command(name="menu", description="操作メニューを開く")
        async def menu(self, it: discord.Interaction):
            embed = discord.Embed(title="🗓️ カレンダー操作パネル", description="「25:00」などの深夜表記や、遠い未来の予定にも対応しています。", color=0x4285F4)
            await it.response.send_message(embed=embed, view=ReminderMenuView(gcal, data_manager))

        @app_commands.command(name="on", description="初期設定")
        async def on(self, it: discord.Interaction, calendar_id: str):
            data = data_manager.get_guild_data(it.guild_id)
            data["google_calendar_id"] = calendar_id
            data["reminder"] = {"enabled": True, "channel_id": it.channel_id}
            await data_manager.save_all()
            await it.response.send_message("✅ 設定完了！")

    bot.tree.add_command(Reminder())
    # 通知ループなどは以前のものを継承（中略）
