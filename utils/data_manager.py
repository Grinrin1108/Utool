import discord
import json
import os

class DataManager:
    def __init__(self, bot, channel_id: int):
        self.bot = bot
        self.channel_id = channel_id
        self.data = {}  # { guild_id: {events: [], todos: []} }

    def get_guild_data(self, guild_id):
        guild_id = str(guild_id)
        if guild_id not in self.data:
            self.data[guild_id] = {"events": [], "todos": []}
        return self.data[guild_id]

    async def load_files(self):
        """起動時に保存チャンネルからJSONを復元"""
        if not self.channel_id:
            print("⚠️ DATA_CHANNEL_ID が未設定です。")
            return

        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            print("⚠️ データ保存用チャンネルが見つかりません。")
            return

        async for msg in channel.history(limit=20):
            if msg.attachments:
                for att in msg.attachments:
                    if att.filename == "data.json":
                        text = await att.read()
                        try:
                            self.data = json.loads(text.decode("utf-8"))
                            print("✅ データをロードしました")
                            return
                        except Exception as e:
                            print("❌ データロード失敗:", e)

    async def save_all(self):
        """現在のデータをファイルとして保存チャンネルにアップロード"""
        if not self.channel_id:
            return
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            return

        filename = "data.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

        # 古いファイルを削除
        async for msg in channel.history(limit=20):
            for att in msg.attachments:
                if att.filename == filename:
                    await msg.delete()

        await channel.send(file=discord.File(filename))
        print("💾 データを保存しました")
