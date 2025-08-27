# commands/calendar.py
from discord import app_commands
import discord
from datetime import datetime, date, timedelta

def register_calendar_commands(bot, get_guild_data, save_data):
    class Calendar(app_commands.Group):
        def __init__(self):
            super().__init__(name="cal", description="予定・Todo一括管理")

        # ===== 内部ユーティリティ =====
        def _sorted_events(self, guild_data):
            # 常に日時昇順
            return sorted(guild_data["events"], key=lambda x: x["datetime"])

        def _sorted_todos(self, guild_data):
            # 期限あり(0) → 期限日時昇順 → 期限なし(1) を最後に
            def key(todo):
                due_iso = todo.get("due")
                if due_iso:
                    try:
                        d = datetime.fromisoformat(due_iso)
                    except Exception:
                        d = datetime.max  # パース失敗時は最後寄り
                    return (0, d, todo.get("added_at", ""))
                else:
                    return (1, datetime.max, todo.get("added_at", ""))
            return sorted(guild_data["todos"], key=key)

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
                    # 行単位の状態表示（色はEmbed全体色のため参考表示に留める）
                    if item.get("due"):
                        try:
                            due_dt = datetime.fromisoformat(item["due"])
                            due_text = f"\n期限: {due_dt.strftime('%Y-%m-%d %H:%M')}"
                            if not item["done"] and due_dt < now:
                                due_text += " ⚠️ 期限切れ"
                        except Exception:
                            due_text = "\n期限: （形式不正）"
                    added = item.get("added_at", "")
                    if added:
                        try:
                            added = datetime.fromisoformat(added).strftime('%Y-%m-%d %H:%M')
                        except Exception:
                            pass
                    embed.add_field(
                        name=f"{i}. {status} {item['content']}",
                        value=f"追加: {added}{due_text}",
                        inline=False
                    )
                else:
                    dt = datetime.fromisoformat(item["datetime"]).strftime("%Y-%m-%d %H:%M")
                    embed.add_field(
                        name=f"{i}. {item['title']}",
                        value=f"🗓 {dt}",
                        inline=False
                    )

            await interaction.followup.send(embed=embed)

        # ===== 予定 =====
        @app_commands.command(name="add", description="予定を追加します")
        async def add(self, interaction: discord.Interaction, title: str, date: str, time_str: str = None):
            await interaction.response.defer()
            dt_str = f"{date}T{time_str}" if time_str else f"{date}T00:00"
            try:
                dt = datetime.fromisoformat(dt_str)
            except Exception:
                await interaction.followup.send("❌ 日付形式が不正です。YYYY-MM-DD または YYYY-MM-DD HH:MM")
                return

            guild_data = get_guild_data(interaction.guild_id)
            guild_data["events"].append({"title": title, "datetime": dt_str})
            # 追加後に保存配列も並びを正規化しておく
            guild_data["events"] = self._sorted_events(guild_data)
            save_data()

            embed = discord.Embed(title="予定追加", description=title, color=0x00ff00)
            embed.add_field(name="日時", value=dt.strftime("%Y-%m-%d %H:%M"))
            await interaction.followup.send(embed=embed)

        @app_commands.command(name="list", description="今後の予定を表示します")
        async def list_events(self, interaction: discord.Interaction, max_results: int = 10):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)
            events = self._sorted_events(guild_data)[:max_results]
            await self._send_embed_list(interaction, events, "今後の予定")

        @app_commands.command(name="today", description="今日の予定を表示します")
        async def today(self, interaction: discord.Interaction):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)
            today_str = date.today().isoformat()
            today_events = [ev for ev in self._sorted_events(guild_data) if ev["datetime"].startswith(today_str)]
            await self._send_embed_list(interaction, today_events, "今日の予定")

        @app_commands.command(name="remove", description="番号で予定を削除します（表示順基準）")
        async def remove(self, interaction: discord.Interaction, index: int):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)
            events_sorted = self._sorted_events(guild_data)

            if index < 1 or index > len(events_sorted):
                await interaction.followup.send("❌ 番号が不正です。")
                return

            removed = events_sorted.pop(index - 1)
            guild_data["events"] = events_sorted  # 並びを保存にも反映
            save_data()

            dt = datetime.fromisoformat(removed["datetime"]).strftime("%Y-%m-%d %H:%M")
            embed = discord.Embed(title="予定削除", description=removed["title"], color=0xe74c3c)
            embed.add_field(name="日時", value=dt)
            await interaction.followup.send(embed=embed)

        @app_commands.command(name="clear", description="全予定を削除します（管理者用）")
        async def clear_all(self, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("権限がありません。", ephemeral=True)
                return
            guild_data = get_guild_data(interaction.guild_id)
            guild_data["events"] = []
            save_data()
            await interaction.response.send_message("✅ 全予定を削除しました", ephemeral=True)

        # ===== Todo =====
        @app_commands.command(name="todo_add", description="Todoを追加します（期限指定可）")
        async def todo_add(self, interaction: discord.Interaction, content: str, due_date: str = None, due_time: str = None):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)

            due_iso = None
            due_dt = None
            if due_date:
                dt_str = f"{due_date}T{due_time}" if due_time else f"{due_date}T23:59"
                try:
                    due_dt = datetime.fromisoformat(dt_str)
                    due_iso = due_dt.isoformat()
                except Exception:
                    await interaction.followup.send("❌ 日付形式が不正です。YYYY-MM-DD または YYYY-MM-DD HH:MM")
                    return

            guild_data["todos"].append({
                "content": content,
                "done": False,
                "added_at": datetime.now().isoformat(),
                "done_at": None,
                "due": due_iso
            })
            # 追加後に正しい並びへ
            guild_data["todos"] = self._sorted_todos(guild_data)
            save_data()

            embed = discord.Embed(title="Todo追加", description=content, color=0x00ff00)
            if due_dt:
                embed.add_field(name="期限", value=due_dt.strftime("%Y-%m-%d %H:%M"))
            await interaction.followup.send(embed=embed)

        @app_commands.command(name="todo_list", description="Todo一覧を表示します（期限ありを先、期限なしは最後）")
        async def todo_list(self, interaction: discord.Interaction):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)
            todos_sorted = self._sorted_todos(guild_data)
            await self._send_embed_list(interaction, todos_sorted, "Todo一覧", is_todo=True)

        @app_commands.command(name="todo_done", description="Todoを完了にします（表示順基準）")
        async def todo_done(self, interaction: discord.Interaction, index: int):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)
            todos_sorted = self._sorted_todos(guild_data)

            if index < 1 or index > len(todos_sorted):
                await interaction.followup.send("❌ 番号が不正です。")
                return

            todo = todos_sorted[index - 1]
            todo["done"] = True
            todo["done_at"] = datetime.now().isoformat()

            # 完了後も表示順をキープ（完了でも「期限あり/なし」の並びはそのまま）
            guild_data["todos"] = self._sorted_todos(guild_data)
            save_data()

            embed = discord.Embed(title="Todo完了", description=todo["content"], color=0x00ff00)
            embed.add_field(name="完了時刻", value=todo["done_at"])
            await interaction.followup.send(embed=embed)

        @app_commands.command(name="todo_remove", description="Todoを削除します（表示順基準）")
        async def todo_remove(self, interaction: discord.Interaction, index: int):
            await interaction.response.defer()
            guild_data = get_guild_data(interaction.guild_id)
            todos_sorted = self._sorted_todos(guild_data)

            if index < 1 or index > len(todos_sorted):
                await interaction.followup.send("❌ 番号が不正です。")
                return

            removed = todos_sorted.pop(index - 1)
            guild_data["todos"] = todos_sorted  # 並びを保存にも反映
            save_data()

            embed = discord.Embed(title="Todo削除", description=removed["content"], color=0xe74c3c)
            await interaction.followup.send(embed=embed)

    bot.tree.add_command(Calendar())
