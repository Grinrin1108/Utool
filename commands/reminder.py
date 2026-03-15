# commands/reminder.py
from discord import app_commands
import discord
import asyncio
import os
import json
import requests
from datetime import datetime, timezone, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- 設定 ---
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

# --- 日付・時間の解析ロジック ---
def parse_date_string(date_str):
    now = datetime.now(JST)
    today_weekday = now.weekday()
    
    if date_str == "今日": return now.strftime('%Y-%m-%d')
    if date_str == "明日": return (now + timedelta(days=1)).strftime('%Y-%m-%d')
    if date_str == "明後日": return (now + timedelta(days=2)).strftime('%Y-%m-%d')
    
    if "週の" in date_str:
        target_name = date_str[-3] # 「水」曜日
        if target_name in WEEKDAY_MAP:
            target_weekday = WEEKDAY_MAP[target_name]
            offset = 7 if "来週" in date_str else 0
            days_ahead = target_weekday - today_weekday + offset
            return (now + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    
    return date_str # 手入力の YYYY-MM-DD

# --- Google Calendar 制御クラス ---
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

    def get_events(self, calendar_id, days=1):
        if not self.service: return []
        now = datetime.now(JST)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        time_max = (now + timedelta(days=days)).replace(hour=23, minute=59, second=59).isoformat()
        try:
            res = self.service.events().list(calendarId=calendar_id, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
            return res.get('items', [])
        except: return []

    def add_event(self, calendar_id, title, date_str, start_time=None, end_time=None):
        if not self.service: return
        actual_date = parse_date_string(date_str)
        if start_time:
            s_dt = datetime.strptime(f"{actual_date} {start_time}", '%Y-%m-%d %H:%M').replace(tzinfo=JST)
            if end_time:
                e_dt = datetime.strptime(f"{actual_date} {end_time}", '%Y-%m-%d %H:%M').replace(tzinfo=JST)
                if e_dt <= s_dt: e_dt += timedelta(days=1)
            else: e_dt = s_dt + timedelta(hours=1)
            body = {'summary': title, 'start': {'dateTime': s_dt.isoformat(), 'timeZone': 'Asia/Tokyo'}, 'end': {'dateTime': e_dt.isoformat(), 'timeZone': 'Asia/Tokyo'}}
        else:
            s_date = datetime.strptime(actual_date, '%Y-%m-%d')
            body = {'summary': title, 'start': {'date': s_date.strftime('%Y-%m-%d')}, 'end': {'date': (s_date + timedelta(days=1)).strftime('%Y-%m-%d')}}
        return self.service.events().insert(calendarId=calendar_id, body=body).execute()

# --- 天気・表示整形 ---
def get_weather():
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=35.6895&longitude=139.6917&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=Asia%2FTokyo").json()
        forecast = {}
        for i, d in enumerate(r['daily']['time']):
            forecast[d] = f"{WEATHER_CODES.get(r['daily']['weathercode'][i], '❓')} ({r['daily']['temperature_2m_max'][i]}℃/{r['daily']['temperature_2m_min'][i]}℃)"
        return forecast
    except: return {}

def format_list(events, weather_map, title):
    embed = discord.Embed(title=f"🗓️ {title}", color=0x4285F4)
    if not events:
        embed.description = "✨ 予定はありません。"; return embed
    grouped = {}
    for e in events:
        d = e['start'].get('dateTime', e['start'].get('date'))[:10]
        if d not in grouped: grouped[d] = []
        grouped[d].append(e)
    for date_key, day_events in sorted(grouped.items()):
        dt = datetime.strptime(date_key, '%Y-%m-%d')
        field_name = f"📅 {dt.strftime('%m/%d')}({WEEKDAYS[dt.weekday()]}) {weather_map.get(date_key, '')}"
        lines = []
        for e in day_events:
            st = e['start'].get('dateTime', e['start'].get('date'))
            time_str = f"⏰ `{st[11:16]}`" if 'T' in st else "☀️ `終日`"
            lines.append(f"{time_str} **{e['summary']}**\n└ `{e['id']}`")
        embed.add_field(name=field_name, value="\n".join(lines) + "\n\u200b", inline=False)
    return embed

# --- コマンド登録 ---
def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self): super().__init__(name="rem", description="Googleカレンダー連携")

        @app_commands.command(name="on", description="通知をこのチャンネルで有効にします")
        async def on(self, interaction: discord.Interaction, calendar_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            guild_data["google_calendar_id"] = calendar_id
            guild_data["reminder"] = {"enabled": True, "channel_id": interaction.channel_id}
            await data_manager.save_all()
            await interaction.response.send_message(f"✅ 設定完了！朝6時と10分前に通知します。")

        # --- 日付・時間のオートコンプリート（予測変換） ---
        @app_commands.command(name="gcal_add", description="予定を追加します")
        async def gcal_add(self, interaction: discord.Interaction, date: str, title: str, start_time: str = None, end_time: str = None):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cid = guild_data.get("google_calendar_id")
            if not cid: return await interaction.followup.send("❌ /rem on を先に実行してください。")
            try:
                gcal.add_event(cid, title, date, start_time, end_time)
                await interaction.followup.send(f"✅ 登録しました: **{title}** ({date})")
            except: await interaction.followup.send("❌ 形式エラー。日付や時刻を確認してください。")

        @gcal_add.autocomplete('date')
        async def date_autocomplete(self, interaction: discord.Interaction, current: str):
            candidates = ["今日", "明日", "明後日"]
            for week in ["今週の", "来週の"]:
                for day in ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]:
                    candidates.append(f"{week}{day}")
            return [app_commands.Choice(name=c, value=c) for c in candidates if current in c][:25]

        @gcal_add.autocomplete('start_time')
        @gcal_add.autocomplete('end_time')
        async def time_autocomplete(self, interaction: discord.Interaction, current: str):
            times = [f"{h:02}:{m:02}" for h in range(7, 24) for m in [0, 30]]
            return [app_commands.Choice(name=t, value=t) for t in times if current in t][:25]

        @app_commands.command(name="gcal_list", description="予定を表示します")
        @app_commands.choices(duration=[app_commands.Choice(name="今日のみ", value=1), app_commands.Choice(name="1週間分", value=7)])
        async def gcal_list(self, interaction: discord.Interaction, duration: int = 7):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cid = guild_data.get("google_calendar_id")
            if not cid: return await interaction.followup.send("❌ ID未設定")
            events = gcal.get_events(cid, days=duration)
            await interaction.followup.send(embed=format_list(events, get_weather(), "予定リスト"))

        @app_commands.command(name="gcal_delete", description="予定を削除します")
        async def gcal_delete(self, interaction: discord.Interaction, event_id: str):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            try:
                gcal.service.events().delete(calendarId=guild_data.get("google_calendar_id"), eventId=event_id).execute()
                await interaction.followup.send("🗑️ 削除しました。")
            except: await interaction.followup.send("❌ 削除失敗。")

    bot.tree.add_command(Reminder())

    # --- 通知ループ ---
    async def reminder_loop():
        await bot.wait_until_ready()
        last_reminded = set()
        while not bot.is_closed():
            now = datetime.now(JST)
            # 6:00 定期通知
            if now.hour == 6 and now.minute == 0:
                weather_map = get_weather()
                for gid, gdata in data_manager.data.items():
                    rem = gdata.get("reminder", {})
                    if rem.get("enabled"):
                        ch, cid = bot.get_channel(rem.get("channel_id")), gdata.get("google_calendar_id")
                        if ch and cid:
                            events = gcal.get_events(cid, days=1)
                            await ch.send(embed=format_list(events, weather_map, "今日の予定"))
                await asyncio.sleep(60)
            # 10分前リマインド
            for gid, gdata in data_manager.data.items():
                rem = gdata.get("reminder", {})
                if rem.get("enabled"):
                    ch, cid = bot.get_channel(rem.get("channel_id")), gdata.get("google_calendar_id")
                    if ch and cid:
                        try:
                            events = gcal.get_events(cid, days=1)
                            for e in events:
                                st = e['start'].get('dateTime')
                                if not st: continue
                                st_dt = datetime.fromisoformat(st.replace('Z', '+00:00')).astimezone(JST)
                                diff = (st_dt - now).total_seconds()
                                if 540 < diff <= 600 and e['id'] not in last_reminded:
                                    embed = discord.Embed(title="🕒 10分前リマインド", description=f"### **{e['summary']}**", color=0xff4757)
                                    await ch.send(content="@everyone", embed=embed)
                                    last_reminded.add(e['id'])
                        except: pass
            if len(last_reminded) > 100: last_reminded.clear()
            await asyncio.sleep(30)

    if not hasattr(bot, "_reminder_loop_started"):
        bot._reminder_loop_started = True
        asyncio.create_task(reminder_loop())
