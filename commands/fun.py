import random
from discord import app_commands
import discord
import asyncio

def register_fun_commands(bot):
    @bot.tree.command(name="roll", description="サイコロを振ります (例: 2d6)")
    async def roll(interaction: discord.Interaction, dice: str):
        await interaction.response.defer()
        try:
            rolls, limit = map(int, dice.lower().split('d'))
        except:
            await interaction.followup.send("形式が違います。例: `/roll 2d6`")
            return
        results = [random.randint(1, limit) for _ in range(rolls)]
        await interaction.followup.send(f"{interaction.user.mention} rolled {dice}: {results} → 合計: {sum(results)}")

    @bot.tree.command(name="poll", description="投票を作成します")
    async def poll(interaction: discord.Interaction, question: str, option1: str, option2: str, option3: str = None, option4: str = None):
        await interaction.response.defer()
        options = [opt for opt in [option1, option2, option3, option4] if opt]
        if len(options) < 2:
            await interaction.followup.send("選択肢は2つ以上必要です。")
            return
        emojis = ["1️⃣","2️⃣","3️⃣","4️⃣"]
        description = "\n".join(f"{emojis[i]} {opt}" for i,opt in enumerate(options))
        embed = discord.Embed(title=question, description=description, color=0xffa500)
        msg = await interaction.channel.send(embed=embed)
        for i in range(len(options)):
            await msg.add_reaction(emojis[i])
        await interaction.followup.send("✅ 投票を作成しました", ephemeral=True)

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
