# commands/reminder.py
import asyncio
import discord
from discord import app_commands
from datetime import datetime, timedelta, timezone

# JST タイムゾーン
JST = timezone(timedelta(hours=9))

def register_reminder_commands(bot, data_manager):
    """
    data_manager は get_guild_data(guild_id) / save_all() を持つ想定
    - calendar.py と同じデータ構造:
      guild_data = {
        "events": [ { "title": str, "datetime": ISO8601 }, ... ],
        "todos":  [ { "content": str, "done": bool, "added_at": ISO8601, "done_at": ISO8601|None, "due": ISO8601|None }, ... ],
        "reminder": { "enabled": bool, "channel_id": int, "notify_minutes": int }
      }
    """

    class Reminder(app_commands.Group):
        def __init__(self):
            super().__init__(name="rem", description="リマインダー管理")

        # -------------------------
        # 単発タイマー
        # -------------------------
        @app_commands.command(name="timer", description="タイマーを設定します (例: 10s / 5m / 1h)")
        async def timer(self, interaction: discord.Interaction, time_str: str, message: str):
            await interaction.response.defer(ephemeral=True)
            try:
                amount = int(time_str[:-1])
                unit = time_str[-1].lower()
                if unit == "s":
                    seconds = amount
                elif unit == "m":
                    seconds = amount * 60
                elif unit == "h":
                    seconds = amount * 3600
                else:
                    raise ValueError("invalid unit")
            except Exception:
                await interaction.followup.send("形式が違います。例: 10s / 5m / 1h", ephemeral=True)
                return

            await interaction.followup.send(f"{interaction.user.mention} リマインダーセット: {message} (あと {time_str})", ephemeral=True)
            await asyncio.sleep(seconds)
            await interaction.channel.send(f"{interaction.user.mention} リマインダー: {message}")

        # -------------------------
        # リマインダー通知の基本設定
        # -------------------------
        @app_commands.command(name="setchannel", description="予定リマインダーを送るチャンネルを設定します")
        async def setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
            gd = data_manager.get_guild_data(interaction.guild_id)
            rem = gd.setdefault("reminder", {})
            rem["channel_id"] = channel.id
            await data_manager.save_all()
            await interaction.response.send_message(f"📢 リマインダー送信先を {channel.mention} に設定しました。")

        @app_commands.command(name="notifytime", description="予定を何分前に通知するか設定します（デフォルト5分）")
        async def notifytime(self, interaction: discord.Interaction, minutes: app_commands.Range[int, 1, 1440]):
            gd = data_manager.get_guild_data(interaction.guild_id)
            rem = gd.setdefault("reminder", {})
            rem["notify_minutes"] = int(minutes)
            await data_manager.save_all()
            await interaction.response.send_message(f"⏰ 予定を {minutes} 分前に通知します。")

        @app_commands.command(name="on", description="予定アナウンスを有効化します")
        async def on(self, interaction: discord.Interaction):
            gd = data_manager.get_guild_data(interaction.guild_id)
            rem = gd.setdefault("reminder", {})
            if "channel_id" not in rem:
                # 未設定なら現在のチャンネルに
                rem["channel_id"] = interaction.channel.id
            rem.setdefault("notify_minutes", 5)
            rem["enabled"] = True
            await data_manager.save_all()
            await interaction.response.send_message("✅ このサーバーの予定アナウンスを有効化しました。")

        @app_commands.command(name="off", description="予定アナウンスを無効化します")
        async def off(self, interaction: discord.Interaction):
            gd = data_manager.get_guild_data(interaction.guild_id)
            rem = gd.setdefault("reminder", {})
            rem["enabled"] = False
            await data_manager.save_all()
            await interaction.response.send_message("🛑 このサーバーの予定アナウンスを無効化しました。")

        @app_commands.command(name="status", description="予定アナウンスの状態を表示します")
        async def status(self, interaction: discord.Interaction):
            gd = data_manager.get_guild_data(interaction.guild_id)
            rem = gd.get("reminder", {})
            enabled = rem.get("enabled", False)
            channel_id = rem.get("channel_id")
            minutes = rem.get("notify_minutes", 5)
            ch = interaction.guild.get_channel(channel_id) if channel_id else None
            txt = (
                f"状態: **{'有効' if enabled else '無効'}**\n"
                f"チャンネル: {ch.mention if ch else '未設定'}\n"
                f"通知タイミング: {minutes} 分前"
            )
            await interaction.response.send_message(txt, ephemeral=True)

    # グループを登録
    bot.tree.add_command(Reminder())

    # -------------------------
    # サーバー横断のバックグラウンド監視タスク
    # -------------------------
    async def reminder_loop():
        await bot.wait_until_ready()
        while not bot.is_closed():
            now = datetime.now(JST).replace(second=0, microsecond=0)

            for guild in bot.guilds:
                gd = data_manager.get_guild_data(guild.id)
                rem = gd.get("reminder", {})
                if not rem.get("enabled"):
                    continue

                channel_id = rem.get("channel_id")
                if not channel_id:
                    continue

                channel = bot.get_channel(channel_id)
                if not channel:
                    continue

                notify_before = int(rem.get("notify_minutes", 5))

                # ---- 予定（events）通知: X分前 ----
                for ev in gd.get("events", []):
                    try:
                        ev_dt = datetime.fromisoformat(ev["datetime"]).astimezone(JST)
                    except Exception:
                        continue
                    if ev_dt < now:
                        continue

                    delta_min = int((ev_dt - now).total_seconds() // 60)
                    if delta_min == notify_before:
                        title = ev.get("title", "(無題)")
                        when = ev_dt.strftime("%Y-%m-%d %H:%M")
                        try:
                            await channel.send(f"⏰ **{notify_before}分後**に予定: **{title}**（{when}）")
                        except Exception:
                            pass

                # ---- Todo（due）通知: X分前、未完のみ ----
                for td in gd.get("todos", []):
                    if td.get("done"):
                        continue
                    due_iso = td.get("due")
                    if not due_iso:
                        continue
                    try:
                        due_dt = datetime.fromisoformat(due_iso).astimezone(JST)
                    except Exception:
                        continue
                    if due_dt < now:
                        continue

                    delta_min = int((due_dt - now).total_seconds() // 60)
                    if delta_min == notify_before:
                        content = td.get("content", "(内容なし)")
                        when = due_dt.strftime("%Y-%m-%d %H:%M")
                        try:
                            await channel.send(f"📝 **{notify_before}分後**が期限: **{content}**（{when}）")
                        except Exception:
                            pass

            # ちょうど分境界に近づけるため 55秒スリープ
            await asyncio.sleep(55)

    # 多重起動を避けるためフラグでガード
    if not hasattr(bot, "_reminder_loop_started"):
        bot._reminder_loop_started = True
        asyncio.create_task(reminder_loop())
