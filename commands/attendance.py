import discord
from discord import app_commands, ui
from datetime import datetime, timezone, timedelta
import io
import csv

JST = timezone(timedelta(hours=9))

class AttendanceView(ui.View):
    def __init__(self, data_manager, guild_id, date_str):
        super().__init__(timeout=None)
        self.dm = data_manager
        self.guild_id = guild_id
        self.date_str = date_str

    async def update_attendance(self, it: discord.Interaction, status: str, emoji: str):
        data = self.dm.get_guild_data(self.guild_id)
        if "attendance" not in data: data["attendance"] = {}
        if self.date_str not in data["attendance"]: data["attendance"][self.date_str] = {}
        
        user_name = it.user.display_name
        data["attendance"][self.date_str][str(it.user.id)] = {"name": user_name, "status": status}
        await self.dm.save_all()
        
        await it.response.send_message(f"{emoji} **{status}** で記録しました（{user_name}さん）", ephemeral=True)

    @ui.button(label="出席", style=discord.ButtonStyle.success, emoji="✅")
    async def present(self, it: discord.Interaction, button: ui.Button):
        await self.update_attendance(it, "出席", "✅")

    @ui.button(label="遅刻", style=discord.ButtonStyle.secondary, emoji="⏳") # ここを secondary(gray) に修正
    async def late(self, it: discord.Interaction, button: ui.Button):
        await self.update_attendance(it, "遅刻", "⏳")

    @ui.button(label="欠席", style=discord.ButtonStyle.danger, emoji="❌")
    async def absent(self, it: discord.Interaction, button: ui.Button):
        await self.update_attendance(it, "欠席", "❌")

def register_attendance_commands(bot, data_manager):
    @bot.tree.command(name="attend_board", description="今日の出席確認パネルを出します")
    async def attend_board(it: discord.Interaction):
        today = datetime.now(JST).strftime('%Y-%m-%d')
        emb = discord.Embed(
            title=f"📅 {today} 出席確認",
            description="今日の活動に参加できるか、下のボタンを押して教えてください！ @everyone",
            color=0x3498db
        )
        await it.response.send_message(embed=emb, view=AttendanceView(data_manager, it.guild_id, today))

    @bot.tree.command(name="attend_list", description="今日の出席状況を表示します")
    async def attend_list(it: discord.Interaction):
        today = datetime.now(JST).strftime('%Y-%m-%d')
        data = data_manager.get_guild_data(it.guild_id)
        records = data.get("attendance", {}).get(today, {})
        
        if not records:
            return await it.response.send_message(f"まだ {today} の回答はありません。", ephemeral=True)
        
        summary = {"出席": [], "遅刻": [], "欠席": []}
        for uid, info in records.items():
            summary[info["status"]].append(info["name"])
        
        emb = discord.Embed(title=f"📊 {today} 出席集計", color=0x2ecc71)
        for status, names in summary.items():
            val = "\n".join(names) if names else "なし"
            emb.add_field(name=f"{status} ({len(names)}人)", value=val, inline=True)
            
        await it.response.send_message(embed=emb, ephemeral=True)

    @bot.tree.command(name="attend_export", description="これまでの出席データをCSV(Excel用)で書き出します")
    async def attend_export(it: discord.Interaction):
        await it.response.defer(ephemeral=True) # 処理に時間がかかるかもなので保留
        
        data = data_manager.get_guild_data(it.guild_id)
        attendance_data = data.get("attendance", {})
        
        if not attendance_data:
            return await it.followup.send("まだ出席データがありません。")

        # CSVデータを作成（メモリ上に保持）
        output = io.StringIO()
        writer = csv.writer(output)
        
        # ヘッダー（1行目）
        writer.writerow(["日付", "ユーザー名", "出席ステータス"])
        
        # データを日付順に整理して書き込み
        for date_str in sorted(attendance_data.keys()):
            for user_id, info in attendance_data[date_str].items():
                writer.writerow([date_str, info["name"], info["status"]])
        
        # ファイルとして送信するために変換
        output.seek(0)
        file = discord.File(fp=io.BytesIO(output.getvalue().encode('utf-8-sig')), filename=f"attendance_backup_{it.guild_id}.csv")
        
        await it.followup.send("これまでの出席データを書き出しました！Excelで開いて確認してください。", file=file)