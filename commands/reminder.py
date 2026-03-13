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

# 天気コードを日本語に変換する辞書 (Open-Meteo)
WEATHER_CODES = {
    0: "☀️ 快晴", 1: "🌤️ 晴れ", 2: "⛅ くもり", 3: "☁️ どんより曇り",
    45: "🌫️ 霧", 48: "🌫️ 霧", 51: "🚿 小雨", 53: "🚿 小雨", 55: "🚿 小雨",
    61: "☔ 雨", 63: "☔ 雨", 65: "☔ 激しい雨", 71: "❄️ 雪", 73: "❄️ 雪", 75: "❄️ 激しい雪",
    80: "🌦️ にわか雨", 81: "🌦️ にわか雨", 82: "🌦️ 激しいにわか雨", 95: "⚡ 雷雨"
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
        """予定取得 (検索キーワード q にも対応)"""
        if not self.service: return []
        now = datetime.now(JST)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_date = now + timedelta(days=days)
        time_max = end_date.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
        
        events_result = self.service.events().list(
            calendarId=calendar_id, timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy='startTime', q=q
        ).execute()
        return events_result.get('items', [])

    def add_event(self, calendar_id, title, date_str, time_str=None):
        if not self.service: raise Exception("Google API Service 未初期化")
        if time_str:
            dt_str = f"{date_str}T{time_str}:00"
            start_dt = datetime.fromisoformat(dt_str).replace(tzinfo=JST)
            end_dt = start_dt + timedelta(hours=1)
            event = {
                'summary': title,
                'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
                'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
            }
        else:
            event = {'summary': title, 'start': {'date': date_str}, 'end': {'date': date_str}}
        return self.service.events().insert(calendarId=calendar_id, body=event).execute()

    def delete_event(self, calendar_id, event_id):
        if not self.service: return None
        return self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

# --- Weather Utility ---
def get_weather():
    """東京の天気を取得 (Open-Meteo)"""
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=35.6895&longitude=139.6917&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=Asia%2FTokyo"
        r = requests.get(url).json()
        daily = r['daily']
        code = daily['weathercode'][0]
        max_t = daily['temperature_2m_max'][0]
        min_t = daily['temperature_2m_min'][0]
        return f"{WEATHER_CODES.get(code, '❓ 不明')} (最高:{max_t}℃ / 最低:{min_t}℃)"
    except:
        return None

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
        async def gcal_add(self, interaction: discord.Interaction, date: str, title: str, time: str = None):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            await interaction.response.defer()
            try:
                res = gcal.add_event(cal_id, title, date, time)
                embed = discord.Embed(title="📅 予定を追加しました", color=0x4285F4)
                embed.add_field(name="内容", value=title, inline=False)
                embed.add_field(name="日時", value=f"{date} {time if time else '(終日)'}", inline=True)
                if res.get('htmlLink'):
                    embed.add_field(name="リンク", value=f"[カレンダー表示]({res['htmlLink']})", inline=True)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await interaction.followup.send(f"❌ エラー: {e}")

        @app_commands.command(name="gcal_list", description="予定表示")
        @app_commands.choices(duration=[
            app_commands.Choice(name="今日", value=1),
            app_commands.Choice(name="今後1週間", value=7),
            app_commands.Choice(name="今後1ヶ月", value=30),
        ])
        async def gcal_list(self, interaction: discord.Interaction, duration: int = 1):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            await interaction.response.defer()
            try:
                events = gcal.get_events(cal_id, days=duration)
                embed = discord.Embed(title=f"📅 予定リスト ({duration}日間)", color=0x4285F4)
                if not events:
                    embed.description = "予定はありません。"
                for e in events:
                    start = e['start'].get('dateTime', e['start'].get('date'))
                    dt = datetime.fromisoformat(start.replace('Z', '+00:00')).astimezone(JST) if 'T' in start else datetime.strptime(start, '%Y-%m-%d')
                    time_str = dt.strftime(f'%m/%d({WEEKDAYS[dt.weekday()]}) %H:%M') if 'T' in start else dt.strftime(f'%m/%d({WEEKDAYS[dt.weekday()]}) (終日)')
                    embed.add_field(name=f"{time_str} | {e['summary']}", value=f"ID: `{e['id']}`", inline=False)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await interaction.followup.send(f"❌ 取得エラー: {e}")

        @app_commands.command(name="gcal_search", description="キーワードで予定を検索")
        async def gcal_search(self, interaction: discord.Interaction, keyword: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            await interaction.response.defer()
            try:
                # 今後90日間の中からキーワード検索
                events = gcal.get_events(cal_id, days=90, q=keyword)
                embed = discord.Embed(title=f"🔍 検索結果: {keyword}", color=0xF4B400)
                if not events:
                    embed.description = "一致する予定は見つかりませんでした。"
                for e in events[:10]: # 最大10件表示
                    start = e['start'].get('dateTime', e['start'].get('date'))
                    embed.add_field(name=f"{start[:10]} | {e['summary']}", value=f"ID: `{e['id']}`", inline=False)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await interaction.followup.send(f"❌ 検索エラー: {e}")

        @app_commands.command(name="gcal_delete", description="予定削除")
        async def gcal_delete(self, interaction: discord.Interaction, event_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            await interaction.response.defer()
            try:
                gcal.delete_event(cal_id, event_id)
                await interaction.followup.send(f"✅ 削除しました。")
            except:
                await interaction.followup.send(f"❌ 削除失敗。")

    bot.tree.add_command(Reminder())

    # --- バックグラウンド通知ループ ---
    async def reminder_loop():
        await bot.wait_until_ready()
        while not bot.is_closed():
            now = datetime.now(JST).replace(second=0, microsecond=0)
            if now.hour == 8 and now.minute == 0:
                weather_info = get_weather()
                for guild in bot.guilds:
                    guild_data = data_manager.get_guild_data(guild.id)
                    rem = guild_data.get("reminder", {})
                    if rem.get("enabled"):
                        channel = bot.get_channel(rem.get("channel_id"))
                        cal_id = guild_data.get("google_calendar_id")
                        if channel and cal_id:
                            try:
                                events = gcal.get_events(cal_id, days=1)
                                embed = discord.Embed(title="☀️ おはようございます！", color=0x4285F4)
                                if weather_info:
                                    embed.add_field(name="今日の天気", value=weather_info, inline=False)
                                
                                if events:
                                    lines = []
                                    for e in events:
                                        st = e['start'].get('dateTime', e['start'].get('date'))
                                        time_label = st.split('T')[1][:5] if 'T' in st else "終日"
                                        lines.append(f"・`{time_label}` {e['summary']}")
                                    embed.add_field(name="今日の予定", value="\n".join(lines), inline=False)
                                else:
                                    embed.add_field(name="今日の予定", value="予定はありません。", inline=False)
                                await channel.send(embed=embed)
                            except: pass
            await asyncio.sleep(55)

    if not hasattr(bot, "_reminder_loop_started"):
        bot._reminder_loop_started = True
        asyncio.create_task(reminder_loop())