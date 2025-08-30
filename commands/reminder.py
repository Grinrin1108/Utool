# commands/reminder.py
import discord
from discord import app_commands
import asyncio
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

def register_reminder_commands(bot, data_manager):
    class Reminder(app_commands.Group):
        def __init__(self):
            super().__init__(name="rem", description="リマインダー管理")

        # ===== 内部ユーティリティ =====
        async def _send_message(self, channel, content):
            try:
                await channel.send(content)
            except:
                pass

        # ===== /rem on =====
        @app_commands.command(name="on", description="予定アナウンスを有効化")
        async def on(self, interaction: discord.Interaction):
            gd = data_manager.get_guild_data(interaction.guild_id)
            rem = gd.setdefault("reminder", {})
            rem.setdefault("notify_minutes", 5)
            rem["enabled"] = True
            rem["channel_id"] = interaction.channel.id
            await data_manager.save_all()
            await interaction.response.send_message("✅ このサーバーの予定アナウンスを有効化しました。")

        # ===== /rem off =====
        @app_commands.command(name="off", description="予定アナウンスを無効化")
        async def off(self, interaction: discord.Interaction):
            gd = data_manager.get_guild_data(interaction.guild_id)
            rem = gd.setdefault("reminder", {})
            rem["enabled"] = False
            await data_manager.save_all()
            await interaction.response.send_message("🛑 このサーバーの予定アナウンスを無効化しました。")

        # ===== /rem status =====
        @app_commands.command(name="status", description="予定アナウンスの状態を表示")
        async def status(self, interaction: discord.Interaction):
            gd = data_manager.get_guild_data(interaction.guild_id)
            rem = gd.get("reminder", {})
            enabled = rem.get("enabled", False)
            ch = interaction.guild.get_channel(rem.get("channel_id"))
            txt = f"状態: **{'有効' if enabled else '無効'}**\nチャンネル: {ch.mention if ch else '未設定'}\n通知タイミング: {rem.get('notify_minutes', 5)} 分前"
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
                await interaction.followup.send("形式が違います。例: 10s / 5m / 1h", ephemeral=True)
                return

            await interaction.followup.send(f"{interaction.user.mention} リマインダーセット: {message} (あと {time_str})", ephemeral=True)
            await asyncio.sleep(seconds)
            await interaction.channel.send(f"{interaction.user.mention} リマインダー: {message}")

    # グループを bot に登録
    bot.tree.add_command(Reminder())

    # ===== バックグラウンド通知タスク =====
    async def reminder_loop():
        await bot.wait_until_ready()
        while not bot.is_closed():
            now = datetime.now(JST).replace(second=0, microsecond=0)
            for guild in bot.guilds:
                gd = data_manager.get_guild_data(guild.id)
                rem = gd.get("reminder", {})
                if not rem.get("enabled"):
                    continue
                ch_id = rem.get("channel_id")
                if not ch_id:
                    continue
                channel = bot.get_channel(ch_id)
                if not channel:
                    continue
                notify_before = int(rem.get("notify_minutes", 5))
                for ev in gd.get("events", []):
                    try:
                        ev_dt = datetime.fromisoformat(ev["datetime"]).astimezone(JST)
                        delta_min = int((ev_dt - now).total_seconds() // 60)
                        if delta_min == notify_before:
                            await channel.send(f"⏰ **{notify_before}分後**に予定: **{ev.get('title','(無題)')}**")
                    except:
                        continue
            await asyncio.sleep(55)

    if not hasattr(bot, "_reminder_loop_started"):
        bot._reminder_loop_started = True
        asyncio.create_task(reminder_loop())
