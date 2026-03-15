# commands/reminder.py
from discord import app_commands, ui
import discord
import asyncio
import os
import json
import requests
from datetime import datetime, timezone, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- 定数設定 ---
JST = timezone(timedelta(hours=9))
SCOPES = ['https://www.googleapis.com/auth/calendar']
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
WEEKDAY_MAP = {"月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6}

WEATHER_CODES = {
    0: "☀️快晴", 1: "🌤️晴れ", 2: "⛅くもり", 3: "☁️曇り",
    45: "🌫️霧", 48: "🌫️霧", 51: "🚿小雨", 53: "🚿小雨", 55: "🚿小雨",
    61: "☔雨", 63: "☔雨", 65: "☔激しい雨", 71: "❄️雪", 73: "❄️雪", 75: "❄️激しい雪",
    80: "🌦️にわか雨", 81: "🌦️にわか雨", 82: "🌦️激しいにわか雨", 95: "⚡雷雨"
}

# --- 解析ユーティリティ ---
def parse_date_string(date_str):
    now = datetime.now(JST)
    if date_str == "今日": return now.strftime('%Y-%m-%d')
    if date_str == "明日": return (now + timedelta(days=1)).strftime('%Y-%m-%d')
    if date_str == "明後日": return (now + timedelta(days=2)).strftime('%Y-%m-%d')
    if "週の" in date_str:
        target_name = date_str[-3] # 「月」曜日
        offset = 7 if "来週" in date_str else 0
        days_ahead = WEEKDAY_MAP[target_name] - now.weekday() + offset
        return (now + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    return date_str

def get_weather():
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=35.6895&longitude=139.6917&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=Asia%2FTokyo").json()
        forecast = {}
        for i, d in enumerate(r['daily']['time']):
            forecast[d] = f"{WEATHER_CODES.get(r['daily']['weathercode'][i], '❓')} ({r['daily']['temperature_2m_max'][i]}℃/{r['daily']['temperature_2m_min'][i]}℃)"
        return forecast
    except: return {}

# --- Google Calendar Manager ---
class GoogleCalendarManager:
    def __init__(self):
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            try:
                info = json.loads(creds_json)
                self.creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
                self.service = build('calendar', 'v3', credentials=self.creds)
            except: self.service = None
        else: self.service = None

    def get_events(self, calendar_id, days=7):
        if not self.service: return []
        now = datetime.now(JST)
        time_min = now.replace(hour=0, minute=0, second=0).isoformat()
        time_max = (now + timedelta(days=days)).replace(hour=23, minute=59, second=59).isoformat()
        try:
            res = self.service.events().list(calendarId=calendar_id, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
            return res.get('items', [])
        except: return []

    def add_event(self, calendar_id, title, date_str, start_time=None, end_time=None):
        actual_date = parse_date_string(date_str)
        if start_time:
            s_dt = datetime.strptime(f"{actual_date} {start_time}", '%Y-%m-%d %H:%M').replace(tzinfo=JST)
            if end_time:
                e_dt = datetime.strptime(f"{actual_date} {end_time}", '%Y-%m-%d %H:%M').replace(tzinfo=JST)
                if e_dt <= s_dt: e_dt += timedelta(days=1)
            else: e_dt = s_dt + timedelta(hours=1)
            body = {'summary': title, 'start': {'dateTime': s_dt.isoformat(), 'timeZone': 'Asia/Tokyo'}, 'end': {'dateTime': e_dt.isoformat(), 'timeZone': 'Asia/Tokyo'}}
        else:
            body = {'summary': title, 'start': {'date': actual_date}, 'end': {'date': (datetime.strptime(actual_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')}}
        return self.service.events().insert(calendarId=calendar_id, body=body).execute()

# --- UIパーツ ---
class AddModal(ui.Modal, title="予定の登録"):
    title_in = ui.TextInput(label="タイトル", placeholder="例：会議、飲み会", required=True)
    start_in = ui.TextInput(label="開始時間 (例 19:00 / 空欄で終日)", placeholder="19:00", required=False)
    end_in = ui.TextInput(label="終了時間 (例 21:00)", placeholder="21:00", required=False)

    def __init__(self, gcal, cid, date):
        super().__init__()
        self.gcal, self.cid, self.date = gcal, cid, date

    async def on_submit(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        try:
            self.gcal.add_event(self.cid, self.title_in.value, self.date, self.start_in.value or None, self.end_in.value or None)
            await it.followup.send(f"✅ **{self.title_in.value}** を {self.date} に登録しました！", ephemeral=True)
        except: await it.followup.send("❌ 形式エラー。時間は 14:00 のように入力してください。", ephemeral=True)

class DeleteModal(ui.Modal, title="予定の削除"):
    id_in = ui.TextInput(label="イベントIDを貼り付けてください", placeholder="リストに表示されている ID をコピーして貼り付け", required=True)
    def __init__(self, gcal, cid):
        super().__init__()
        self.gcal, self.cid = gcal, cid
    async def on_submit(self, it: discord.Interaction):
        try:
            self.gcal.service.events().delete(calendarId=self.cid, eventId=self.id_in.value).execute()
            await it.response.send_message("🗑️ 予定を削除しました。", ephemeral=True)
        except: await it.response.send_message("❌ 削除失敗。IDが正しいか確認してください。", ephemeral=True)

class ReminderMenuView(ui.View):
    def __init__(self, gcal, dm):
        super().__init__(timeout=None)
        self.gcal, self.dm = gcal, dm

    @ui.button(label="➕ 予定を追加", style=discord.ButtonStyle.success)
    async def add(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        if not cid: return await it.response.send_message("❌ 先に /rem on で設定してください。", ephemeral=True)
        
        view = ui.View()
        select = ui.Select(placeholder="日付を選んでください")
        dates = ["今日", "明日", "明後日"] + [f"今週の{d}曜日" for d in WEEKDAYS] + [f"来週の{d}曜日" for d in WEEKDAYS]
        for d in dates: select.add_option(label=d, value=d)
        
        async def callback(sit: discord.Interaction):
            await sit.response.send_modal(AddModal(self.gcal, cid, select.values[0]))
        select.callback = callback
        view.add_item(select)
        await it.response.send_message("どの日付に追加しますか？", view=view, ephemeral=True)

    @ui.button(label="📅 予定を確認", style=discord.ButtonStyle.primary)
    async def list(self, it: discord.Interaction, button: ui.Button):
        await it.response.defer(ephemeral=True)
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        events = self.gcal.get_events(cid)
        weather = get_weather()
        embed = discord.Embed(title="🗓️ 直近の予定", color=0x4285F4)
        if not events: embed.description = "予定はありません。"
        else:
            grouped = {}
            for e in events:
                d = e['start'].get('dateTime', e['start'].get('date'))[:10]
                if d not in grouped: grouped[d] = []
                grouped[d].append(e)
            for d, evs in sorted(grouped.items()):
                dt = datetime.strptime(d, '%Y-%m-%d')
                name = f"📅 {dt.strftime('%m/%d')}({WEEKDAYS[dt.weekday()]}) {weather.get(d, '')}"
                lines = [f"{'⏰' if 'T' in e['start'].get('dateTime', '') else '☀️'} `{e['start'].get('dateTime', '終日')[11:16]}` **{e['summary']}**\n└ `{e['id']}`" for e in evs]
                embed.add_field(name=name, value="\n".join(lines) + "\n\u200b", inline=False)
        await it.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="🗑️ 予定を削除", style=discord.ButtonStyle.danger)
    async def delete(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        await it.response.send_modal(DeleteModal(self.gcal, cid))

# --- メイン登録 ---
def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self): super().__init__(name="rem", description="カレンダー操作")

        @app_commands.command(name="menu", description="操作パネルを表示します")
        async def menu(self, it: discord.Interaction):
            embed = discord.Embed(title="🗓️ リマインダー操作パネル", description="ボタンを押して操作を開始してください。", color=0x4285F4)
            await it.response.send_message(embed=embed, view=ReminderMenuView(gcal, data_manager))

        @app_commands.command(name="on", description="初期設定（カレンダーIDの登録）")
        async def on(self, it: discord.Interaction, calendar_id: str):
            data = data_manager.get_guild_data(it.guild_id)
            data["google_calendar_id"] = calendar_id
            data["reminder"] = {"enabled": True, "channel_id": it.channel_id}
            await data_manager.save_all()
            await it.response.send_message("✅ 通知をONにしました！朝6時と10分前に通知します。")

    bot.tree.add_command(Reminder())

    # --- 通知ループ (6時 & 10分前) ---
    async def loop():
        await bot.wait_until_ready()
        reminded = set()
        while not bot.is_closed():
            now = datetime.now(JST)
            # 6:00通知
            if now.hour == 6 and now.minute == 0:
                weather = get_weather()
                for gid, gdata in data_manager.data.items():
                    r = gdata.get("reminder", {})
                    if r.get("enabled"):
                        ch, cid = bot.get_channel(r.get("channel_id")), gdata.get("google_calendar_id")
                        if ch and cid:
                            evs = gcal.get_events(cid, days=1)
                            embed = discord.Embed(title="☀️ 今日の予定", color=0x4285F4)
                            lines = [f"・`{e['start'].get('dateTime', '  終日  ')[11:16]}` {e['summary']}" for e in evs]
                            embed.description = f"今日の天気: {weather.get(now.strftime('%Y-%m-%d'), '')}\n\n" + ("\n".join(lines) if lines else "予定はありません。")
                            await ch.send(embed=embed)
                await asyncio.sleep(60)
            # 10分前通知
            for gid, gdata in data_manager.data.items():
                r = gdata.get("reminder", {})
                if r.get("enabled"):
                    ch, cid = bot.get_channel(r.get("channel_id")), gdata.get("google_calendar_id")
                    if ch and cid:
                        try:
                            for e in gcal.get_events(cid, days=1):
                                st = e['start'].get('dateTime')
                                if st and e['id'] not in reminded:
                                    diff = (datetime.fromisoformat(st.replace('Z', '+00:00')).astimezone(JST) - now).total_seconds()
                                    if 540 < diff <= 600:
                                        await ch.send(f"🕒 **10分前:** {e['summary']} が始まります！", content="@everyone")
                                        reminded.add(e['id'])
                        except: pass
            if len(reminded) > 100: reminded.clear()
            await asyncio.sleep(30)
    
    if not hasattr(bot, "_rem_loop"):
        bot._rem_loop = True
        asyncio.create_task(loop())
