# commands/reminder.py
from discord import app_commands, ui
import discord
import asyncio
import os
import json
import requests
from datetime import datetime, timezone, timedelta
import re

# --- 設定項目 ---
JST = timezone(timedelta(hours=9))
SCOPES = ['https://www.googleapis.com/auth/calendar']
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

# 天気予報用コード変換
WEATHER_CODES = {
    0: "☀️快晴", 1: "🌤️晴れ", 2: "⛅くもり", 3: "☁️曇り",
    45: "🌫️霧", 48: "🌫️霧", 51: "🚿小雨", 53: "🚿小雨", 55: "🚿小雨",
    61: "☔雨", 63: "☔雨", 65: "☔激しい雨", 71: "❄️雪", 73: "❄️雪", 75: "❄️激しい雪",
    80: "🌦️にわか雨", 81: "🌦️にわか雨", 82: "🌦️激しいにわか雨", 95: "⚡雷雨"
}

# --- ヘルパー関数 ---

def parse_extended_datetime(date_str, time_str):
    """
    '25:30' などの表記を解釈し、翌日の '01:30' として datetime オブジェクトを返す。
    """
    # 基準となる日付（00:00:00）を作成
    base_dt = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=JST)
    
    # 記号のゆらぎを補正 (25.30 -> 25:30)
    time_str = time_str.replace('.', ':')
    match = re.match(r"(\d{1,2}):(\d{2})", time_str)
    if not match:
        raise ValueError("時間の形式が正しくありません (例: 25:30)")
    
    hours, minutes = map(int, match.groups())
    
    # hours // 24 で翌日以降の加算日数を算出。hours % 24 で実際の時間を算出。
    return base_dt + timedelta(days=(hours // 24)) + timedelta(hours=(hours % 24), minutes=minutes)

def get_weather():
    """Open-Meteo APIから東京の天気を取得して辞書形式で返す"""
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=35.6895&longitude=139.6917&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=Asia%2FTokyo"
        r = requests.get(url).json()
        forecast = {}
        for i, d in enumerate(r['daily']['time']):
            forecast[d] = f"{WEATHER_CODES.get(r['daily']['weathercode'][i], '❓')} ({r['daily']['temperature_2m_max'][i]}℃/{r['daily']['temperature_2m_min'][i]}℃)"
        return forecast
    except:
        return {}

# --- Google Calendar 操作クラス ---

class GoogleCalendarManager:
    def __init__(self):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            try:
                info = json.loads(creds_json)
                self.creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
                self.service = build('calendar', 'v3', credentials=self.creds)
            except:
                self.service = None
        else:
            self.service = None

    def add_event(self, calendar_id, title, date_str, start_time_str=None, end_time_str=None):
        """予定の追加ロジック"""
        if not self.service: return
        
        if start_time_str:
            # 開始時刻の解析 (25時表記対応)
            s_dt = parse_extended_datetime(date_str, start_time_str)
            
            if end_time_str:
                # 終了時刻の解析
                e_dt = parse_extended_datetime(date_str, end_time_str)
                # 終了が開始より前なら翌日とみなす (例: 23:00〜01:00)
                if e_dt <= s_dt:
                    e_dt += timedelta(days=1)
            else:
                # 終了指定なしなら1時間後に設定
                e_dt = s_dt + timedelta(hours=1)
                
            body = {
                'summary': title,
                'start': {'dateTime': s_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
                'end': {'dateTime': e_dt.isoformat(), 'timeZone': 'Asia/Tokyo'}
            }
        else:
            # 終日予定
            body = {
                'summary': title,
                'start': {'date': date_str},
                'end': {'date': (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')}
            }
        return self.service.events().insert(calendarId=calendar_id, body=body).execute()

    def get_events(self, calendar_id, days=7):
        """直近指定日数の予定を取得"""
        if not self.service: return []
        now = datetime.now(JST)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        time_max = (now + timedelta(days=days)).replace(hour=23, minute=59, second=59).isoformat()
        try:
            res = self.service.events().list(calendarId=calendar_id, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
            return res.get('items', [])
        except:
            return []

# --- UIパーツ (Modal / View) ---

class UniversalAddModal(ui.Modal, title="予定の登録"):
    """
    登録用フォーム。
    日付が最初から入っている場合（クイック追加）と、空の場合（手入力追加）の両方で使用。
    """
    date_input = ui.TextInput(label="日付 (YYYY-MM-DD)", placeholder="2026-03-20", min_length=10, max_length=10)
    title_input = ui.TextInput(label="タイトル", placeholder="会議、飲み会など", required=True)
    start_input = ui.TextInput(label="開始時間 (25:00対応)", placeholder="19:00", required=False)
    end_input = ui.TextInput(label="終了時間 (日またぎ対応)", placeholder="21:00", required=False)

    def __init__(self, gcal, cid, default_date=""):
        super().__init__()
        self.gcal, self.cid = gcal, cid
        if default_date:
            self.date_input.default = default_date

    async def on_submit(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        try:
            self.gcal.add_event(self.cid, self.title_input.value, self.date_input.value, self.start_input.value or None, self.end_input.value or None)
            await it.followup.send(f"✅ **{self.title_input.value}** を登録しました！", ephemeral=True)
        except Exception as e:
            await it.followup.send(f"❌ 登録失敗。形式を確認してください。\n日付: `2026-03-20` / 時間: `25:30`", ephemeral=True)

class ReminderMenuView(ui.View):
    """
    メインメニューボタン群
    """
    def __init__(self, gcal, dm):
        super().__init__(timeout=None)
        self.gcal, self.dm = gcal, dm

    @ui.button(label="➕ 2週間以内の追加", style=discord.ButtonStyle.success, emoji="📆")
    async def quick_add(self, it: discord.Interaction, button: ui.Button):
        # 2週間分の日付をドロップダウンメニューで作成
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        view = ui.View()
        select = ui.Select(placeholder="カレンダーから日付を選択...")
        now = datetime.now(JST)
        for i in range(14):
            target = now + timedelta(days=i)
            val = target.strftime('%Y-%m-%d')
            label = target.strftime('%m/%d') + f" ({WEEKDAYS[target.weekday()]})"
            select.add_option(label=label, value=val)
        
        async def callback(sit: discord.Interaction):
            await sit.response.send_modal(UniversalAddModal(self.gcal, cid, default_date=select.values[0]))
        
        select.callback = callback
        view.add_item(select)
        await it.response.send_message("日付を選んでください：", view=view, ephemeral=True)

    @ui.button(label="🚀 日付を指定して追加", style=discord.ButtonStyle.secondary, emoji="📅")
    async def manual_add(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        await it.response.send_modal(UniversalAddModal(self.gcal, cid))

    @ui.button(label="🔍 予定を確認", style=discord.ButtonStyle.primary, emoji="📋")
    async def list_events(self, it: discord.Interaction, button: ui.Button):
        await it.response.defer(ephemeral=True)
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        events = self.gcal.get_events(cid, days=7)
        weather = get_weather()
        
        if not events:
            return await it.followup.send("✨ 予定はありません。", ephemeral=True)

        # 日付ごとにグループ化
        grouped = {}
        for e in events:
            d = e['start'].get('dateTime', e['start'].get('date'))[:10]
            if d not in grouped: grouped[d] = []
            grouped[d].append(e)
        
        embeds = []
        today_str = datetime.now(JST).strftime('%Y-%m-%d')
        
        # 各日付を独立したEmbedカードとして出力
        for d, evs in sorted(grouped.items()):
            dt = datetime.strptime(d, '%Y-%m-%d')
            w = weather.get(d, "")
            color = 0x2ecc71 if d == today_str else 0x3498db
            emb = discord.Embed(title=f"📅 {dt.strftime('%m/%d')} ({WEEKDAYS[dt.weekday()]}) {w}", color=color)
            
            lines = []
            for e in evs:
                st = e['start'].get('dateTime', "終日")
                time_str = f"`{st[11:16]}`" if ":" in st else "`終日`"
                lines.append(f"{'⏰' if ':' in st else '☀️'} {time_str} **{e['summary']}**\n└ ID: `{e['id']}`")
            
            emb.description = "\n".join(lines)
            embeds.append(emb)

        # 1メッセージ最大10個まで送信
        await it.followup.send(embeds=embeds[:10], ephemeral=True)

    @ui.button(label="🗑️ 予定を削除", style=discord.ButtonStyle.danger, emoji="🧹")
    async def delete_event(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        
        class DelModal(ui.Modal, title="予定の削除"):
            ev_id_input = ui.TextInput(label="イベントIDを貼り付けてください", placeholder="バックマーク ` 等は自動で除去されます", required=True)
            
            def __init__(self, gcal, cid):
                super().__init__()
                self.gcal, self.cid = gcal, cid

            async def on_submit(self, sit: discord.Interaction):
                # IDの前後から余計な空白や ` 記号を除去 (コピーミス対策)
                raw_id = self.ev_id_input.value.strip().replace("`", "")
                try:
                    self.gcal.service.events().delete(calendarId=self.cid, eventId=raw_id).execute()
                    await sit.response.send_message(f"🗑️ 削除完了\n(ID: `{raw_id[:10]}...`)", ephemeral=True)
                except Exception as e:
                    await sit.response.send_message(f"❌ 削除失敗。IDが正しいか確認してください。\n理由: `{str(e)[:50]}`", ephemeral=True)
        
        await it.response.send_modal(DelModal(self.gcal, cid))

# --- メインロジック ---

def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self): super().__init__(name="rem", description="Googleカレンダー管理")

        @app_commands.command(name="menu", description="操作メニューを開く")
        async def menu(self, it: discord.Interaction):
            now = datetime.now(JST)
            emb = discord.Embed(title="🗓️ カレンダー操作パネル", description=f"現在は **{now.strftime('%Y/%m/%d')}** です。\nボタンを押して操作を選んでください。", color=0x4285F4)
            await it.response.send_message(embed=emb, view=ReminderMenuView(gcal, data_manager))

        @app_commands.command(name="on", description="初期設定（カレンダーID登録）")
        async def on(self, it: discord.Interaction, calendar_id: str):
            data = data_manager.get_guild_data(it.guild_id)
            data["google_calendar_id"] = calendar_id
            data["reminder"] = {"enabled": True, "channel_id": it.channel_id}
            await data_manager.save_all()
            await it.response.send_message("✅ 通知設定を完了しました！朝6時と10分前に通知します。")

    bot.tree.add_command(Reminder())

    # --- バックグラウンド通知ループ ---
    async def loop():
        await bot.wait_until_ready()
        reminded_ids = set()
        while not bot.is_closed():
            now = datetime.now(JST)
            # 朝6時の天気・予定まとめ
            if now.hour == 6 and now.minute == 0:
                weather = get_weather()
                for gid, gdata in data_manager.data.items():
                    r = gdata.get("reminder", {})
                    if r.get("enabled"):
                        ch, cid = bot.get_channel(r.get("channel_id")), gdata.get("google_calendar_id")
                        if ch and cid:
                            evs = gcal.get_events(cid, days=1)
                            w = weather.get(now.strftime('%Y-%m-%d'), "")
                            emb = discord.Embed(title=f"☀️ {now.strftime('%m/%d')} 本日の予定", color=0xf1c40f)
                            lines = [f"・`{e['start'].get('dateTime', '  終日  ')[11:16]}` {e['summary']}" for e in evs]
                            emb.description = f"天気: **{w}**\n\n" + ("\n".join(lines) if lines else "本日の予定はありません。")
                            await ch.send(embed=emb)
                await asyncio.sleep(60)

            # 10分前リマインド (メンション付き)
            for gid, gdata in data_manager.data.items():
                r = gdata.get("reminder", {})
                if r.get("enabled"):
                    ch, cid = bot.get_channel(r.get("channel_id")), gdata.get("google_calendar_id")
                    if ch and cid:
                        try:
                            for e in gcal.get_events(cid, days=1):
                                st = e['start'].get('dateTime')
                                if st and e['id'] not in reminded_ids:
                                    dt = datetime.fromisoformat(st.replace('Z', '+00:00')).astimezone(JST)
                                    if 0 < (dt - now).total_seconds() <= 600:
                                        await ch.send(content="@everyone", embed=discord.Embed(title="🕒 まもなく開始", description=f"**{e['summary']}** が始まります！", color=0xe74c3c))
                                        reminded_ids.add(e['id'])
                        except: pass
            
            if len(reminded_ids) > 100: reminded_ids.clear()
            await asyncio.sleep(30)

    if not hasattr(bot, "_rem_loop_final_v2"):
        bot._rem_loop_final_v2 = True
        asyncio.create_task(loop())
