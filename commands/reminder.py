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
        # 10分前通知のために、少し余裕を持って取得
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
            forecast[date_str] = f"{WEATHER_CODES.get(code, '❓')} ({max_t}℃/{min_t}℃)"
        return forecast
    except:
        return {}

def format_event_list(events, weather_data, title_text, color=0x4285F4):
    embed = discord.Embed(title=f"🗓️ {title_text}", color=color)
    if not events:
        embed.description = "✨ 予定はありません。ゆっくり休みましょう！"
        embed.color = 0x95a5a6
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
        weather = weather_data.get(date_key, "データなし")
        field_name = f"📅 {dt.strftime('%m月%d日')}({weekday}) ｜ {weather}"
        
        lines = []
        for e in day_events:
            start_val = e['start'].get('dateTime', e['start'].get('date'))
            if 'T' in start_val:
                s_t = datetime.fromisoformat(start_val.replace('Z', '+00:00')).astimezone(JST).strftime('%H:%M')
                time_tag = f"⏰ `{s_t}`"
            else:
                time_tag = "☀️ ` 終日 `"
            lines.append(f"{time_tag} **{e['summary']}**\n　 `ID: {e['id']}`")
        embed.add_field(name=field_name, value="\n".join(lines) + "\n\u200b", inline=False)
    
    embed.set_footer(text="IDをコピーして /rem gcal_delete で削除できます")
    return embed

# --- Discord Commands ---
def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self):
            super().__init__(name="rem", description="Googleカレンダー連携・通知設定")

        @app_commands.command(name="on", description="このチャンネルで通知を有効にします")
        async def on(self, interaction: discord.Interaction, calendar_id: str):
            guild_id = interaction.guild_id
            guild_data = data_manager.get_guild_data(guild_id)
            guild_data["google_calendar_id"] = calendar_id
            guild_data["reminder"] = {"enabled": True, "channel_id": interaction.channel_id}
            await data_manager.save_all()
            await interaction.response.send_message(f"✅ 通知設定をONにしました！\n・毎朝6:00に今日の予定\n・各予定の10分前にリマインド\nをお届けします。")

        @app_commands.command(name="off", description="通知を無効にします")
        async def off(self, interaction: discord.Interaction):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            if "reminder" in guild_data:
                guild_data["reminder"]["enabled"] = False
                await data_manager.save_all()
                await interaction.response.send_message("📴 全ての通知を停止しました。")

        @app_commands.command(name="status", description="設定確認")
        async def status(self, interaction: discord.Interaction):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            rem = guild_data.get("reminder", {})
            embed = discord.Embed(title="⚙️ 設定ステータス", color=0x3498db)
            status_val = "✅ 有効 (朝6時 & 10分前)" if rem.get("enabled") else "❌ 無効"
            embed.add_field(name="通知状態", value=status_val, inline=True)
            embed.add_field(name="通知先", value=f"<#{rem.get('channel_id')}>" if rem.get('channel_id') else "未設定")
            embed.add_field(name="カレンダーID", value=f"`{guild_data.get('google_calendar_id', '未設定')}`", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @app_commands.command(name="gcal_add", description="予定追加")
        async def gcal_add(self, interaction: discord.Interaction, date: str, title: str, start_time: str = None, end_time: str = None):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            if not cal_id: return await interaction.response.send_message("❌ ID未設定")
            await interaction.response.defer()
            try:
                gcal.add_event(cal_id, title, date, start_time, end_time)
                await interaction.followup.send(f"✅ 予定を登録しました: **{title}**")
            except:
                await interaction.followup.send("❌ 形式エラー")

        @app_commands.command(name="gcal_list", description="予定表示")
        async def gcal_list(self, interaction: discord.Interaction, duration: int = 7):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            if not cal_id: return await interaction.response.send_message("❌ ID未設定")
            await interaction.response.defer()
            events = gcal.get_events(cal_id, days=duration)
            weather = get_weather_forecast()
            await interaction.followup.send(embed=format_event_list(events, weather, f"予定リスト"))

        @app_commands.command(name="gcal_delete", description="予定削除")
        async def gcal_delete(self, interaction: discord.Interaction, event_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            await interaction.response.defer()
            try:
                gcal.delete_event(cal_id, event_id)
                await interaction.followup.send("🗑️ 削除しました。")
            except:
                await interaction.followup.send("❌ 削除失敗。")

    bot.tree.add_command(Reminder())

    # --- 通知ループ ---
    async def reminder_loop():
        await bot.wait_until_ready()
        print("⏰ Reminder loop (06:00 & 10min) started.")
        last_reminded_ids = set() # 二重通知防止

        while not bot.is_closed():
            now = datetime.now(JST)
            
            # 1. 毎朝6:00の定期通知
            if now.hour == 6 and now.minute == 0:
                weather_map = get_weather_forecast()
                for guild_id, guild_data in data_manager.data.items():
                    rem = guild_data.get("reminder", {})
                    if rem.get("enabled"):
                        channel = bot.get_channel(rem.get("channel_id"))
                        cal_id = guild_data.get("google_calendar_id")
                        if channel and cal_id:
                            events = gcal.get_events(cal_id, days=1)
                            embed = format_event_list(events, weather_map, f"おはようございます！ {now.strftime('%m/%d')}の予定")
                            await channel.send(embed=embed)
                await asyncio.sleep(60)

            # 2. 10分前の個別リマインド
            for guild_id, guild_data in data_manager.data.items():
                rem = guild_data.get("reminder", {})
                if rem.get("enabled"):
                    channel = bot.get_channel(rem.get("channel_id"))
                    cal_id = guild_data.get("google_calendar_id")
                    if channel and cal_id:
                        try:
                            # 予定をチェック
                            events = gcal.get_events(cal_id, days=1)
                            for e in events:
                                start_val = e['start'].get('dateTime')
                                if not start_val: continue # 終日予定は除外
                                
                                start_dt = datetime.fromisoformat(start_val.replace('Z', '+00:00')).astimezone(JST)
                                # 今から「10分〜11分後」に始まる予定かチェック
                                diff = (start_dt - now).total_seconds()
                                if 540 < diff <= 600 and e['id'] not in last_reminded_ids:
                                    # 10分前リマインドEmbed
                                    rem_embed = discord.Embed(
                                        title="🕒 まもなく予定の時間です (10分前)",
                                        description=f"### **{e['summary']}**",
                                        color=0xff4757 # 赤系で注意を引く
                                    )
                                    rem_embed.add_field(name="開始時刻", value=f"`{start_dt.strftime('%H:%M')}`", inline=True)
                                    rem_embed.set_footer(text="準備は大丈夫ですか？")
                                    
                                    await channel.send(content="@everyone", embed=rem_embed)
                                    last_reminded_ids.add(e['id'])
                        except: pass

            # 過去のリマインドIDを整理（24時間以上前のものは削除）
            if len(last_reminded_ids) > 100: last_reminded_ids.clear()
            
            await asyncio.sleep(30) # 30秒ごとにチェック

    if not hasattr(bot, "_reminder_loop_started"):
        bot._reminder_loop_started = True
        asyncio.create_task(reminder_loop())