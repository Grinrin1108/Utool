from discord import app_commands
import discord
import asyncio
import os
import json
import requests
from datetime import datetime, timezone, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

JST = timezone(timedelta(hours=9))
SCOPES = ['https://www.googleapis.com/auth/calendar']
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

WEATHER_CODES = {
    0: "☀️快晴", 1: "🌤️晴れ", 2: "⛅くもり", 3: "☁️曇り",
    45: "🌫️霧", 48: "🌫️霧", 51: "🚿小雨", 53: "🚿小雨", 55: "🚿小雨",
    61: "☔雨", 63: "☔雨", 65: "☔激しい雨", 71: "❄️雪", 73: "❄️雪", 75: "❄️激しい雪",
    80: "🌦️にわか雨", 81: "🌦️にわか雨", 82: "🌦️激しいにわか雨", 95: "⚡雷雨"
}

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
        if start_time:
            s_dt = datetime.fromisoformat(f"{date_str}T{start_time}:00").replace(tzinfo=JST)
            e_dt = datetime.fromisoformat(f"{date_str}T{end_time}:00").replace(tzinfo=JST) if end_time else s_dt + timedelta(hours=1)
            event = {
                'summary': title,
                'start': {'dateTime': s_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
                'end': {'dateTime': e_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
            }
        else:
            event = {'summary': title, 'start': {'date': date_str}, 'end': {'date': date_str}}
        return self.service.events().insert(calendarId=calendar_id, body=event).execute()

    def delete_event(self, calendar_id, event_id):
        if not self.service: return None
        return self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

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
            forecast[date_str] = f"{WEATHER_CODES.get(code, '不明')} ({max_t}℃/{min_t}℃)"
        return forecast
    except:
        return {}

def format_event_list(events, weather_data, title_text):
    embed = discord.Embed(title=title_text, color=0x4285F4)
    if not events:
        embed.description = "該当する予定はありません。"
        return embed

    grouped_events = {}
    for e in events:
        start_val = e['start'].get('dateTime', e['start'].get('date'))
        date_key = start_val[:10]
        if date_key not in grouped_events:
            grouped_events[date_key] = []
        grouped_events[date_key].append(e)

    for date_key, day_events in grouped_events.items():
        dt = datetime.strptime(date_key, '%Y-%m-%d')
        weekday = WEEKDAYS[dt.weekday()]
        weather = weather_data.get(date_key, "")
        field_name = f"─── {dt.strftime('%m/%d')}({weekday}) {weather} ───"
        
        lines = []
        for e in day_events:
            start_val = e['start'].get('dateTime', e['start'].get('date'))
            end_val = e['end'].get('dateTime', e['end'].get('date'))
            if 'T' in start_val:
                s_t = datetime.fromisoformat(start_val.replace('Z', '+00:00')).astimezone(JST).strftime('%H:%M')
                e_t = datetime.fromisoformat(end_val.replace('Z', '+00:00')).astimezone(JST).strftime('%H:%M')
                time_label = f"`{s_t}-{e_t}`"
            else:
                time_label = "`終日`"
            lines.append(f"{time_label} **{e['summary']}**\nID: `{e['id']}`")
        
        embed.add_field(name=field_name, value="\n".join(lines) + "\n\u200b", inline=False)
    return embed

def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self):
            super().__init__(name="rem", description="Googleカレンダー連携")

        @app_commands.command(name="status", description="設定状態を確認")
        async def status(self, interaction: discord.Interaction):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            rem = guild_data.get("reminder", {})
            txt = f"通知: **{'有効' if rem.get('enabled') else '無効'}**\nカレンダーID: `{guild_data.get('google_calendar_id', '未設定')}`"
            await interaction.response.send_message(txt, ephemeral=True)

        @app_commands.command(name="gcal_add", description="予定を追加")
        async def gcal_add(self, interaction: discord.Interaction, date: str, title: str, start_time: str = None, end_time: str = None):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            if not cal_id: return await interaction.response.send_message("❌ 先に `/rem setup` でIDを設定してください")
            await interaction.response.defer()
            try:
                gcal.add_event(cal_id, title, date, start_time, end_time)
                await interaction.followup.send(f"✅ 追加完了: {title}")
            except:
                await interaction.followup.send("❌ 形式エラー (YYYY-MM-DD)")

        @app_commands.command(name="gcal_list", description="予定を表示")
        @app_commands.choices(duration=[
            app_commands.Choice(name="今日", value=1),
            app_commands.Choice(name="1週間", value=7),
            app_commands.Choice(name="1ヶ月", value=30),
        ])
        async def gcal_list(self, interaction: discord.Interaction, duration: int = 1):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            if not cal_id: return await interaction.response.send_message("❌ ID未設定")
            await interaction.response.defer()
            events = gcal.get_events(cal_id, days=duration)
            weather = get_weather_forecast()
            await interaction.followup.send(embed=format_event_list(events, weather, f"📅 予定リスト ({duration}日間)"))

        @app_commands.command(name="gcal_search", description="予定を検索")
        async def gcal_search(self, interaction: discord.Interaction, keyword: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            await interaction.response.defer()
            events = gcal.get_events(cal_id, q=keyword)
            weather = get_weather_forecast()
            await interaction.followup.send(embed=format_event_list(events, weather, f"🔍 検索: {keyword}"))

        @app_commands.command(name="gcal_delete", description="予定を削除")
        async def gcal_delete(self, interaction: discord.Interaction, event_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            await interaction.response.defer()
            try:
                gcal.delete_event(cal_id, event_id)
                await interaction.followup.send("✅ 削除しました。")
            except:
                await interaction.followup.send("❌ 失敗。IDを確認してください。")

    bot.tree.add_command(Reminder())

    async def reminder_loop():
        await bot.wait_until_ready()
        while not bot.is_closed():
            now = datetime.now(JST)
            if now.hour == 8 and now.minute == 0:
                weather_map = get_weather_forecast()
                for guild in bot.guilds:
                    guild_data = data_manager.get_guild_data(guild.id)
                    rem = guild_data.get("reminder", {})
                    if rem.get("enabled"):
                        channel = bot.get_channel(rem.get("channel_id"))
                        cal_id = guild_data.get("google_calendar_id")
                        if channel and cal_id:
                            events = gcal.get_events(cal_id, days=1)
                            weather = weather_map.get(now.strftime('%Y-%m-%d'), "")
                            embed = discord.Embed(title=f"☀️ {now.strftime('%m/%d')} の予定", color=0x4285F4)
                            if weather: embed.description = f"天気: **{weather}**"
                            lines = [f"・`{e['start'].get('dateTime', '終日')[11:16]}` {e['summary']}" for e in events] if events else ["予定なし"]
                            embed.add_field(name="一覧", value="\n".join(lines))
                            await channel.send(embed=embed)
            await asyncio.sleep(60)
    
    if not hasattr(bot, "_reminder_loop_started"):
        bot._reminder_loop_started = True
        asyncio.create_task(reminder_loop())