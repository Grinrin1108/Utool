from discord import app_commands
import discord

def register_utility_commands(bot):
    @bot.tree.command(name="userinfo", description="ユーザー情報を表示します")
    async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        embed = discord.Embed(title=f"{member}", description="ユーザー情報", color=0x00ff00)
        embed.add_field(name="ID", value=member.id)
        embed.add_field(name="作成日", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"))
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="serverinfo", description="サーバー情報を表示します")
    async def serverinfo(interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title=f"{guild.name}", description="サーバー情報", color=0x0000ff)
        embed.add_field(name="ID", value=guild.id)
        embed.add_field(name="メンバー数", value=guild.member_count)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="avatar", description="ユーザーのアバターを表示します")
    async def avatar(interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        embed = discord.Embed(title=f"{member}'s Avatar")
        embed.set_image(url=member.avatar.url if member.avatar else None)
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="clear", description="チャンネルのメッセージを削除します（管理者専用）")
    async def clear(interaction: discord.Interaction, amount: int = 5):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("権限がありません。", ephemeral=True)
            return
        # 先に応答
        await interaction.response.send_message(f"{amount} 件削除を実行します…", ephemeral=True)
        # purge（ここでコマンドメッセージも消える場合はdelay）
        await interaction.channel.purge(limit=amount)