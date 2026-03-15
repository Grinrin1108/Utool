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

# JST タイムゾーン
JST = timezone(timedelta(hours=9))
SCOPES = ['https://www.googleapis.com/auth/calendar']
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

WEATHER_CODES = {
    0: "☀️快晴", 1: "🌤️晴れ", 2: "⛅くもり", 3: "☁️曇り",
    45: "🌫️霧", 48: "🌫️霧", 51: "🚿小雨", 53: "🚿小雨", 55: "🚿小雨",
    61: "☔雨", 63: "☔雨", 65: "☔激しい雨", 71: "❄️雪", 73: "❄️雪", 75: "❄️激しい雪",
    80: "🌦️にわか雨", 81: "🌦️にわか雨", 82: "🌦️激しいにわか雨", 95: "⚡雷雨"
}

# --- Utility: 日付文字列の解析 ---
def parse_date_string(date_str):
    """「明日」「明後日」などの文字列を YYYY-MM-DD 形式に変換する"""
    now = datetime.now(JST)
    if date_str in ["今日", "きょう", "today"]:
        return now.strftime('%Y-%m-%d')
    elif date_str in ["明日", "あした", "tomorrow"]:
        return (now + timedelta(days=1)).strftime('%Y-%m-%d')
    elif date_str in ["明後日", "あさって"]:
        return (now + timedelta(days=2)).strftime('%Y-%m-%d')
    elif date_str in ["明々後日", "しあさって"]:
        return (now + timedelta(days=3)).strftime('%Y-%m-%d')
    return date_str # それ以外はそのまま（2024-05-25等）を期待

# --- Google Calendar Manager ---
class GoogleCalendarManager:
    def __init__(self):
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            try:
                info = json.loads(creds_json)
                self.creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
                self.service = build('calendar', 'v3', credentials=self.creds)
            except Exception as e:
                print(f"Google Auth Error: {e}")
                self.service = None
        else:
            self.service = None

    def get_events(self, calendar_id, days=1, q=None):
        if not self.service: return []
        now = datetime.now(JST)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        search_days = 90 if q else days
        end_date = now + timedelta(days=search_days)
        time_max = end_date.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
        
        events_result = self.service.events().list(
            calendarId=calendar_id, timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy='startTime', q=q
        ).execute()
        return events_result.get('items', [])

    def add_event(self, calendar_id, title, date_str, start_time=None, end_time=None):
        if not self.service: raise Exception("Google API Service 未初期化")
        
        # 「明日」などを日付に変換
        actual_date = parse_date_string(date_str)
        
        if start_time:
            s_dt = datetime.strptime(f"{actual_date} {start_time}", '%Y-%m-%d %H:%M').replace(tzinfo=JST)
            if end_time:
                e_dt = datetime.strptime(f"{actual_date} {end_time}", '%Y-%m-%d %H:%M').replace(tzinfo=JST)
                if e_dt <= s_dt: # 日をまたぐ場合
                    e_dt += timedelta(days=1)
            else:
                e_dt = s_dt + timedelta(hours=1)
            event = {
                'summary': title,
                'start': {'dateTime': s_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
                'end': {'dateTime': e_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
            }
        else:
            s_date = datetime.strptime(actual_date, '%Y-%m-%d')
            e_date = s_date + timedelta(days=1)
            event = {
                'summary': title,
                'start': {'date': s_date.strftime('%Y-%m-%d')},
                'end': {'date': e_date.strftime('%Y-%m-%d')}
            }
        return self.service.events().insert(calendarId=calendar_id, body=event).execute()

    def delete_event(self, calendar_id, event_id):
        if not self.service: return None
        return self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

# --- Utility: 天気 & フォーマット ---
def get_weather_forecast():
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude=35.6895&longitude=139.6917&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=Asia%2FTokyo"
        r = requests.get(url).json()
        forecast = {}
        for i in range(len(r['daily']['time'])):
            date_str = r['daily']['time'][i]
            code = r['daily']['weathercode'][i]
            max_t = r['daily']['temperature_2m_max'][i]
            min_t = r['daily']['temperature_2m_min'][i]
            forecast[date_str] = f"{WEATHER_CODES.get(code, '❓')} ({max_t}℃/{min_t}℃)"
        return forecast
    except: return {}

def format_event_list(events, weather_data, title_text, color=0x4285F4):
    embed = discord.Embed(title=f"🗓️ {title_text}", color=color)
    if not events:
        embed.description = "✨ 予定はありません。ゆっくり休みましょう！"
        embed.color = 0x95a5a6
        return embed

    grouped_events = {}
    for e in events:
        start_raw = e['start'].get('dateTime', e['start'].get('date'))
        date_key = start_raw[:10]
        if date_key not in grouped_events: grouped_events[date_key] = []
        grouped_events[date_key].append(e)

    for date_key, day_events in sorted(grouped_events.items()):
        dt = datetime.strptime(date_key, '%Y-%m-%d')
        weekday = WEEKDAYS[dt.weekday()]
        weather = weather_data.get(date_key, "データなし")
        field_name = f"📅 {dt.strftime('%m月%d日')}({weekday}) ｜ {weather}"
        lines = []
        for e in day_events:
            start_raw = e['start'].get('dateTime', e['start'].get('date'))
            end_raw = e['end'].get('dateTime', e['end'].get('date'))
            if 'T' in start_raw:
                s_t = datetime.fromisoformat(start_raw.replace('Z', '+00:00')).astimezone(JST).strftime('%H:%M')
                e_t = datetime.fromisoformat(end_raw.replace('Z', '+00:00')).astimezone(JST).strftime('%H:%M')
                time_tag = f"⏰ `{s_t} - {e_t}`"
            else: time_tag = "☀️ ` 終日予定 `"
            lines.append(f"{time_tag}\n└ **{e['summary']}**\n　 `ID: {e['id']}`")
        embed.add_field(name=field_name, value="\n".join(lines) + "\n\u200b", inline=False)
    embed.set_footer(text="IDをコピーして /rem gcal_delete で削除可能")
    return embed

# --- Discord Commands ---
def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self):
            super().__init__(name="rem", description="Googleカレンダー連携")

        @app_commands.command(name="on", description="通知を有効にします")
        async def on(self, interaction: discord.Interaction, calendar_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            guild_data["google_calendar_id"] = calendar_id
            guild_data["reminder"] = {"enabled": True, "channel_id": interaction.channel_id}
            await data_manager.save_all()
            await interaction.response.send_message(f"✅ 設定完了！朝6時と10分前に通知します。")

        @app_commands.command(name="gcal_add", description="予定追加 (日付は「明日」等も可)")
        async def gcal_add(self, interaction: discord.Interaction, date: str, title: str, start_time: str = None, end_time: str = None):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            if not cal_id: return await interaction.response.send_message("❌ ID未設定")
            await interaction.response.defer()
            try:
                actual_date = parse_date_string(date)
                gcal.add_event(cal_id, title, actual_date, start_time, end_time)
                await interaction.followup.send(f"✅ 登録完了: **{title}** ({actual_date})")
            except:
                await interaction.followup.send("❌ 形式エラー (YYYY-MM-DD または 明日/明後日)")

        @app_commands.command(name="gcal_list", description="予定一覧表示")
        @app_commands.choices(duration=[
            app_commands.Choice(name="今日のみ", value=1),
            app_commands.Choice(name="明日まで", value=2),
            app_commands.Choice(name="1週間分", value=7),
            app_commands.Choice(name="1ヶ月分", value=30),
        ])
        async def gcal_list(self, interaction: discord.Interaction, duration: int = 7):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            if not cal_id: return await interaction.response.send_message("❌ ID未設定")
            await interaction.response.defer()
            events = gcal.get_events(cal_id, days=duration)
            weather = get_weather_forecast()
            await interaction.followup.send(embed=format_event_list(events, weather, f"予定リスト ({duration}日間)"))

        @app_commands.command(name="gcal_delete", description="予定削除")
        async def gcal_delete(self, interaction: discord.Interaction, event_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            await interaction.response.defer()
            try:
                gcal.delete_event(cal_id, event_id)
                await interaction.followup.send("🗑️ 削除しました。")
            except: await interaction.followup.send("❌ 削除失敗。")

    bot.tree.add_command(Reminder())

    # --- 通知ループ ---
    async def reminder_loop():
        await bot.wait_until_ready()
        last_reminded_ids = set()
        while not bot.is_closed():
            now = datetime.now(JST)
            # 朝6:00通知
            if now.hour == 6 and now.minute == 0:
                weather_map = get_weather_forecast()
                for g_id, g_data in data_manager.data.items():
                    rem = g_data.get("reminder", {})
                    if rem.get("enabled"):
                        channel = bot.get_channel(rem.get("channel_id"))
                        cal_id = g_data.get("google_calendar_id")
                        if channel and cal_id:
                            events = gcal.get_events(cal_id, days=1)
                            await channel.send(embed=format_event_list(events, weather_map, f"{now.strftime('%m/%d')}の予定"))
                await asyncio.sleep(60)

            # 10分前リマインド
            for g_id, g_data in data_manager.data.items():
                rem = g_data.get("reminder", {})
                if rem.get("enabled"):
                    channel = bot.get_channel(rem.get("channel_id"))
                    cal_id = g_data.get("google_calendar_id")
                    if channel and cal_id:
                        try:
                            events = gcal.get_events(cal_id, days=1)
                            for e in events:
                                st_val = e['start'].get('dateTime')
                                if not st_val: continue
                                st_dt = datetime.fromisoformat(st_val.replace('Z', '+00:00')).astimezone(JST)
                                diff = (st_dt - now).total_seconds()
                                if 540 < diff <= 600 and e['id'] not in last_reminded_ids:
                                    rem_embed = discord.Embed(title="🕒 10分前のリマインド", description=f"### **{e['summary']}**", color=0xff4757)
                                    rem_embed.add_field(name="開始時刻", value=f"`{st_dt.strftime('%H:%M')}`")
                                    await channel.send(content="@everyone", embed=rem_embed)
                                    last_reminded_ids.add(e['id'])
                        except: pass
            if len(last_reminded_ids) > 100: last_reminded_ids.clear()
            await asyncio.sleep(30)

    if not hasattr(bot, "_reminder_loop_started"):
        bot._reminder_loop_started = True
        asyncio.create_task(reminder_loop())
