from discord import app_commands
import discord
from datetime import datetime, date

def register_calendar_commands(bot, get_guild_data, save_data):
    class Calendar(app_commands.Group):
        def __init__(self):
            super().__init__(name="cal", description="予定・Todo一括管理")

        # ----- 予定 -----
        @app_commands.command(name="add", description="予定を追加します")
        async def add(self, interaction: discord.Interaction, title: str, date: str, time_str: str = None):
            await interaction.response.defer()
            dt_str = f"{date}T{time_str}" if time_str else f"{date}T00:00"
            try:
                dt = datetime.fromisoformat(dt_str)
            except:
                await interaction.followup.send("❌ 日付形式が不正です。YYYY-MM-DD または YYYY-MM-DD HH:MM")
                return
            guild_data = get_guild_data(interaction.guild_id)
            guild_data["events"].append({"title": title, "datetime": dt_str})
            save_data()
            embed = discord.Embed(title="予定追加", description=title, color=0x00ff00)
            embed.add_field(name="日時", value=dt.strftime("%Y-%m-%d %H:%M"))
            await interaction.followup.send(embed=embed)

        async def _send_embed_list(self, interaction, items, title, is_todo=False):
            if not items:
                await interaction.followup.send("データはありません。")
                return
            embed = discord.Embed(title=title, color=0x00ff99 if not is_todo else 0x9b59b6)
            now = datetime.now()
            for i, item in enumerate(items, start=1):
                if is_todo:
                    status = "✅" if item["done"] else "❌"
                    due_text = ""
                    color = 0x9b59b6
                    if item.get("due"):
                        due_dt = datetime.fromisoformat(item["due"])
                        due_text = f"\n期限: {due_dt.strftime('%Y-%m-%d %H:%M')}"
                        if not item["done"] and due_dt < now:
                            color = 0xe74c3c
                            due_text += " ⚠️ 期限切れ"
                    if item["done"]:
                        color = 0x00ff00
                    embed.add_field(name=f"{i}. {status} {item['content']}", value=f"追加: {item['added_at']}{due_text}", inline=False)
                else:
                    dt = datetime.fromisoformat(item["datetime"]).strftime("%Y-%m-%d %H:%M")
                    embed.add_field(name=f"{i}. {item['title']}", value=f"🗓 {dt}", inline=False)
            await interaction.followup.send(embed=embed)

        # 予定表示・削除
        @app_commands.command(name="list", description="今後の予定を表示します")
        async def list_events(self, interaction: discord.Interaction, max_results: int = 10):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)
            events = sorted(guild_data["events"], key=lambda x: x["datetime"])[:max_results]
            await self._send_embed_list(interaction, events, "今後の予定")

        @app_commands.command(name="today", description="今日の予定を表示します")
        async def today(self, interaction: discord.Interaction):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)
            today_str = date.today().isoformat()
            today_events = [ev for ev in guild_data["events"] if ev["datetime"].startswith(today_str)]
            today_events.sort(key=lambda x: x["datetime"])
            await self._send_embed_list(interaction, today_events, "今日の予定")

        @app_commands.command(name="remove", description="番号で予定を削除します")
        async def remove(self, interaction: discord.Interaction, index: int):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)
            if index < 1 or index > len(guild_data["events"]):
                await interaction.followup.send("❌ 番号が不正です。")
                return
            removed = guild_data["events"].pop(index-1)
            save_data()
            dt = datetime.fromisoformat(removed["datetime"]).strftime("%Y-%m-%d %H:%M")
            embed = discord.Embed(title="予定削除", description=removed["title"], color=0xe74c3c)
            embed.add_field(name="日時", value=dt)
            await interaction.followup.send(embed=embed)

        # ----- Todo -----
        @app_commands.command(name="todo_add", description="Todoを追加します（期限指定可）")
        async def todo_add(self, interaction: discord.Interaction, content: str, due_date: str = None, due_time: str = None):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)
            due_iso = None
            if due_date:
                dt_str = f"{due_date}T{due_time}" if due_time else f"{due_date}T23:59"
                try:
                    due_dt = datetime.fromisoformat(dt_str)
                    due_iso = due_dt.isoformat()
                except:
                    await interaction.followup.send("❌ 日付形式が不正です。YYYY-MM-DD または YYYY-MM-DD HH:MM")
                    return
            guild_data["todos"].append({
                "content": content,
                "done": False,
                "added_at": datetime.now().isoformat(),
                "done_at": None,
                "due": due_iso
            })
            save_data()
            embed = discord.Embed(title="Todo追加", description=content, color=0x00ff00)
            if due_iso:
                embed.add_field(name="期限", value=due_dt.strftime("%Y-%m-%d %H:%M"))
            await interaction.followup.send(embed=embed)

        @app_commands.command(name="todo_list", description="Todo一覧を表示します")
        async def todo_list(self, interaction: discord.Interaction):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)
            todos = guild_data["todos"]
            await self._send_embed_list(interaction, todos, "Todo一覧", is_todo=True)

        @app_commands.command(name="todo_done", description="Todoを完了にします")
        async def todo_done(self, interaction: discord.Interaction, index: int):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)
            if index < 1 or index > len(guild_data["todos"]):
                await interaction.followup.send("❌ 番号が不正です。")
                return
            todo = guild_data["todos"][index-1]
            todo["done"] = True
            todo["done_at"] = datetime.now().isoformat()
            save_data()
            embed = discord.Embed(title="Todo完了", description=todo["content"], color=0x00ff00)
            embed.add_field(name="完了時刻", value=todo["done_at"])
            await interaction.followup.send(embed=embed)

        @app_commands.command(name="todo_remove", description="Todoを削除します")
        async def todo_remove(self, interaction: discord.Interaction, index: int):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)
            if index < 1 or index > len(guild_data["todos"]):
                await interaction.followup.send("❌ 番号が不正です。")
                return
            removed = guild_data["todos"].pop(index-1)
            save_data()
            embed = discord.Embed(title="Todo削除", description=removed["content"], color=0xe74c3c)
            await interaction.followup.send(embed=embed)

    bot.tree.add_command(Calendar())
