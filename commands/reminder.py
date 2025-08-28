import discord
from discord import app_commands
from datetime import datetime, timedelta
import asyncio

# JST タイムゾーン
JST = timedelta(hours=9)

def register_reminder_commands(bot):
    @bot.tree.command(name="remind", description="リマインダーを設定します (例: 10s / 5m / 1h)")
    async def remind(interaction: discord.Interaction, time_str: str, message: str):
        await interaction.response.defer()
        try:
            amount = int(time_str[:-1])
            unit = time_str[-1]
            seconds = amount * 60 if unit == "m" else amount * 3600 if unit=="h" else amount
        except:
            await interaction.followup.send("形式が違います。例: 10s / 5m / 1h")
            return
        await interaction.followup.send(f"{interaction.user.mention} リマインダーセット: {message} (あと {time_str})")
        await asyncio.sleep(seconds)
        await interaction.channel.send(f"{interaction.user.mention} リマインダー: {message}")