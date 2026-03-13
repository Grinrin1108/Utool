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
# 権限スコープ（タイポを修正済み）
SCOPES = ['https://www.googleapis.com/auth/calendar']
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

WEATHER_CODES = {
    0: "☀️快晴", 1: "🌤️晴れ", 2: "⛅くもり", 3: "☁️曇り",
    45: "🌫️霧", 48: "🌫️霧", 51: "🚿小雨", 53: "🚿小雨", 55: "🚿小雨",
    61: "☔雨", 63: "☔雨", 65: "☔激しい雨", 71: "❄️雪", 73: "❄️雪", 75: "❄️激しい雪",
    80: "🌦️にわか雨", 81: "🌦️にわか雨", 82: "🌦️激しいにわか雨", 95: "⚡雷雨"
}

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
        # 検索(q)がある場合は長めの期間(90日)をデフォルトにする
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

# --- Utility ---
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
    """予定リストのEmbedを生成する共通関数"""
    embed = discord.Embed(title=title_text, color=0x4285F4)
    if not events:
        embed.description = "該当する予定はありません。"
        return embed

    # 日付ごとにグループ化
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
        
        # 見出し
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
            
            # IDをインラインコードブロックにして、コピーしやすくする
            # 前後の [🔗ID](url) を削除し、IDそのものを表示
            lines.append(f"{time_label} **{e['summary']}**\nID: `{e['id']}`")
        
        # 予定と予定の間、および日付グループの間に余白を追加
        embed.add_field(name=field_name, value="\n".join(lines) + "\n\u200b", inline=False)
    
    return embed

# --- Discord Commands ---
def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self):
            super().__init__(name="rem", description="管理コマンド")

        @app_commands.command(name="status", description="設定確認")
        async def status(self, interaction: discord.Interaction):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            rem = guild_data.get("reminder", {})
            txt = f"状態: **{'有効' if rem.get('enabled') else '無効'}**\nカレンダーID: `{guild_data.get('google_calendar_id', '未設定')}`"
            await interaction.response.send_message(txt, ephemeral=True)

        @app_commands.command(name="gcal_add", description="予定追加")
        async def gcal_add(self, interaction: discord.Interaction, date: str, title: str, start_time: str = None, end_time: str = None):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            if not cal_id: return await interaction.response.send_message("❌ ID未設定")
            
            await interaction.response.defer()
            try:
                res = gcal.add_event(cal_id, title, date, start_time, end_time)
                dt_obj = datetime.strptime(date, '%Y-%m-%d')
                weekday = WEEKDAYS[dt_obj.weekday()]
                embed = discord.Embed(title="✅ 予定を追加しました", color=0x4285F4)
                embed.add_field(name="内容", value=title, inline=False)
                t_display = f"{start_time} - {end_time if end_time else '(+1h)'}" if start_time else "(終日)"
                embed.add_field(name="日時", value=f"{date}({weekday}) {t_display}", inline=True)
                if res.get('htmlLink'):
                    embed.add_field(name="Link", value=f"[Calendar]({res['htmlLink']})", inline=True)
                await interaction.followup.send(embed=embed)
            except Exception:
                await interaction.followup.send("❌ 入力形式エラー")

        @app_commands.command(name="gcal_list", description="予定表示")
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
            try:
                events = gcal.get_events(cal_id, days=duration)
                weather_data = get_weather_forecast()
                title = f"📅 スケジュール集計 ({duration}日間)"
                embed = format_event_list(events, weather_data, title)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await interaction.followup.send(f"❌ エラー: {e}")

        @app_commands.command(name="gcal_search", description="予定を検索")
        async def gcal_search(self, interaction: discord.Interaction, keyword: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            if not cal_id: return await interaction.response.send_message("❌ ID未設定")
            await interaction.response.defer()
            try:
                # 90日間の中から検索
                events = gcal.get_events(cal_id, q=keyword)
                weather_data = get_weather_forecast()
                title = f"🔍 検索結果: {keyword}"
                embed = format_event_list(events, weather_data, title)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await interaction.followup.send(f"❌ 検索エラー")

        @app_commands.command(name="gcal_delete", description="予定削除")
        async def gcal_delete(self, interaction: discord.Interaction, event_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            await interaction.response.defer()
            try:
                gcal.delete_event(cal_id, event_id)
                await interaction.followup.send("✅ 削除しました。")
            except:
                await interaction.followup.send("❌ 削除失敗。")

    bot.tree.add_command(Reminder())

    # --- 通知ループ ---
    async def reminder_loop():
        await bot.wait_until_ready()
        while not bot.is_closed():
            now = datetime.now(JST).replace(second=0, microsecond=0)
            if now.hour == 8 and now.minute == 0:
                weather_map = get_weather_forecast()
                today_str = now.strftime('%Y-%m-%d')
                for guild in bot.guilds:
                    guild_data = data_manager.get_guild_data(guild.id)
                    rem = guild_data.get("reminder", {})
                    if rem.get("enabled"):
                        channel = bot.get_channel(rem.get("channel_id"))
                        cal_id = guild_data.get("google_calendar_id")
                        if channel and cal_id:
                            try:
                                events = gcal.get_events(cal_id, days=1)
                                weather = weather_map.get(today_str, "")
                                embed = discord.Embed(title=f"☀️ {now.strftime('%m/%d')}({WEEKDAYS[now.weekday()]}) の予定", color=0x4285F4)
                                if weather: embed.description = f"今日の天気: **{weather}**"
                                if events:
                                    lines = []
                                    for e in events:
                                        st = e['start'].get('dateTime', e['start'].get('date'))
                                        time_label = st.split('T')[1][:5] if 'T' in st else "終日"
                                        lines.append(f"・`{time_label}` {e['summary']}")
                                    embed.add_field(name="予定一覧", value="\n".join(lines))
                                else:
                                    embed.add_field(name="予定一覧", value="予定はありません。")
                                await channel.send(embed=embed)
                            except: pass
            await asyncio.sleep(55)

    if not hasattr(bot, "_reminder_loop_started"):
        bot._reminder_loop_started = True
        asyncio.create_task(reminder_loop())