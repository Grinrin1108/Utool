# commands/reminder.py
from discord import app_commands
import discord
import asyncio
import os
import json
from datetime import datetime, timezone, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

# JST タイムゾーン
JST = timezone(timedelta(hours=9))
SCOPES = ['https://www.googleapis.com/auth/calendar']

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

    def get_events(self, calendar_id, days=1):
        """指定された日数分の予定を取得"""
        if not self.service: return []
        now = datetime.now(JST)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        # 終了日を設定
        end_date = now + timedelta(days=days-1)
        time_max = end_date.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
        
        events_result = self.service.events().list(
            calendarId=calendar_id, timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy='startTime'
        ).execute()
        return events_result.get('items', [])

    def add_event(self, calendar_id, title, date_str, time_str):
        if not self.service: 
            raise Exception("Google API Service が初期化されていません。")
        
        dt_str = f"{date_str}T{time_str}:00"
        start_dt = datetime.fromisoformat(dt_str).replace(tzinfo=JST)
        end_dt = start_dt + timedelta(hours=1)

        event = {
            'summary': title,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
        }
        return self.service.events().insert(calendarId=calendar_id, body=event).execute()

    def delete_event(self, calendar_id, event_id):
        if not self.service: return None
        return self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

# --- Discord Commands ---
def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self):
            super().__init__(name="rem", description="リマインダー・Googleカレンダー管理")

        @app_commands.command(name="status", description="設定状態を表示")
        async def status(self, interaction: discord.Interaction):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            rem = guild_data.get("reminder", {})
            enabled = rem.get("enabled", False)
            channel = interaction.guild.get_channel(rem.get("channel_id")) if rem.get("channel_id") else None
            txt = (
                f"状態: **{'有効' if enabled else '無効'}**\n"
                f"チャンネル: {channel.mention if channel else '未設定'}\n"
                f"通知タイミング: {rem.get('notify_minutes', 5)} 分前\n"
                f"GoogleカレンダーID: `{guild_data.get('google_calendar_id', '未設定')}`"
            )
            await interaction.response.send_message(txt, ephemeral=True)

        # --- Google Calendar コマンド ---
        @app_commands.command(name="gcal_set", description="GoogleカレンダーIDを設定")
        async def gcal_set(self, interaction: discord.Interaction, calendar_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            guild_data["google_calendar_id"] = calendar_id
            await data_manager.save_all()
            await interaction.response.send_message(f"✅ カレンダーIDを設定しました")

        @app_commands.command(name="gcal_add", description="Googleカレンダーに予定追加")
        async def gcal_add(self, interaction: discord.Interaction, date: str, time: str, title: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            if not cal_id:
                await interaction.response.send_message("❌ IDが未設定です。")
                return
            
            await interaction.response.defer()
            try:
                res = gcal.add_event(cal_id, title, date, time)
                url = res.get('htmlLink')
                
                embed = discord.Embed(title="📅 予定を追加しました", color=0x4285F4)
                embed.add_field(name="内容", value=title, inline=False)
                embed.add_field(name="日時", value=f"{date} {time}", inline=True)
                if url:
                    embed.add_field(name="リンク", value=f"[Googleカレンダーで確認]({url})", inline=True)
                
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await interaction.followup.send(f"❌ 追加エラー: {e}")

        @app_commands.command(name="gcal_list", description="Googleカレンダーの予定を表示")
        @app_commands.choices(duration=[
            app_commands.Choice(name="今日", value=1),
            app_commands.Choice(name="今後1週間", value=7),
            app_commands.Choice(name="今後1ヶ月 (30日間)", value=30),
        ])
        async def gcal_list(self, interaction: discord.Interaction, duration: int = 1):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            if not cal_id:
                await interaction.response.send_message("❌ IDが未設定です。")
                return

            await interaction.response.defer()
            try:
                events = gcal.get_events(cal_id, days=duration)
                
                title_text = "今日の予定" if duration == 1 else f"今後 {duration} 日間の予定"
                embed = discord.Embed(title=f"📅 {title_text}", color=0x4285F4)

                if not events:
                    embed.description = "予定は見つかりませんでした。"
                else:
                    for event in events:
                        start = event['start'].get('dateTime', event['start'].get('date'))
                        # 日付と時間の表示を整える
                        if 'T' in start:
                            dt = datetime.fromisoformat(start).astimezone(JST)
                            time_str = dt.strftime('%m/%d %H:%M')
                        else:
                            time_str = f"{start} (終日)"
                        
                        embed.add_field(
                            name=f"{time_str} | {event['summary']}",
                            value=f"ID: `{event['id']}`",
                            inline=False
                        )

                await interaction.followup.send(embed=embed)
            except Exception as e:
                await interaction.followup.send(f"❌ 取得エラー: {e}")

        @app_commands.command(name="gcal_delete", description="予定を削除")
        async def gcal_delete(self, interaction: discord.Interaction, event_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            await interaction.response.defer()
            try:
                gcal.delete_event(cal_id, event_id)
                await interaction.followup.send(f"✅ 予定を削除しました。")
            except Exception as e:
                await interaction.followup.send(f"❌ 削除失敗: IDを確認してください。")

    bot.tree.add_command(Reminder())

    # --- バックグラウンド通知ループ ---
    async def reminder_loop():
        await bot.wait_until_ready()
        while not bot.is_closed():
            now = datetime.now(JST).replace(second=0, microsecond=0)
            # 毎朝8時の通知
            if now.hour == 8 and now.minute == 0:
                for guild in bot.guilds:
                    guild_data = data_manager.get_guild_data(guild.id)
                    rem = guild_data.get("reminder", {})
                    if rem.get("enabled"):
                        channel = bot.get_channel(rem.get("channel_id"))
                        cal_id = guild_data.get("google_calendar_id")
                        if channel and cal_id:
                            try:
                                events = gcal.get_events(cal_id, days=1)
                                if events:
                                    embed = discord.Embed(title="☀️ おはようございます！今日の予定です", color=0x4285F4)
                                    for e in events:
                                        st = e['start'].get('dateTime', '終日')
                                        if 'T' in st: st = st.split('T')[1][:5]
                                        embed.add_field(name=st, value=e['summary'], inline=False)
                                    await channel.send(embed=embed)
                            except: pass
            await asyncio.sleep(55)

    if not hasattr(bot, "_reminder_loop_started"):
        bot._reminder_loop_started = True
        asyncio.create_task(reminder_loop())