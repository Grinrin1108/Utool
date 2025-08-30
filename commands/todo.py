from discord import app_commands
import discord
from datetime import datetime, timezone, timedelta

# JST タイムゾーン
JST = timezone(timedelta(hours=9))

def register_todo_commands(bot, data_manager):
    class Todo(app_commands.Group):
        def __init__(self):
            super().__init__(name="todo", description="Todo管理")

        # ===== 内部ユーティリティ =====
        def _sorted_todos(self, guild_data):
            def key(todo):
                due_iso = todo.get("due")
                if due_iso:
                    try:
                        d = datetime.fromisoformat(due_iso)
                    except Exception:
                        d = datetime.max
                    return (0, d, todo.get("added_at", ""))
                else:
                    return (1, datetime.max, todo.get("added_at", ""))
            return sorted(guild_data["todos"], key=key)

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

        # ===== Todo =====
        @app_commands.command(name="add", description="Todoを追加します（期限指定可）")
        async def add(self, interaction: discord.Interaction, content: str, due_date: str = None, due_time: str = None):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)

            due_iso = None
            due_dt = None
            if due_date:
                dt_str = f"{due_date}T{due_time}" if due_time else f"{due_date}T23:59"
                try:
                    due_dt = datetime.fromisoformat(dt_str).replace(tzinfo=JST)
                    due_iso = due_dt.isoformat()
                except Exception:
                    await interaction.followup.send("❌ 日付形式が不正です。YYYY-MM-DD または YYYY-MM-DD HH:MM")
                    return

            guild_data["todos"].append({
                "content": content,
                "done": False,
                "added_at": datetime.now(JST).isoformat(),
                "done_at": None,
                "due": due_iso
            })
            guild_data["todos"] = self._sorted_todos(guild_data)
            await data_manager.save_all()

            embed = discord.Embed(title="Todo追加", description=content, color=0x00ff00)
            if due_dt:
                embed.add_field(name="期限", value=due_dt.strftime("%Y-%m-%d %H:%M"))
            await interaction.followup.send(embed=embed)

        @app_commands.command(name="list", description="Todoリストを表示します")
        async def list(self, interaction: discord.Interaction, max_results: int = 20):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            todos = self._sorted_todos(guild_data)[:max_results]
            await self._send_embed_list(interaction, todos, "Todoリスト", is_todo=True)

        @app_commands.command(name="remove", description="番号でTodoを削除します（表示順基準）")
        async def remove(self, interaction: discord.Interaction, index: int):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            todos_sorted = self._sorted_todos(guild_data)

            if index < 1 or index > len(todos_sorted):
                await interaction.followup.send("❌ 番号が不正です。")
                return

            removed = todos_sorted.pop(index - 1)
            guild_data["todos"] = todos_sorted  # ←ここを修正
            await data_manager.save_all()

            embed = discord.Embed(title="Todo削除", description=removed["content"], color=0xe74c3c)
            if removed.get("due"):
                try:
                    due_dt = datetime.fromisoformat(removed["due"]).astimezone(JST).strftime("%Y-%m-%d %H:%M")
                    embed.add_field(name="期限", value=due_dt)
                except Exception:
                    pass
            await interaction.followup.send(embed=embed)

        @app_commands.command(name="clear", description="完了済みのTodoをすべて削除します")
        async def clear(self, interaction: discord.Interaction):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            before_count = len(guild_data["todos"])
            guild_data["todos"] = [td for td in guild_data["todos"] if not td["done"]]
            cleared_count = before_count - len(guild_data["todos"])
            await data_manager.save_all()

            await interaction.followup.send(f"✅ 完了済みのTodoを {cleared_count} 件削除しました。")

        @app_commands.command(name="today", description="今日のTodoを表示します")
        async def today(self, interaction: discord.Interaction):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            today_str = datetime.now(JST).date().isoformat()
            today_todos = [td for td in self._sorted_todos(guild_data) if td.get("due", "").startswith(today_str) and not td["done"]]
            await self._send_embed_list(interaction, today_todos, "今日のTodo", is_todo=True)

        @app_commands.command(name="done", description="Todoを完了にします（表示順基準）")
        async def done(self, interaction: discord.Interaction, index: int):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            todos_sorted = self._sorted_todos(guild_data)

            if index < 1 or index > len(todos_sorted):
                await interaction.followup.send("❌ 番号が不正です。")
                return

            todo = todos_sorted[index - 1]
            todo["done"] = True
            done_at_dt = datetime.now(JST)
            todo["done_at"] = done_at_dt.isoformat()
            guild_data["todos"] = self._sorted_todos(guild_data)
            await data_manager.save_all()

            embed = discord.Embed(title="Todo完了", description=todo["content"], color=0x00ff00)
            # ↓ここで表示形式を修正
            embed.add_field(name="完了時刻", value=done_at_dt.strftime("%Y-%m-%d %H:%M"))
            await interaction.followup.send(embed=embed)

        @app_commands.command(name="edit", description="Todoを修正します（表示順基準）")
        async def edit(self, interaction: discord.Interaction, index: int, new_content: str, new_due_date: str = None, new_due_time: str = None):
            await interaction.response.defer()
            guild_data = data_manager.get_guild_data(interaction.guild_id)
            todos_sorted = self._sorted_todos(guild_data)

            if index < 1 or index > len(todos_sorted):
                await interaction.followup.send("❌ 番号が不正です。")
                return

            todo = todos_sorted[index - 1]
            todo["content"] = new_content

            if new_due_date:
                dt_str = f"{new_due_date}T{new_due_time}" if new_due_time else f"{new_due_date}T23:59"
                try:
                    new_due = datetime.fromisoformat(dt_str).replace(tzinfo=JST)
                    todo["due"] = new_due.isoformat()
                except Exception:
                    await interaction.followup.send("❌ 日付形式が不正です。YYYY-MM-DD または YYYY-MM-DD HH:MM")
                    return

            guild_data["todos"] = self._sorted_todos(guild_data)
            await data_manager.save_all()

            embed = discord.Embed(title="Todo修正", description=todo["content"], color=0x3498db)
            if todo.get("due"):
                embed.add_field(name="期限", value=datetime.fromisoformat(todo["due"]).astimezone(JST).strftime("%Y-%m-%d %H:%M"))
            await interaction.followup.send(embed=embed)


    bot.tree.add_command(Todo())
