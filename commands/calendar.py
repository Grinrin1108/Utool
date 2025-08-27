import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import json

DATA_FILE = "data.json"
JST = timezone(timedelta(hours=9))


async def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


async def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class Calendar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- 📅 予定追加 ---
    @app_commands.command(name="cal_add", description="予定を追加します")
    async def cal_add(self, interaction: discord.Interaction, title: str, date: str, time: str = None):
        await interaction.response.defer(ephemeral=False)

        data = await load_data()
        dt_str = f"{date}T{time}:00+09:00" if time else f"{date}T00:00:00+09:00"
        dt = datetime.fromisoformat(dt_str)

        data["calendar"].append({
            "title": title,
            "datetime": dt.astimezone(JST).isoformat()
        })
        await save_data(data)
        await interaction.followup.send(f"✅ 予定を追加しました: **{title}** {dt.strftime('%Y-%m-%d %H:%M')}")

    # --- 📅 予定一覧 ---
    @app_commands.command(name="cal_list", description="予定を一覧表示します")
    async def cal_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        data = await load_data()
        events = sorted(
            data["calendar"],
            key=lambda e: datetime.fromisoformat(e["datetime"])
        )

        if not events:
            await interaction.followup.send("予定はありません。")
            return

        embed = discord.Embed(title="📅 予定一覧", color=0x00aaff)
        for e in events:
            dt = datetime.fromisoformat(e["datetime"]).astimezone(JST)
            embed.add_field(
                name=e["title"],
                value=dt.strftime("%Y-%m-%d %H:%M"),
                inline=False
            )

        await interaction.followup.send(embed=embed)

    # --- ✅ Todo追加 ---
    @app_commands.command(name="todo_add", description="Todoを追加します（期限は省略可）")
    async def todo_add(self, interaction: discord.Interaction, task: str, deadline: str = None, time: str = None):
        await interaction.response.defer(ephemeral=False)

        data = await load_data()
        if deadline:
            dt_str = f"{deadline}T{time}:00+09:00" if time else f"{deadline}T00:00:00+09:00"
            dt = datetime.fromisoformat(dt_str).astimezone(JST).isoformat()
        else:
            dt = None

        data["todo"].append({
            "task": task,
            "deadline": dt,
            "done": False
        })
        await save_data(data)

        msg = f"✅ Todoを追加しました: **{task}**"
        if dt:
            msg += f"（期限: {datetime.fromisoformat(dt).strftime('%Y-%m-%d %H:%M')}）"
        await interaction.followup.send(msg)

    # --- 📋 Todo一覧 ---
    @app_commands.command(name="todo_list", description="Todoを一覧表示します")
    async def todo_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        data = await load_data()
        todos = sorted(
            data["todo"],
            key=lambda t: datetime.fromisoformat(t["deadline"]) if t["deadline"] else datetime.max
        )

        if not todos:
            await interaction.followup.send("Todoはありません。")
            return

        embed = discord.Embed(title="📋 Todo一覧", color=0x33cc33)
        now = datetime.now(JST)

        for i, t in enumerate(todos, 1):
            status = "✅ 完了" if t["done"] else "⏳ 未完了"
            if t["deadline"]:
                dt = datetime.fromisoformat(t["deadline"]).astimezone(JST)
                if not t["done"] and dt < now:
                    status += " ⚠️期限切れ"
                deadline_str = dt.strftime("%Y-%m-%d %H:%M")
            else:
                deadline_str = "（期限なし）"

            embed.add_field(
                name=f"{i}. {t['task']}",
                value=f"{status}\n期限: {deadline_str}",
                inline=False
            )

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Calendar(bot))
