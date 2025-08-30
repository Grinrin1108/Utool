import discord
from discord import app_commands
from datetime import datetime, timedelta
import asyncio

# JST タイムゾーン
JST = timedelta(hours=9)

def register_reminder_commands(bot, data_manager):
    class Reminder(app_commands.Group):
        def __init__(self):
            super().__init__(name="rem", description="リマインダー管理")
            self.announce_enabled = False
            self.announce_task = None

        # -------------------------
        # タイマー型リマインダー
        # -------------------------
        @app_commands.command(name="timer", description="タイマーを設定します (例: 10s / 5m / 1h)")
        async def remind(self, interaction: discord.Interaction, time_str: str, message: str):
            await interaction.response.defer()
            try:
                amount = int(time_str[:-1])
                unit = time_str[-1]
                if unit == "s":
                    seconds = amount
                elif unit == "m":
                    seconds = amount * 60
                elif unit == "h":
                    seconds = amount * 3600
                else:
                    raise ValueError("単位が不正です")
            except:
                await interaction.followup.send("形式が違います。例: 10s / 5m / 1h")
                return

            await interaction.followup.send(f"{interaction.user.mention} リマインダーセット: {message} (あと {time_str})")
            await asyncio.sleep(seconds)
            await interaction.channel.send(f"{interaction.user.mention} リマインダー: {message}")

        # -------------------------
        # アナウンス機能
        # -------------------------
        @app_commands.group(name="announce", description="予定アナウンスの管理")
        async def announce(self, interaction: discord.Interaction):
            pass

        @announce.command(name="on", description="予定アナウンスを有効化")
        async def announce_on(self, interaction: discord.Interaction):
            if self.announce_enabled:
                await interaction.response.send_message("すでに有効です。")
                return

            self.announce_enabled = True
            self.announce_task = bot.loop.create_task(self.check_announcements(interaction.channel, interaction.guild_id))
            await interaction.response.send_message("予定アナウンスを開始しました。")

        @announce.command(name="off", description="予定アナウンスを無効化")
        async def announce_off(self, interaction: discord.Interaction):
            if not self.announce_enabled:
                await interaction.response.send_message("すでに無効です。")
                return

            self.announce_enabled = False
            if self.announce_task:
                self.announce_task.cancel()
                self.announce_task = None
            await interaction.response.send_message("予定アナウンスを停止しました。")

        @announce.command(name="status", description="予定アナウンスの状態を確認")
        async def announce_status(self, interaction: discord.Interaction):
            status = "有効" if self.announce_enabled else "無効"
            await interaction.response.send_message(f"現在の予定アナウンス: {status}")

        # -------------------------
        # 内部タスク: 定期チェック
        # -------------------------
        async def check_announcements(self, channel, guild_id):
            await bot.wait_until_ready()
            while self.announce_enabled:
                now = datetime.utcnow() + JST
                today_str = now.strftime("%Y-%m-%d")
                time_str = now.strftime("%H:%M")

                data = data_manager.load(guild_id)

                # カレンダー予定
                for event in data.get("calendar", {}).get(today_str, []):
                    if event.get("time") == time_str:
                        await channel.send(f"📅 カレンダー予定: **{event['event']}** の時間です！")

                # TODO予定
                for todo in data.get("todo", {}).get(today_str, []):
                    if todo.get("time") == time_str:
                        await channel.send(f"📝 TODO: **{todo['task']}** の時間です！")

                await asyncio.sleep(60)  # 1分ごとにチェック

    bot.tree.add_command(Reminder())
