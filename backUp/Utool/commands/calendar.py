from discord import app_commands
import discord
from datetime import datetime, timezone, timedelta

# JST タイムゾーン
JST = timezone(timedelta(hours=9))

def register_calendar_commands(bot, data_manager):
    class Calendar(app_commands.Group):
        def __init__(self):
            super().__init__(name="cal", description="予定・Todo一括管理")

        # ===== 内部ユーティリティ =====
        def _sorted_events(self, guild_data):
            return sorted(guild_data["events"], key=lambda x: datetime.fromisoformat(x["datetime"]))

        async def _send_embed_list(self, interaction, items, title, is_todo=False):
            if not items:
                await interaction.followup.send("データはありません。")
                return

            embed = discord.Embed(title=title, color=0x00ff99 if not is_todo else 0x9b59b6)
            now = datetime.now(JST)

            for i, item in enumerate(items, start=1):
                if is_todo:
                    status = "✅" if item["done"] else "❌"
                    due_text = ""
                    if item.get("due"):
                        try:
                            due_dt = datetime.fromisoformat(item["due"]).astimezone(JST)
                            due_text = f"\n期限: {due_dt.strftime('%Y-%m-%d %H:%M')}"
                            if not item["done"] and due_dt < now:
                                due_text += " ⚠️ 期限切れ"
                        except Exception:
                            due_text = "\n期限: （形式不正）"
                    added = item.get("added_at", "")
                    if added:
                        try:
                            added = datetime.fromisoformat(added).astimezone(JST).strftime('%Y-%m-%d %H:%M')
                        except Exception:
                            pass
                    embed.add_field(
                        name=f"{i}. {status} {item['content']}",
                        value=f"追加: {added}{due_text}",
                        inline=False
                    )
                else:
                    dt = datetime.fromisoformat(item["datetime"]).astimezone(JST)
                    embed.add_field(
                        name=f"{i}. {item['title']}",
                        value=f"🗓 {dt.strftime('%Y-%m-%d %H:%M')}",
                        inline=False
                    )

            await interaction.followup.send(embed=embed)

        # ===== 予定 =====
        @app_commands.command(name="add", description="予定を追加します")
        async def add(self, interaction: discord.Interaction, title: str, date: str, time_str: str = None):
            await interaction.response.defer()
            dt_str = f"{date}T{time_str}" if time_str else f"{date}T00:00"
            try:
                dt = datetime.fromisoformat(dt_str).replace(tzinfo=JST)
            except Exception:
                await interaction.followup.send("❌ 日付形式が不正です。YYYY-MM-DD または YYYY-MM-DD HH:MM")
                return

            guild_data = data_manager.get_guild_data(interaction.guild_id)
            guild_data["events"].append({"title": title, "datetime": dt.isoformat()})
            guild_data["events"] = self._sorted_events(guild_data)
            await data_manager.save_all()

            embed = discord.Embed(title="予定追加", description=title, color=0x00ff00)
            embed.add_field(name="日時", value=dt.strftime("%Y-%m-%d %H:%M"))
            await interaction.followup.send(embed=embed)

        @app_commands.command(name="list", description="今後の予定を表示します")
        async def list_events(self, interaction: discord.Interaction, max_results: int = 10):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            events = self._sorted_events(guild_data)[:max_results]
            await self._send_embed_list(interaction, events, "今後の予定")

        @app_commands.command(name="today", description="今日の予定を表示します")
        async def today(self, interaction: discord.Interaction):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            today_str = datetime.now(JST).date().isoformat()
            today_events = [ev for ev in self._sorted_events(guild_data) if ev["datetime"].startswith(today_str)]
            await self._send_embed_list(interaction, today_events, "今日の予定")

        @app_commands.command(name="remove", description="番号で予定を削除します（表示順基準）")
        async def remove(self, interaction: discord.Interaction, index: int):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            events_sorted = self._sorted_events(guild_data)

            if index < 1 or index > len(events_sorted):
                await interaction.followup.send("❌ 番号が不正です。")
                return

            removed = events_sorted.pop(index - 1)
            guild_data["events"] = events_sorted
            await data_manager.save_all()

            dt = datetime.fromisoformat(removed["datetime"]).astimezone(JST).strftime("%Y-%m-%d %H:%M")
            embed = discord.Embed(title="予定削除", description=removed["title"], color=0xe74c3c)
            embed.add_field(name="日時", value=dt)
            await interaction.followup.send(embed=embed)

        @app_commands.command(name="edit", description="予定を修正します（表示順基準）")
        async def edit(self, interaction: discord.Interaction, index: int, new_title: str, new_date: str = None, new_time: str = None):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            events_sorted = self._sorted_events(guild_data)

            if index < 1 or index > len(events_sorted):
                await interaction.followup.send("❌ 番号が不正です。")
                return

            event = events_sorted[index - 1]
            event["title"] = new_title

            if new_date:
                dt_str = f"{new_date}T{new_time}" if new_time else f"{new_date}T00:00"
                try:
                    new_dt = datetime.fromisoformat(dt_str).replace(tzinfo=JST)
                    event["datetime"] = new_dt.isoformat()
                except Exception:
                    await interaction.followup.send("❌ 日付形式が不正です。YYYY-MM-DD または YYYY-MM-DD HH:MM")
                    return

            guild_data["events"] = self._sorted_events(guild_data)
            await data_manager.save_all()

            embed = discord.Embed(title="予定修正", description=event["title"], color=0x3498db)
            embed.add_field(name="日時", value=datetime.fromisoformat(event["datetime"]).astimezone(JST).strftime("%Y-%m-%d %H:%M"))
            await interaction.followup.send(embed=embed)

    bot.tree.add_command(Calendar())
