# commands/reminder.py
from discord import app_commands, ui
import discord
import asyncio
import os
import json
import requests
from datetime import datetime, timezone, timedelta
import re
import traceback

# --- 設定項目 ---
JST = timezone(timedelta(hours=9))
SCOPES = ['https://www.googleapis.com/auth/calendar']
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

GENRES = {
    "work": {"label": "仕事・勉強", "emoji": "💼", "tag": "[仕事]"},
    "play": {"label": "遊び・趣味", "emoji": "🎮", "tag": "[遊び]"},
    "life": {"label": "生活・家事", "emoji": "🏠", "tag": "[生活]"},
    "meal": {"label": "食事", "emoji": "🍱", "tag": "[食事]"},
    "other": {"label": "その他", "emoji": "✨", "tag": "[他]"}
}

WEATHER_CODES = {
    0: "☀️快晴", 1: "🌤️晴れ", 2: "⛅くもり", 3: "☁️曇り",
    45: "🌫️霧", 48: "🌫️霧", 51: "🚿小雨", 53: "🚿小雨", 55: "🚿小雨",
    61: "☔雨", 63: "☔雨", 65: "☔激しい雨", 71: "❄️雪", 73: "❄️雪", 75: "❄️激しい雪",
    80: "🌦️にわか雨", 81: "🌦️にわか雨", 82: "🌦️激しいにわか雨", 95: "⚡雷雨"
}

# --- ヘルパー関数 ---

def parse_extended_datetime(date_str, time_str):
    base_dt = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=JST)
    time_str = time_str.replace('.', ':')
    match = re.match(r"(\d{1,2}):(\d{2})", time_str)
    if not match:
        raise ValueError("時間形式エラー")
    hours, minutes = map(int, match.groups())
    return base_dt + timedelta(days=(hours // 24)) + timedelta(hours=(hours % 24), minutes=minutes)

def get_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=31.9111&longitude=131.4239&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=Asia%2FTokyo"
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
                info = json.loads(creds_json, strict=False)
                if "private_key" in info:
                    info["private_key"] = info["private_key"].replace("\\n", "\n")
                self.creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
                self.service = build('calendar', 'v3', credentials=self.creds)
            except:
                self.service = None
        else:
            self.service = None

    def add_event(self, calendar_id, title, date_str, start_time_str=None, end_time_str=None):
        if not self.service: return
        body = self._create_body(title, date_str, start_time_str, end_time_str)
        return self.service.events().insert(calendarId=calendar_id, body=body).execute()

    def update_event(self, calendar_id, event_id, title, date_str, start_time_str=None, end_time_str=None):
        if not self.service: return
        body = self._create_body(title, date_str, start_time_str, end_time_str)
        return self.service.events().update(calendarId=calendar_id, eventId=event_id, body=body).execute()

    def _create_body(self, title, date_str, start_time_str, end_time_str):
        if start_time_str:
            s_dt = parse_extended_datetime(date_str, start_time_str)
            if end_time_str:
                e_dt = parse_extended_datetime(date_str, end_time_str)
                if e_dt <= s_dt: e_dt += timedelta(days=1)
            else: e_dt = s_dt + timedelta(hours=1)
            return {'summary': title, 'start': {'dateTime': s_dt.isoformat(), 'timeZone': 'Asia/Tokyo'}, 'end': {'dateTime': e_dt.isoformat(), 'timeZone': 'Asia/Tokyo'}}
        else:
            return {'summary': title, 'start': {'date': date_str}, 'end': {'date': (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')}}

    def get_events(self, calendar_id, days=7):
        if not self.service: return []
        now = datetime.now(JST)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        time_max = (now + timedelta(days=days)).replace(hour=23, minute=59, second=59).isoformat()
        try:
            res = self.service.events().list(calendarId=calendar_id, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
            return res.get('items', [])
        except: return []

# --- UIパーツ ---

class UniversalAddModal(ui.Modal, title="予定の登録"):
    date_input = ui.TextInput(label="日付 (YYYY-MM-DD)", placeholder="2026-03-20")
    title_input = ui.TextInput(label="タイトル", placeholder="予定の内容", required=True)
    start_input = ui.TextInput(label="開始時間 (25:00対応)", placeholder="19:00", required=False)
    end_input = ui.TextInput(label="終了時間", placeholder="21:00", required=False)

    def __init__(self, gcal, cid, genre_key, default_date=""):
        super().__init__()
        self.gcal, self.cid = gcal, cid
        self.genre = GENRES[genre_key]
        self.date_input.default = default_date

    async def on_submit(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        tagged_title = f"{self.genre['tag']} {self.title_input.value}"
        try:
            self.gcal.add_event(self.cid, tagged_title, self.date_input.value, self.start_input.value or None, self.end_input.value or None)
            await it.followup.send(f"✅ {self.genre['emoji']} **{tagged_title}** を登録しました！", ephemeral=True)
        except:
            await it.followup.send("❌ 形式エラー。日付や時間を確認してください。", ephemeral=True)

class UniversalEditModal(ui.Modal, title="予定の編集"):
    date_input = ui.TextInput(label="日付 (YYYY-MM-DD)")
    title_input = ui.TextInput(label="タイトル（タグは自動維持）")
    start_input = ui.TextInput(label="開始時間", required=False)
    end_input = ui.TextInput(label="終了時間", required=False)

    def __init__(self, gcal, cid, event_id, current_title, current_date, current_start, current_end):
        super().__init__()
        self.gcal, self.cid, self.event_id = gcal, cid, event_id
        self.tag = ""
        match = re.match(r"(\[.*?\])\s*(.*)", current_title or "")
        if match:
            self.tag, clean_title = match.groups()
            self.title_input.default = clean_title
        else:
            self.title_input.default = current_title or ""
        self.date_input.default = current_date
        self.start_input.default = current_start or ""
        self.end_input.default = current_end or ""

    async def on_submit(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        final_title = f"{self.tag} {self.title_input.value}" if self.tag else self.title_input.value
        try:
            self.gcal.update_event(self.cid, self.event_id, final_title, self.date_input.value, self.start_input.value or None, self.end_input.value or None)
            await it.followup.send(f"✅ **{final_title}** に更新完了！", ephemeral=True)
        except:
            await it.followup.send("❌ 更新に失敗しました。", ephemeral=True)

class ReminderMenuView(ui.View):
    def __init__(self, gcal, dm):
        super().__init__(timeout=None)
        self.gcal, self.dm = gcal, dm

    async def prompt_genre_selection(self, it: discord.Interaction, cid: str, selected_date: str):
        genre_view = ui.View()
        genre_select = ui.Select(placeholder="ジャンルを選んでください")
        for k, v in GENRES.items():
            genre_select.add_option(label=v['label'], value=k, emoji=v['emoji'])
        async def genre_callback(git: discord.Interaction):
            await git.response.send_modal(UniversalAddModal(self.gcal, cid, genre_select.values[0], default_date=selected_date))
        genre_select.callback = genre_callback
        genre_view.add_item(genre_select)
        await it.response.edit_message(content=f"📅 **{selected_date}** の種別は？", view=genre_view)

    @ui.button(label="➕ 予定を追加", style=discord.ButtonStyle.success, emoji="📆")
    async def quick_add(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        now = datetime.now(JST)
        date_view = ui.View()
        date_select = ui.Select(placeholder="日付を選ぶ...")
        for label, diff in [("今日", 0), ("明日", 1), ("明後日", 2), ("来週の今日", 7)]:
            d = (now + timedelta(days=diff))
            date_select.add_option(label=f"{label} ({d.strftime('%m/%d')})", value=d.strftime('%Y-%m-%d'))
        async def date_callback(sit: discord.Interaction):
            await self.prompt_genre_selection(sit, cid, date_select.values[0])
        date_select.callback = date_callback
        date_view.add_item(date_select)
        manual_btn = ui.Button(label="⌨️ 直接入力", style=discord.ButtonStyle.secondary)
        async def manual_callback(sit: discord.Interaction):
            await self.prompt_genre_selection(sit, cid, now.strftime('%Y-%m-%d'))
        manual_btn.callback = manual_callback
        date_view.add_item(manual_btn)
        await it.response.send_message("予定の追加：日付を選択", view=date_view, ephemeral=True)

    @ui.button(label="📝 予定を編集", style=discord.ButtonStyle.secondary, emoji="✍️")
    async def edit_event(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        class EditIdModal(ui.Modal, title="編集：ID指定"):
            ev_id_input = ui.TextInput(label="イベントIDを貼り付けてください", required=True)
            def __init__(self, gcal, cid):
                super().__init__(); self.gcal, self.cid = gcal, cid
            async def on_submit(self, sit: discord.Interaction):
                # 入力値を徹底的に掃除（空白、バッククォート、"ID: " という文字列を削除）
                raw_input = self.ev_id_input.value.strip()
                raw_id = re.sub(r'^.*?ID:\s*|[`\s]', '', raw_input)
                
                try:
                    # 1. Google APIから予定を取得
                    try:
                        event = self.gcal.service.events().get(calendarId=self.cid, eventId=raw_id).execute()
                    except Exception as api_err:
                        # ここで失敗する場合はID自体が間違っている可能性大
                        return await sit.response.send_message(f"❌ Google側でIDが見つかりませんでした。\n(Error: `{api_err}`)", ephemeral=True)

                    # 2. 時間情報の解析
                    start_data = event.get('start', {})
                    end_data = event.get('end', {})
                    
                    if 'dateTime' in start_data:
                        # 時間指定の予定
                        date_val = start_data['dateTime'][:10]
                        s_time = start_data['dateTime'][11:16]
                        e_time = end_data.get('dateTime', "")[11:16] if 'dateTime' in end_data else ""
                    else:
                        # 終日の予定
                        date_val = start_data.get('date', "")
                        s_time, e_time = "", ""

                    # 3. 編集Modalを表示
                    await sit.response.send_modal(UniversalEditModal(
                        self.gcal, self.cid, raw_id, event.get('summary', ''), 
                        date_val, s_time, e_time
                    ))
                except Exception as e:
                    # 解析エラーなどの場合
                    print(f"Parsing Error: {traceback.format_exc()}")
                    await sit.response.send_message(f"❌ 解析エラーが発生しました: `{type(e).__name__}`", ephemeral=True)
        await it.response.send_modal(EditIdModal(self.gcal, cid))

    @ui.button(label="🔍 予定を確認", style=discord.ButtonStyle.primary, emoji="📋")
    async def list_events(self, it: discord.Interaction, button: ui.Button):
        await it.response.defer(ephemeral=True)
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        events = self.gcal.get_events(cid, days=7)
        weather = get_weather()
        if not events: return await it.followup.send("✨ 予定はありません。", ephemeral=True)
        grouped = {}
        for e in events:
            d = e['start'].get('dateTime', e['start'].get('date'))[:10]
            if d not in grouped: grouped[d] = []
            grouped[d].append(e)
        embeds = []
        for d, evs in sorted(grouped.items()):
            dt = datetime.strptime(d, '%Y-%m-%d')
            emb = discord.Embed(title=f"📅 {dt.strftime('%m/%d')} ({WEEKDAYS[dt.weekday()]}) 宮崎: {weather.get(d, '不明')}", color=0x3498db)
            lines = [f"{'⏰' if ':' in e['start'].get('dateTime','') else '☀️'} `{e['start'].get('dateTime','終日')[11:16] if ':' in e['start'].get('dateTime','') else '終日'}` **{e['summary']}**\n└ ID: `{e['id']}`" for e in evs]
            emb.description = "\n".join(lines)
            embeds.append(emb)
        await it.followup.send(embeds=embeds[:10], ephemeral=True)

    @ui.button(label="🗑️ 予定を削除", style=discord.ButtonStyle.danger, emoji="🧹")
    async def delete_event(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        class DelModal(ui.Modal, title="予定の削除"):
            ev_id_input = ui.TextInput(label="イベントIDを貼り付けてください", required=True)
            def __init__(self, gcal, cid):
                super().__init__(); self.gcal, self.cid = gcal, cid
            async def on_submit(self, sit: discord.Interaction):
                try:
                    self.gcal.service.events().delete(calendarId=self.cid, eventId=self.ev_id_input.value.strip().replace("`","")).execute()
                    await sit.response.send_message("🗑️ 削除完了。", ephemeral=True)
                except: await sit.response.send_message("❌ 削除に失敗しました。", ephemeral=True)
        await it.response.send_modal(DelModal(self.gcal, cid))

# --- コマンド登録・ループ ---
def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self): super().__init__(name="rem", description="カレンダー管理")
        
        @app_commands.command(name="menu", description="操作パネルを表示（お掃除機能付き）")
        async def menu(self, it: discord.Interaction):
            # 1. 応答を保留（3秒ルール対策）
            await it.response.defer(ephemeral=False)
            
            data = data_manager.get_guild_data(it.guild_id)
            
            # 2. お掃除機能：前回のメニューがあれば削除を試みる
            last_msg_id = data.get("last_menu_id")
            if last_msg_id:
                try:
                    old_msg = await it.channel.fetch_message(last_msg_id)
                    await old_msg.delete()
                except: pass # 削除できなくても次へ

            # 3. 新しいパネルを送信
            now = datetime.now(JST)
            emb = discord.Embed(title="🗓️ カレンダー操作パネル", description=f"現在は **{now.strftime('%Y/%m/%d')}** です。\n宮崎の天気と共に予定を管理します。", color=0x4285F4)
            msg = await it.followup.send(embed=emb, view=ReminderMenuView(gcal, data_manager))
            
            # 4. IDを保存して次回削除できるようにする
            data["last_menu_id"] = msg.id
            await data_manager.save_all()

        @app_commands.command(name="on", description="通知設定")
        async def on(self, it: discord.Interaction, calendar_id: str):
            data = data_manager.get_guild_data(it.guild_id)
            data.update({"google_calendar_id": calendar_id, "reminder": {"enabled": True, "channel_id": it.channel_id}})
            await data_manager.save_all()
            await it.response.send_message("✅ 設定完了！", ephemeral=True)

    bot.tree.add_command(Reminder())

    # --- ループ処理 (ステータス & 通知) ---
    async def status_loop():
        await bot.wait_until_ready()
        while not bot.is_closed():
            current_activity = "宮崎の空を監視中 ☁️"
            for gid, gdata in data_manager.data.items():
                cid = gdata.get("google_calendar_id")
                if cid:
                    try:
                        events = gcal.get_events(cid, days=0)
                        now = datetime.now(JST)
                        for e in events:
                            st, et = e['start'].get('dateTime'), e['end'].get('dateTime')
                            if st and et:
                                start = datetime.fromisoformat(st.replace('Z', '+00:00')).astimezone(JST)
                                end = datetime.fromisoformat(et.replace('Z', '+00:00')).astimezone(JST)
                                if start <= now <= end:
                                    s = e['summary']
                                    icon = "💼 仕事" if "[仕事]" in s else "🎮 遊び" if "[遊び]" in s else "🏠 生活" if "[生活]" in s else "🍱 食事" if "[食事]" in s else "📋"
                                    current_activity = f"{icon}: {s.split('] ')[-1]}"
                                    break
                    except: pass
            await bot.change_presence(activity=discord.Game(name=current_activity))
            await asyncio.sleep(600)

    async def notification_loop():
        await bot.wait_until_ready()
        reminded_ids = set()
        while not bot.is_closed():
            now = datetime.now(JST)
            # 朝6時の天気予報
            if now.hour == 6 and now.minute == 0:
                weather = get_weather()
                for gid, gdata in data_manager.data.items():
                    r = gdata.get("reminder", {})
                    if r.get("enabled"):
                        ch, cid = bot.get_channel(r.get("channel_id")), gdata.get("google_calendar_id")
                        if ch and cid:
                            evs = gcal.get_events(cid, days=1)
                            w = weather.get(now.strftime('%Y-%m-%d'), "")
                            emb = discord.Embed(title=f"☀️ {now.strftime('%m/%d')} 宮崎の予定", color=0xf1c40f)
                            lines = [f"・`{e['start'].get('dateTime', '  終日  ')[11:16]}` {e['summary']}" for e in evs]
                            emb.description = f"宮崎の天気: **{w}**\n\n" + ("\n".join(lines) if lines else "予定はありません。")
                            if ch: await ch.send(embed=emb)
                await asyncio.sleep(60)
            
            # 10分前通知
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
                                        if ch: await ch.send(content="@everyone", embed=discord.Embed(title="🕒 まもなく開始", description=f"**{e['summary']}** が始まります！", color=0xe74c3c))
                                        reminded_ids.add(e['id'])
                        except: pass
            if len(reminded_ids) > 100: reminded_ids.clear()
            await asyncio.sleep(30)

    if not hasattr(bot, "_loops_started"):
        bot._loops_started = True
        asyncio.create_task(status_loop())
        asyncio.create_task(notification_loop())
