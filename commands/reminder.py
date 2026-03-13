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

    def get_todays_events(self, calendar_id):
        if not self.service: return []
        now = datetime.now(JST)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        time_max = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
        
        events_result = self.service.events().list(
            calendarId=calendar_id, timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy='startTime'
        ).execute()
        return events_result.get('items', [])

    def add_event(self, calendar_id, title, date_str, time_str):
        if not self.service: return None
        dt_str = f"{date_str}T{time_str}:00"
        # タイムゾーン込みでパース
        start_dt = datetime.fromisoformat(dt_str).replace(tzinfo=JST)
        end_dt = start_dt + timedelta(hours=1)

        event = {
            'summary': title,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
        }
        return self.service.events().insert(calendarId=calendar_id, body=event).execute()

# --- Discord Commands ---
def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self):
            super().__init__(name="rem", description="リマインダー・Googleカレンダー管理")

        @app_commands.command(name="on", description="予定アナウンスを有効化")
        async def on(self, interaction: discord.Interaction):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            rem = guild_data.setdefault("reminder", {})
            rem.setdefault("notify_minutes", 5)
            rem["enabled"] = True
            rem["channel_id"] = interaction.channel.id
            await data_manager.save_all()
            await interaction.response.send_message("✅ 予定アナウンスを有効化しました。")

        @app_commands.command(name="off", description="予定アナウンスを無効化")
        async def off(self, interaction: discord.Interaction):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            rem = guild_data.setdefault("reminder", {})
            rem["enabled"] = False
            await data_manager.save_all()
            await interaction.response.send_message("🛑 予定アナウンスを無効化しました。")

        @app_commands.command(name="status", description="アナウンスの状態を表示")
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

        @app_commands.command(name="timer", description="タイマーを設定 (例: 10s / 5m / 1h)")
        async def timer(self, interaction: discord.Interaction, time_str: str, message: str):
            await interaction.response.defer(ephemeral=True)
            try:
                amount = int(time_str[:-1])
                unit = time_str[-1].lower()
                seconds = {"s": amount, "m": amount*60, "h": amount*3600}[unit]
            except:
                await interaction.followup.send("❌ 形式が違います。例: 10s / 5m / 1h", ephemeral=True)
                return
            await interaction.followup.send(f"⏰ リマインダーをセットしました: {message}", ephemeral=True)
            await asyncio.sleep(seconds)
            await interaction.channel.send(f"{interaction.user.mention} ⏰ 時間です: {message}")

        @app_commands.command(name="daily", description="毎日リマインダー設定 (例: 21:00)")
        async def daily(self, interaction: discord.Interaction, time_str: str, message: str):
            try:
                hr, mn = map(int, time_str.split(":"))
                if not (0 <= hr < 24 and 0 <= mn < 60): raise ValueError
            except:
                await interaction.response.send_message("❌ 時刻形式が不正です。HH:MM で入力してください。", ephemeral=True)
                return
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            reminders = guild_data.setdefault("daily_reminders", [])
            reminders.append({"time": time_str, "message": message, "channel_id": interaction.channel.id})
            await data_manager.save_all()
            await interaction.response.send_message(f"✅ 毎日 {time_str} に通知します: {message}")

        @app_commands.command(name="weekly", description="毎週リマインダー設定 (例: 月 09:00)")
        async def weekly(self, interaction: discord.Interaction, weekday: str, time_str: str, message: str):
            weekdays = ["月","火","水","木","金","土","日"]
            if weekday not in weekdays:
                await interaction.response.send_message("❌ 曜日が不正です。", ephemeral=True)
                return
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            reminders = guild_data.setdefault("weekly_reminders", [])
            reminders.append({"weekday": weekday, "time": time_str, "message": message, "channel_id": interaction.channel.id})
            await data_manager.save_all()
            await interaction.response.send_message(f"✅ 毎週 {weekday}曜 {time_str} に通知します: {message}")

        @app_commands.command(name="list", description="定期リマインダー一覧")
        async def list_reminders(self, interaction: discord.Interaction):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            daily = guild_data.get("daily_reminders", [])
            weekly = guild_data.get("weekly_reminders", [])
            embed = discord.Embed(title="定期リマインダー一覧", color=0x00ff99)
            for i, dr in enumerate(daily, start=1):
                embed.add_field(name=f"[D{i}] {dr['time']}", value=dr["message"], inline=False)
            for i, wr in enumerate(weekly, start=1):
                embed.add_field(name=f"[W{i}] {wr['weekday']} {wr['time']}", value=wr["message"], inline=False)
            if not daily and not weekly: embed.description = "登録なし"
            await interaction.response.send_message(embed=embed)

        @app_commands.command(name="remove", description="リマインダー削除 (例: D1)")
        async def remove_reminder(self, interaction: discord.Interaction, reminder_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            try:
                if reminder_id.startswith("D"):
                    guild_data.get("daily_reminders", []).pop(int(reminder_id[1:]) - 1)
                elif reminder_id.startswith("W"):
                    guild_data.get("weekly_reminders", []).pop(int(reminder_id[1:]) - 1)
                await data_manager.save_all()
                await interaction.response.send_message(f"✅ 削除しました。")
            except:
                await interaction.response.send_message("❌ 無効なIDです。")

        # --- Google Calendar コマンド ---
        @app_commands.command(name="gcal_set", description="GoogleカレンダーIDを設定")
        async def gcal_set(self, interaction: discord.Interaction, calendar_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            guild_data["google_calendar_id"] = calendar_id
            await data_manager.save_all()
            await interaction.response.send_message(f"✅ IDを設定しました: `{calendar_id}`")

        @app_commands.command(name="gcal_add", description="Googleカレンダーに予定追加")
        async def gcal_add(self, interaction: discord.Interaction, date: str, time: str, title: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            cal_id = guild_data.get("google_calendar_id")
            if not cal_id:
                await interaction.response.send_message("❌ IDが未設定です。")
                return
            await interaction.response.defer()
            try:
                # 実行
                res = gcal.add_event(cal_id, title, date, time)
                # 結果表示を詳細にする
                html_link = res.get('htmlLink', 'リンクなし')
                await interaction.followup.send(
                    f"📅 **追加成功！**\n"
                    f"タイトル: {title}\n"
                    f"カレンダーID: `{cal_id}`\n"
                    f"URL: [カレンダーを開く]({html_link})"
                )
            except Exception as e:
                await interaction.followup.send(f"❌ エラー発生: {e}")

    bot.tree.add_command(Reminder())

    # --- バックグラウンド通知ループ ---
    async def reminder_loop():
        await bot.wait_until_ready()
        while not bot.is_closed():
            now = datetime.now(JST).replace(second=0, microsecond=0)
            is_report_time = (now.hour == 8 and now.minute == 0) # 毎朝8時

            for guild in bot.guilds:
                guild_data = data_manager.get_guild_data(guild.id)
                rem = guild_data.get("reminder", {})
                channel = bot.get_channel(rem.get("channel_id")) if rem.get("enabled") else None

                if not channel: continue

                # 1. Googleカレンダー朝の通知 (8:00)
                if is_report_time:
                    cal_id = guild_data.get("google_calendar_id")
                    if cal_id:
                        try:
                            events = gcal.get_todays_events(cal_id)
                            if events:
                                lines = []
                                for e in events:
                                    st = e['start'].get('dateTime', '終日')
                                    if 'T' in st: st = st.split('T')[1][:5]
                                    lines.append(f"・{st} : {e['summary']}")
                                await channel.send(f"📅 **今日の予定**\n" + "\n".join(lines))
                        except Exception as e:
                            print(f"GCal Error: {e}")

                # 2. 既存のカレンダー予定（5分前など）
                notify_before = int(rem.get("notify_minutes", 5))
                for ev in guild_data.get("events", []):
                    try:
                        ev_dt = datetime.fromisoformat(ev["datetime"]).astimezone(JST)
                        if int((ev_dt - now).total_seconds() // 60) == notify_before:
                            await channel.send(f"⏰ **{notify_before}分後**: {ev.get('title')}")
                    except: continue

                # 3. 毎日リマインダー
                for dr in guild_data.get("daily_reminders", []):
                    if dr["time"] == now.strftime("%H:%M"):
                        ch = bot.get_channel(dr["channel_id"])
                        if ch: await ch.send(f"⏰ 毎日通知: {dr['message']}")

                # 4. 毎週リマインダー
                wd_map = {"月":0,"火":1,"水":2,"木":3,"金":4,"土":5,"日":6}
                for wr in guild_data.get("weekly_reminders", []):
                    if wd_map.get(wr["weekday"]) == now.weekday() and wr["time"] == now.strftime("%H:%M"):
                        ch = bot.get_channel(wr["channel_id"])
                        if ch: await ch.send(f"⏰ 毎週通知: {wr['message']}")

            await asyncio.sleep(55)

    if not hasattr(bot, "_reminder_loop_started"):
        bot._reminder_loop_started = True
        # ここを修正しました (async を削除)
        asyncio.create_task(reminder_loop())