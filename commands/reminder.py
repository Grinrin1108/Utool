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

# JST タイムゾーン設定
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

# --- Utility: 日付・時間解析 ---
def parse_date_string(date_str):
    """「明日」「来週の月」などの文字列を YYYY-MM-DD 形式に変換する"""
    now = datetime.now(JST)
    today_weekday = now.weekday()

    if date_str in ["今日", "きょう"]:
        return now.strftime('%Y-%m-%d')
    elif date_str in ["明日", "あした"]:
        return (now + timedelta(days=1)).strftime('%Y-%m-%d')
    elif date_str in ["明後日", "あさって"]:
        return (now + timedelta(days=2)).strftime('%Y-%m-%d')
    
    # 「今週・来週の曜日」解析
    if "週の" in date_str:
        target_name = date_str[-1]
        if target_name in WEEKDAY_MAP:
            target_weekday = WEEKDAY_MAP[target_name]
            offset = 7 if "来週" in date_str else 0
            days_ahead = target_weekday - today_weekday + offset
            return (now + timedelta(days=days_ahead)).strftime('%Y-%m-%d')

    return date_str # 直接入力の場合

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

    def get_events(self, calendar_id, days=1):
        if not self.service: return []
        now = datetime.now(JST)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        time_max = (now + timedelta(days=days)).replace(hour=23, minute=59, second=59).isoformat()
        try:
            events_result = self.service.events().list(
                calendarId=calendar_id, timeMin=time_min, timeMax=time_max,
                singleEvents=True, orderBy='startTime'
            ).execute()
            return events_result.get('items', [])
        except: return []

    def add_event(self, calendar_id, title, date_str, start_time=None, end_time=None):
        if not self.service: return
        actual_date = parse_date_string(date_str)
        if start_time:
            s_dt = datetime.strptime(f"{actual_date} {start_time}", '%Y-%m-%d %H:%M').replace(tzinfo=JST)
            if end_time:
                e_dt = datetime.strptime(f"{actual_date} {end_time}", '%Y-%m-%d %H:%M').replace(tzinfo=JST)
                if e_dt <= s_dt: e_dt += timedelta(days=1) # 日またぎ対応
            else: e_dt = s_dt + timedelta(hours=1)
            event = {
                'summary': title,
                'start': {'dateTime': s_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
                'end': {'dateTime': e_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
            }
        else: # 終日
            s_date = datetime.strptime(actual_date, '%Y-%m-%d')
            event = {
                'summary': title,
                'start': {'date': s_date.strftime('%Y-%m-%d')},
                'end': {'date': (s_date + timedelta(days=1)).strftime('%Y-%m-%d')}
            }
        return self.service.events().insert(calendarId=calendar_id, body=event).execute()

# --- Utility: 表示整形 ---
def get_weather_forecast():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=35.6895&longitude=139.6917&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=Asia%2FTokyo"
        r = requests.get(url).json()
        forecast = {}
        for i in range(len(r['daily']['time'])):
            d = r['daily']['time'][i]
            forecast[d] = f"{WEATHER_CODES.get(r['daily']['weathercode'][i], '❓')} ({r['daily']['temperature_2m_max'][i]}℃/{r['daily']['temperature_2m_min'][i]}℃)"
        return forecast
    except: return {}

def format_event_list(events, weather_data, title_text):
    embed = discord.Embed(title=f"🗓️ {title_text}", color=0x4285F4)
    if not events:
        embed.description = "✨ 予定はありません。"
        return embed

    grouped = {}
    for e in events:
        d = e['start'].get('dateTime', e['start'].get('date'))[:10]
        if d not in grouped: grouped[d] = []
        grouped[d].append(e)

    for date_key, day_events in sorted(grouped.items()):
        dt = datetime.strptime(date_key, '%Y-%m-%d')
        weather = weather_data.get(date_key, "")
        field_name = f"📅 {dt.strftime('%m/%d')}({WEEKDAYS[dt.weekday()]}) {weather}"
        
        lines = []
        for e in day_events:
            st = e['start'].get('dateTime', e['start'].get('date'))
            time_tag = f"⏰ `{st[11:16]}`" if 'T' in st else "☀️ `終日`"
            # IDをラベルなしのコードブロックにしてコピーしやすく
            lines.append(f"{time_tag} **{e['summary']}**\n└ `{e['id']}`")
        
        embed.add_field(name=field_name, value="\n".join(lines) + "\n\u200b", inline=False)
    
    embed.set_footer(text="IDをコピーして /rem gcal_delete に貼り付けて削除できます")
    return embed

# --- Discord Commands ---
def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self):
            super().__init__(name="rem", description="Googleカレンダー連携・通知")

        @app_commands.command(name="on", description="通知設定をONにします")
        async def on(self, interaction: discord.Interaction, calendar_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            guild_data["google_calendar_id"] = calendar_id
            guild_data["reminder"] = {"enabled": True, "channel_id": interaction.channel_id}
            await data_manager.save_all()
            await interaction.response.send_message(f"✅ 設定完了！朝6時と予定の10分前に通知します。")

        @app_commands.command(name="gcal_add", description="予定を追加します")
        @app_commands.choices(date=[
            app_commands.Choice(name="今日", value="今日"),
            app_commands.Choice(name="明日", value="明日"),
            app_commands.Choice(name="明後日", value="明後日"),
            app_commands.Choice(name="今週の土曜日", value="今週の土"),
            app_commands.Choice(name="今週の日曜日", value="今週の日"),
            app_commands.Choice(name="来週の月曜日", value="来週の月"),
            app_commands.Choice(name="来週の金曜日", value="来週の金"),
            app_commands.Choice(name="来週の土曜日", value="来週の土"),
            app_commands.Choice(name="来週の日曜日", value="来週の日"),
        ])
        async def gcal_add(self, interaction: discord.Interaction, date: str, title: str, start_time: str = None, end_time: str = None):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cid = guild_data.get("google_calendar_id")
            if not cid: return await interaction.followup.send("❌ 先に /rem on でカレンダーIDを設定してください。")
            try:
                gcal.add_event(cid, title, date, start_time, end_time)
                await interaction.followup.send(f"✅ 登録しました: **{title}** ({date})")
            except: await interaction.followup.send("❌ 登録失敗。時刻は 14:00 の形式で入力してください。")

        @app_commands.command(name="gcal_list", description="予定を表示します")
        @app_commands.choices(duration=[
            app_commands.Choice(name="今日のみ", value=1),
            app_commands.Choice(name="明日まで", value=2),
            app_commands.Choice(name="1週間分", value=7),
        ])
        async def gcal_list(self, interaction: discord.Interaction, duration: int = 7):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cid = guild_data.get("google_calendar_id")
            if not cid: return await interaction.followup.send("❌ ID未設定")
            events = gcal.get_events(cid, days=duration)
            weather = get_weather_forecast()
            await interaction.followup.send(embed=format_event_list(events, weather, "予定リスト"))

        @app_commands.command(name="gcal_delete", description="予定を削除します")
        async def gcal_delete(self, interaction: discord.Interaction, event_id: str):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cid = guild_data.get("google_calendar_id")
            try:
                gcal.service.events().delete(calendarId=cid, eventId=event_id).execute()
                await interaction.followup.send("🗑️ 予定を削除しました。")
            except: await interaction.followup.send("❌ 削除失敗。IDを確認してください。")

    bot.tree.add_command(Reminder())

    # --- 通知ループ (朝6時 & 10分前) ---
    async def reminder_loop():
        await bot.wait_until_ready()
        last_reminded = set()
        while not bot.is_closed():
            now = datetime.now(JST)
            
            # 1. 朝6:00通知
            if now.hour == 6 and now.minute == 0:
                weather_map = get_weather_forecast()
                for gid, gdata in data_manager.data.items():
                    rem = gdata.get("reminder", {})
                    if rem.get("enabled"):
                        ch = bot.get_channel(rem.get("channel_id"))
                        cid = gdata.get("google_calendar_id")
                        if ch and cid:
                            events = gcal.get_events(cid, days=1)
                            await ch.send(embed=format_event_list(events, weather_map, "おはようございます！今日の予定"))
                await asyncio.sleep(60)

            # 2. 10分前リマインド
            for gid, gdata in data_manager.data.items():
                rem = gdata.get("reminder", {})
                if rem.get("enabled"):
                    ch = bot.get_channel(rem.get("channel_id"))
                    cid = gdata.get("google_calendar_id")
                    if ch and cid:
                        try:
                            events = gcal.get_events(cid, days=1)
                            for e in events:
                                st_raw = e['start'].get('dateTime')
                                if not st_raw: continue
                                st_dt = datetime.fromisoformat(st_raw.replace('Z', '+00:00')).astimezone(JST)
                                diff = (st_dt - now).total_seconds()
                                # 9分〜10分の間に通知
                                if 540 < diff <= 600 and e['id'] not in last_reminded:
                                    embed = discord.Embed(title="🕒 10分前リマインド", description=f"### {e['summary']}", color=0xff4757)
                                    embed.add_field(name="開始時刻", value=f"`{st_dt.strftime('%H:%M')}`")
                                    await ch.send(content="@everyone", embed=embed)
                                    last_reminded.add(e['id'])
                        except: pass
            
            if len(last_reminded) > 100: last_reminded.clear()
            await asyncio.sleep(30)

    if not hasattr(bot, "_reminder_loop_started"):
        bot._reminder_loop_started = True
        asyncio.create_task(reminder_loop())
