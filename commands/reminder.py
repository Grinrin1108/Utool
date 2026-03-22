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

# 部活・汎用向けジャンル設定
GENRES = {
    "activity": {"label": "活動・練習", "emoji": "🎺", "tag": "[活動]"},
    "meeting": {"label": "ミーティング", "emoji": "👥", "tag": "[会議]"},
    "event": {"label": "本番・行事", "emoji": "✨", "tag": "[行事]"},
    "important": {"label": "重要・締切", "emoji": "⚠️", "tag": "[重要]"},
    "other": {"label": "その他", "emoji": "📝", "tag": "[他]"}
}

WEATHER_CODES = {
    0: "☀️快晴", 1: "🌤️晴れ", 2: "⛅くもり", 3: "☁️曇り",
    45: "🌫️霧", 48: "🌫️霧", 51: "🚿小雨", 53: "🚿小雨", 55: "🚿小雨",
    61: "☔雨", 63: "☔雨", 65: "☔激しい雨", 71: "❄️雪", 73: "❄️雪", 75: "❄️激しい雪",
    80: "🌦️にわか雨", 81: "🌦️にわか雨", 82: "🌦️激しいにわか雨", 95: "⚡雷雨"
}

# --- ヘルパー関数 ---

def parse_extended_datetime(date_str, time_str):
    """25:00 などの表記を翌日として処理する関数"""
    base_dt = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=JST)
    time_str = time_str.replace('.', ':')
    match = re.match(r"(\d{1,2}):(\d{2})", time_str)
    if not match:
        raise ValueError("時間形式エラー")
    hours, minutes = map(int, match.groups())
    # 24時以降なら日を跨ぐ
    return base_dt + timedelta(days=(hours // 24)) + timedelta(hours=(hours % 24), minutes=minutes)

def get_weather():
    """宮崎の天気を取得"""
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

# --- UIパーツ：モーダル ---

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
    title_input = ui.TextInput(label="タイトル")
    start_input = ui.TextInput(label="開始時間", required=False)
    end_input = ui.TextInput(label="終了時間", required=False)

    def __init__(self, gcal, cid, event_id, current_title, current_date, current_start, current_end):
        super().__init__()
        self.gcal, self.cid, self.event_id = gcal, cid, event_id
        self.title_input.default = current_title or ""
        self.date_input.default = current_date
        self.start_input.default = current_start or ""
        self.end_input.default = current_end or ""

    async def on_submit(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        try:
            self.gcal.update_event(self.cid, self.event_id, self.title_input.value, self.date_input.value, self.start_input.value or None, self.end_input.value or None)
            await it.followup.send(f"✅ **{self.title_input.value}** に更新完了！", ephemeral=True)
        except:
            await it.followup.send("❌ 更新に失敗しました。", ephemeral=True)

# --- UIパーツ：ビュー ---

class EditLaunchView(ui.View):
    """ID入力後、クッションとして表示するボタン。モーダル連鎖エラーを回避する"""
    def __init__(self, gcal, cid, event_id, event_data):
        super().__init__(timeout=180)
        self.gcal, self.cid, self.event_id = gcal, cid, event_id
        self.event_data = event_data

    @ui.button(label="✍️ 編集画面を開く", style=discord.ButtonStyle.primary)
    async def open_edit(self, it: discord.Interaction, button: ui.Button):
        start_data = self.event_data.get('start', {})
        end_data = self.event_data.get('end', {})
        
        if 'dateTime' in start_data:
            date_val = start_data['dateTime'][:10]
            s_time = start_data['dateTime'][11:16]
            e_time = end_data.get('dateTime', "")[11:16] if 'dateTime' in end_data else ""
        else:
            date_val = start_data.get('date', "")
            s_time, e_time = "", ""

        await it.response.send_modal(UniversalEditModal(
            self.gcal, self.cid, self.event_id, 
            self.event_data.get('summary', ''), date_val, s_time, e_time
        ))

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
        if not cid: return await it.response.send_message("❌ 先に `/rem setup` でカレンダーIDを設定してください。", ephemeral=True)
        
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
        
        await it.response.send_message("予定の追加：日付を選択", view=date_view, ephemeral=True)

    @ui.button(label="📝 予定を編集", style=discord.ButtonStyle.secondary, emoji="✍️")
    async def edit_event(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        if not cid: return await it.response.send_message("❌ 未設定です。", ephemeral=True)

        class EditIdModal(ui.Modal, title="編集：ID指定"):
            ev_id_input = ui.TextInput(label="イベントIDを貼り付けてください", required=True)
            def __init__(self, gcal, cid):
                super().__init__(); self.gcal, self.cid = gcal, cid
            async def on_submit(self, sit: discord.Interaction):
                await sit.response.defer(ephemeral=True)
                raw_id = re.sub(r'^.*?ID:\s*|[`\s]', '', self.ev_id_input.value.strip())
                try:
                    event = self.gcal.service.events().get(calendarId=self.cid, eventId=raw_id).execute()
                    emb = discord.Embed(title="🔍 予定が見つかりました", description=f"予定名: **{event.get('summary', '無題')}**\nこの予定を編集しますか？", color=0x3498db)
                    await sit.followup.send(embed=emb, view=EditLaunchView(self.gcal, self.cid, raw_id, event), ephemeral=True)
                except Exception as e:
                    await sit.followup.send(f"❌ IDが見つかりません。\n`{e}`", ephemeral=True)
        
        await it.response.send_modal(EditIdModal(self.gcal, cid))

    @ui.button(label="🔍 予定を確認", style=discord.ButtonStyle.primary, emoji="📋")
    async def list_events(self, it: discord.Interaction, button: ui.Button):
        await it.response.defer(ephemeral=True)
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        if not cid: return await it.followup.send("❌ カレンダーが設定されていません。`/rem setup` を行ってください。", ephemeral=True)

        events = self.gcal.get_events(cid, days=7)
        weather = get_weather()
        if not events:
            return await it.followup.send("✨ 今後7日間に予定はありません。ゆっくり休みましょう！", ephemeral=True)

        # 日付ごとにグループ化
        grouped = {}
        for e in events:
            d = e['start'].get('dateTime', e['start'].get('date'))[:10]
            if d not in grouped: grouped[d] = []
            grouped[d].append(e)

        embeds = []
        for d, evs in sorted(grouped.items()):
            dt = datetime.strptime(d, '%Y-%m-%d')
            date_str = f"{dt.strftime('%m/%d')} ({WEEKDAYS[dt.weekday()]})"
            
            # その日のEmbed作成（最初の予定のジャンル色を反映させるなど工夫可）
            emb = discord.Embed(
                title=f"📅 {date_str} ｜ {weather.get(d, '天気情報なし')}", 
                color=0x4285F4 # Google Blue
            )
            
            field_value = ""
            for i, e in enumerate(evs):
                title = e.get('summary', '無題')
                
                # --- ジャンル絵文字の特定 ---
                emoji = "📝" # デフォルト
                for key, info in GENRES.items():
                    if info['tag'] in title:
                        emoji = info['emoji']
                        break
                
                # --- 時間表示の整形 (終日も時間指定と同じ幅に) ---
                if 'dateTime' in e['start']:
                    start_t = datetime.fromisoformat(e['start']['dateTime'].replace('Z', '+00:00')).astimezone(JST).strftime('%H:%M')
                    end_t = datetime.fromisoformat(e['end']['dateTime'].replace('Z', '+00:00')).astimezone(JST).strftime('%H:%M')
                    time_display = f"`{start_t} - {end_t}`"
                else:
                    # 終日の場合もバッククォートで幅を合わせる
                    time_display = "`  終日予定  `"

                # --- 1つの予定の表示ブロック ---
                field_value += f"{emoji} **{title}**\n"
                field_value += f"┗ {time_display}\n"
                field_value += f"   ID: `{e['id']}`\n"
                
                # 予定の間に少し隙間を作る（最後の要素以外）
                if i < len(evs) - 1:
                    field_value += "\n"

            emb.description = field_value
            embeds.append(emb)
        
        # Discordの制限（一度に10個まで）を考慮して送信
        await it.followup.send(embeds=embeds[:10], ephemeral=True)

    @ui.button(label="🗑️ 予定を削除", style=discord.ButtonStyle.danger, emoji="🧹")
    async def delete_event(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        if not cid: return await it.response.send_message("❌ 未設定です。", ephemeral=True)

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

# --- コマンド登録とループ処理 ---

def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self): super().__init__(name="rem", description="カレンダー管理")
        
        @app_commands.command(name="setup", description="このサーバー用のカレンダーを設定")
        async def setup(self, it: discord.Interaction, calendar_id: str):
            data = data_manager.get_guild_data(it.guild_id)
            data.update({
                "google_calendar_id": calendar_id,
                "reminder": {"enabled": True, "channel_id": it.channel_id}
            })
            await data_manager.save_all()
            await it.response.send_message(f"✅ 設定完了！\nID: `{calendar_id}`\n通知: <#{it.channel_id}>", ephemeral=True)

        @app_commands.command(name="menu", description="操作パネルを表示")
        async def menu(self, it: discord.Interaction):
            await it.response.defer()
            data = data_manager.get_guild_data(it.guild_id)
            
            # 古いメッセージがあれば削除してお掃除
            if data.get("last_menu_id"):
                try:
                    old_msg = await it.channel.fetch_message(data["last_menu_id"])
                    await old_msg.delete()
                except: pass

            emb = discord.Embed(title="🗓️ カレンダー操作パネル", description="予定の確認・追加・編集ができます。", color=0x4285F4)
            msg = await it.followup.send(embed=emb, view=ReminderMenuView(gcal, data_manager))
            data["last_menu_id"] = msg.id
            await data_manager.save_all()

    bot.tree.add_command(Reminder())

    # --- バックグラウンドループ ---

    async def status_loop():
        """ステータス欄に現在の予定を表示"""
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
                                    current_activity = f"進行中: {e['summary']}"
                                    break
                    except: pass
            await bot.change_presence(activity=discord.Game(name=current_activity))
            await asyncio.sleep(600)

    async def notification_loop():
        """朝の通知と直前通知"""
        await bot.wait_until_ready()
        reminded_ids = set()
        while not bot.is_closed():
            now = datetime.now(JST)
            # 朝6時の全体通知
            if now.hour == 6 and now.minute == 0:
                weather = get_weather()
                for gid, gdata in data_manager.data.items():
                    r = gdata.get("reminder", {})
                    if r.get("enabled"):
                        ch = bot.get_channel(r.get("channel_id"))
                        cid = gdata.get("google_calendar_id")
                        if ch and cid:
                            evs = gcal.get_events(cid, days=1)
                            w = weather.get(now.strftime('%Y-%m-%d'), "取得失敗")
                            emb = discord.Embed(title=f"☀️ {now.strftime('%m/%d')} 今日の予定", color=0xf1c40f)
                            lines = [f"・`{e['start'].get('dateTime', '  終日  ')[11:16]}` {e['summary']}" for e in evs]
                            emb.description = f"宮崎の天気: **{w}**\n\n" + ("\n".join(lines) if lines else "予定はありません。")
                            await ch.send(embed=emb)
                await asyncio.sleep(60)

            # 10分前の直前通知
            for gid, gdata in data_manager.data.items():
                r = gdata.get("reminder", {})
                if r.get("enabled"):
                    ch = bot.get_channel(r.get("channel_id"))
                    cid = gdata.get("google_calendar_id")
                    if ch and cid:
                        try:
                            for e in gcal.get_events(cid, days=1):
                                st = e['start'].get('dateTime')
                                if st and e['id'] not in reminded_ids:
                                    dt = datetime.fromisoformat(st.replace('Z', '+00:00')).astimezone(JST)
                                    if 0 < (dt - now).total_seconds() <= 600:
                                        await ch.send(content="@everyone 🕒 まもなく開始", embed=discord.Embed(title=e['summary'], description="開始10分前です。", color=0xe74c3c))
                                        reminded_ids.add(e['id'])
                        except: pass
            
            if len(reminded_ids) > 100: reminded_ids.clear()
            await asyncio.sleep(30)

    if not hasattr(bot, "_loops_started"):
        bot._loops_started = True
        asyncio.create_task(status_loop())
        asyncio.create_task(notification_loop())