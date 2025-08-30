# commands/reminder.py
from discord import app_commands
import discord
import asyncio
from datetime import datetime, timezone, timedelta

# JST タイムゾーン
JST = timezone(timedelta(hours=9))

def register_reminder_commands(bot, data_manager):
    class Reminder(app_commands.Group):
        def __init__(self):
            super().__init__(name="rem", description="リマインダー管理")

        # ===== /rem on =====
        @app_commands.command(name="on", description="予定アナウンスを有効化")
        async def on(self, interaction: discord.Interaction):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            rem = guild_data.setdefault("reminder", {})
            rem.setdefault("notify_minutes", 5)
            rem["enabled"] = True
            rem["channel_id"] = interaction.channel.id
            await data_manager.save_all()
            await interaction.response.send_message("✅ このサーバーの予定アナウンスを有効化しました。")

        # ===== /rem off =====
        @app_commands.command(name="off", description="予定アナウンスを無効化")
        async def off(self, interaction: discord.Interaction):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            rem = guild_data.setdefault("reminder", {})
            rem["enabled"] = False
            await data_manager.save_all()
            await interaction.response.send_message("🛑 このサーバーの予定アナウンスを無効化しました。")

        # ===== /rem status =====
        @app_commands.command(name="status", description="予定アナウンスの状態を表示")
        async def status(self, interaction: discord.Interaction):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            rem = guild_data.get("reminder", {})
            enabled = rem.get("enabled", False)
            channel = interaction.guild.get_channel(rem.get("channel_id")) if rem.get("channel_id") else None
            txt = (
                f"状態: **{'有効' if enabled else '無効'}**\n"
                f"チャンネル: {channel.mention if channel else '未設定'}\n"
                f"通知タイミング: {rem.get('notify_minutes', 5)} 分前"
            )
            await interaction.response.send_message(txt, ephemeral=True)

        # ===== /rem timer =====
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

            await interaction.followup.send(
                f"{interaction.user.mention} リマインダーセット: {message} (あと {time_str})",
                ephemeral=True
            )
            await asyncio.sleep(seconds)
            await interaction.channel.send(f"{interaction.user.mention} ⏰ リマインダー: {message}")

        # ===== /rem daily =====
        @app_commands.command(name="daily", description="毎日指定した時刻にリマインダーを設定 (例: 21:00)")
        async def daily(self, interaction: discord.Interaction, time_str: str, message: str):
            # 時刻チェック
            try:
                hr, mn = map(int, time_str.split(":"))
                if not (0 <= hr < 24 and 0 <= mn < 60):
                    raise ValueError
            except:
                await interaction.response.send_message("❌ 時刻形式が不正です。HH:MM 形式で入力してください。", ephemeral=True)
                return

            guild_data = data_manager.get_guild_data(interaction.guild_id)
            reminders = guild_data.setdefault("daily_reminders", [])
            reminders.append({"time": time_str, "message": message, "channel_id": interaction.channel.id})
            await data_manager.save_all()
            await interaction.response.send_message(f"✅ 毎日 {time_str} に通知を登録しました: {message}")

        # ===== /rem weekly =====
        @app_commands.command(name="weekly", description="毎週指定した曜日・時刻にリマインダーを設定 (例: 月 09:00)")
        async def weekly(self, interaction: discord.Interaction, weekday: str, time_str: str, message: str):
            weekdays = {"月":0,"火":1,"水":2,"木":3,"金":4,"土":5,"日":6}
            wd = weekdays.get(weekday)
            if wd is None:
                await interaction.response.send_message("❌ 曜日が不正です。月～日で指定してください。", ephemeral=True)
                return

            # 時刻チェック
            try:
                hr, mn = map(int, time_str.split(":"))
                if not (0 <= hr < 24 and 0 <= mn < 60):
                    raise ValueError
            except:
                await interaction.response.send_message("❌ 時刻形式が不正です。HH:MM 形式で入力してください。", ephemeral=True)
                return

            guild_data = data_manager.get_guild_data(interaction.guild_id)
            reminders = guild_data.setdefault("weekly_reminders", [])
            reminders.append({"weekday": weekday, "time": time_str, "message": message, "channel_id": interaction.channel.id})
            await data_manager.save_all()
            await interaction.response.send_message(f"✅ 毎週 {weekday} {time_str} に通知を登録しました: {message}")

        # ===== /rem list =====
        @app_commands.command(name="list", description="登録済み定期リマインダー一覧")
        async def list_reminders(self, interaction: discord.Interaction):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            daily = guild_data.get("daily_reminders", [])
            weekly = guild_data.get("weekly_reminders", [])

            embed = discord.Embed(title="定期リマインダー一覧", color=0x00ff99)
            if daily:
                for i, dr in enumerate(daily, start=1):
                    ch = bot.get_channel(dr["channel_id"])
                    embed.add_field(name=f"[D{i}] {dr['time']} チャンネル: {ch.mention if ch else '不明'}", value=dr["message"], inline=False)
            if weekly:
                for i, wr in enumerate(weekly, start=1):
                    ch = bot.get_channel(wr["channel_id"])
                    embed.add_field(name=f"[W{i}] {wr['weekday']} {wr['time']} チャンネル: {ch.mention if ch else '不明'}", value=wr["message"], inline=False)
            if not daily and not weekly:
                embed.description = "登録されている定期リマインダーはありません。"

            await interaction.response.send_message(embed=embed)

        # ===== /rem remove =====
        @app_commands.command(name="remove", description="定期リマインダーを削除 (ID指定)")
        async def remove_reminder(self, interaction: discord.Interaction, reminder_id: str):
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            daily = guild_data.get("daily_reminders", [])
            weekly = guild_data.get("weekly_reminders", [])

            removed = None
            if reminder_id.startswith("D"):
                idx = int(reminder_id[1:]) - 1
                if 0 <= idx < len(daily):
                    removed = daily.pop(idx)
                    await interaction.response.send_message(f"✅ 毎日リマインダー削除: {removed['message']}")
            elif reminder_id.startswith("W"):
                idx = int(reminder_id[1:]) - 1
                if 0 <= idx < len(weekly):
                    removed = weekly.pop(idx)
                    await interaction.response.send_message(f"✅ 毎週リマインダー削除: {removed['message']}")
            else:
                await interaction.response.send_message("❌ IDが不正です。D# または W# 形式で指定してください。", ephemeral=True)
                return

            await data_manager.save_all()

    bot.tree.add_command(Reminder())

    # ===== バックグラウンド通知タスク =====
    async def reminder_loop():
        await bot.wait_until_ready()
        while not bot.is_closed():
            now = datetime.now(JST).replace(second=0, microsecond=0)
            for guild in bot.guilds:
                guild_data = data_manager.get_guild_data(guild.id)
                rem = guild_data.get("reminder", {})
                channel_id = rem.get("channel_id")
                channel = bot.get_channel(channel_id) if channel_id else None
                notify_before = int(rem.get("notify_minutes", 5)) if rem.get("enabled") else None

                # 既存予定通知
                for ev in guild_data.get("events", []):
                    try:
                        ev_dt = datetime.fromisoformat(ev["datetime"]).astimezone(JST)
                        if notify_before is not None and channel:
                            delta_min = int((ev_dt - now).total_seconds() // 60)
                            if delta_min == notify_before:
                                await channel.send(f"⏰ **{notify_before}分後**に予定: **{ev.get('title','(無題)')}**")
                    except Exception:
                        continue

                # 毎日リマインダー通知
                for dr in guild_data.get("daily_reminders", []):
                    try:
                        hr, mn = map(int, dr["time"].split(":"))
                        if now.hour == hr and now.minute == mn:
                            ch = bot.get_channel(dr["channel_id"])
                            if ch:
                                await ch.send(f"⏰ 毎日リマインダー: {dr['message']}")
                    except Exception:
                        continue

                # 毎週リマインダー通知
                weekdays_map = {"月":0,"火":1,"水":2,"木":3,"金":4,"土":5,"日":6}
                for wr in guild_data.get("weekly_reminders", []):
                    try:
                        wd = weekdays_map.get(wr["weekday"])
                        hr, mn = map(int, wr["time"].split(":"))
                        if now.weekday() == wd and now.hour == hr and now.minute == mn:
                            ch = bot.get_channel(wr["channel_id"])
                            if ch:
                                await ch.send(f"⏰ 毎週リマインダー: {wr['message']}")
                    except Exception:
                        continue

            await asyncio.sleep(55)

    if not hasattr(bot, "_reminder_loop_started"):
        bot._reminder_loop_started = True
        asyncio.create_task(reminder_loop())
