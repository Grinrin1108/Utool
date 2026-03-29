import discord
import json
import os

class DataManager:
    def __init__(self, bot, channel_id: int):
        self.bot = bot
        self.channel_id = channel_id
        self.data = {}

    def get_guild_data(self, guild_id):
        gid = str(guild_id)
        if gid not in self.data:
            self.data[gid] = {
                "calendar_ids": [],  # リスト形式に変更
                "reminder": {"enabled": False, "channel_id": None},
                "last_menu_id": None
            }
        
        # --- 互換性維持のための処理 ---
        # もし古いデータ(google_calendar_id)があれば、自動でリストに移動させる
        if "google_calendar_id" in self.data[gid] and self.data[gid]["google_calendar_id"]:
            old_id = self.data[gid].pop("google_calendar_id")
            if "calendar_ids" not in self.data[gid]:
                self.data[gid]["calendar_ids"] = []
            if old_id not in self.data[gid]["calendar_ids"]:
                self.data[gid]["calendar_ids"].append(old_id)
        
        return self.data[gid]

    async def load_files(self):
        if not self.channel_id: return
        channel = self.bot.get_channel(self.channel_id)
        if not channel: return
        async for msg in channel.history(limit=5):
            for att in msg.attachments:
                if att.filename == "data.json":
                    try:
                        text = await att.read()
                        self.data = json.loads(text.decode("utf-8"))
                        print("✅ データの復元に成功しました")
                        return
                    except: print("❌ ロード失敗")

    async def save_all(self):
        channel = self.bot.get_channel(self.channel_id)
        if not channel: return
        filename = "data.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        await channel.send(file=discord.File(filename))