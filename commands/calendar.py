import discord
from discord import app_commands
from discord.ext import commands
import os
import json
from datetime import datetime, timezone, timedelta

DATA_FILE = "data/calendar_todo.json"
JST = timezone(timedelta(hours=9))

# -----------------------------
# データ管理ユーティリティ
# -----------------------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"calendar": {}, "todo": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# -----------------------------
# Cog本体
# -----------------------------
class Calendar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = load_data()

    # -------------------------
    # Calendar系
    # -------------------------
    @app_commands.command(name="cal_add", description="予定を追加します")
    async def cal_add(self, interaction: discord.Interaction, title: str, date: str, time: str = "00:00"):
        await interaction.response.defer()

        try:
            dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=JST)
            iso_time = dt.isoformat()
        except ValueError:
            await interaction.followup.send("❌ 日付または時間の形式が正しくありません（例: 2025-08-28 14:00）")
            return

        guild_id = str(interaction.guild_id)
        self.data.setdefault("calendar", {}).setdefault(guild_id, []).append({
            "title": title,
            "datetime": iso_time
        })
        save_data(self.data)

        await interaction.followup.send(f"✅ 予定を追加しました: **{title}** （{dt.strftime('%Y-%m-%d %H:%M')} JST）")

    @app_commands.command(name="cal_list", description="予定一覧を表示します")
    async def cal_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = str(interaction.guild_id)
        events = self.data.get("calendar", {}).get(guild_id, [])

        if not events:
            await interaction.followup.send("📅 登録された予定はありません。")
            return

        # ソート（日付順）
        events.sort(key=lambda e: e["datetime"])

        embed = discord.Embed(title="📅 予定一覧", color=discord.Color.blue())
        for i, e in enumerate(events, start=1):
            dt = datetime.fromisoformat(e["datetime"]).astimezone(JST)
            embed.add_field(name=f"{i}. {e['title']}", value=dt.strftime("%Y-%m-%d %H:%M JST"), inline=False)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="cal_remove", description="予定を削除します")
    async def cal_remove(self, interaction: discord.Interaction, index: int):
        await interaction.response.defer()
        guild_id = str(interaction.guild_id)
        events = self.data.get("calendar", {}).get(guild_id, [])

        if 0 < index <= len(events):
            removed = events.pop(index - 1)
            save_data(self.data)
            await interaction.followup.send(f"🗑️ 予定を削除しました: **{removed['title']}**")
        else:
            await interaction.followup.send("❌ 指定された番号の予定が存在しません。")

    # -------------------------
    # Todo系
    # -------------------------
    @app_commands.command(name="todo_add", description="Todoを追加します（締め切りは任意）")
    async def todo_add(self, interaction: discord.Interaction, task: str, deadline: str = None):
        await interaction.response.defer()
        guild_id = str(interaction.guild_id)

        deadline_iso = None
        if deadline:
            try:
                dt = datetime.strptime(deadline, "%Y-%m-%d %H:%M").replace(tzinfo=JST)
                deadline_iso = dt.isoformat()
            except ValueError:
                await interaction.followup.send("❌ 締め切りの形式が正しくありません（例: 2025-08-28 18:00）")
                return

        self.data.setdefault("todo", {}).setdefault(guild_id, []).append({
            "task": task,
            "deadline": deadline_iso,
            "done": False
        })
        save_data(self.data)

        msg = f"✅ Todoを追加しました: **{task}**"
        if deadline_iso:
            msg += f" （締め切り {dt.strftime('%Y-%m-%d %H:%M JST')}）"
        await interaction.followup.send(msg)

    @app_commands.command(name="todo_list", description="Todo一覧を表示します")
    async def todo_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = str(interaction.guild_id)
        todos = self.data.get("todo", {}).get(guild_id, [])

        if not todos:
            await interaction.followup.send("📝 登録されたTodoはありません。")
            return

        # ソート（期限ありを前、期限なしを後）
        def sort_key(t):
            return (t["deadline"] is None, t["deadline"] or "")

        todos.sort(key=sort_key)

        embed = discord.Embed(title="📝 Todo一覧", color=discord.Color.green())
        now = datetime.now(JST)

        for i, t in enumerate(todos, start=1):
            status = "✅ 完了" if t["done"] else "⏳ 未完了"
            if t["deadline"]:
                dt = datetime.fromisoformat(t["deadline"]).astimezone(JST)
                if not t["done"] and dt < now:
                    status += " ⚠️期限切れ"
                deadline_str = dt.strftime("%Y-%m-%d %H:%M JST")
            else:
                deadline_str = "なし"

            embed.add_field(
                name=f"{i}. {t['task']}",
                value=f"状態: {status}\n締め切り: {deadline_str}",
                inline=False
            )

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="todo_done", description="Todoを完了にします")
    async def todo_done(self, interaction: discord.Interaction, index: int):
        await interaction.response.defer()
        guild_id = str(interaction.guild_id)
        todos = self.data.get("todo", {}).get(guild_id, [])

        if 0 < index <= len(todos):
            todos[index - 1]["done"] = True
            save_data(self.data)
            await interaction.followup.send(f"✅ Todoを完了にしました: **{todos[index-1]['task']}**")
        else:
            await interaction.followup.send("❌ 指定された番号のTodoが存在しません。")

    @app_commands.command(name="todo_remove", description="Todoを削除します")
    async def todo_remove(self, interaction: discord.Interaction, index: int):
        await interaction.response.defer()
        guild_id = str(interaction.guild_id)
        todos = self.data.get("todo", {}).get(guild_id, [])

        if 0 < index <= len(todos):
            removed = todos.pop(index - 1)
            save_data(self.data)
            await interaction.followup.send(f"🗑️ Todoを削除しました: **{removed['task']}**")
        else:
            await interaction.followup.send("❌ 指定された番号のTodoが存在しません。")


# -----------------------------
# セットアップ
# -----------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Calendar(bot))
