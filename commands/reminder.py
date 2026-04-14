from discord import app_commands, ui
import discord
import asyncio
import os
import json
import requests
from datetime import datetime, timezone, timedelta
import re
import traceback
import random
import csv
from utils.layout_engine import layout_engine
from commands.attendance import AttendanceView 

# --- 設定項目 ---
JST = timezone(timedelta(hours=9))
SCOPES = ['https://www.googleapis.com/auth/calendar']
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

# ジャンル設定（通知の色や絵文字を決定）
GENRES = {
    "activity": {"label": "活動・練習", "emoji": "🎺", "tag": "[活動]", "color": 0x3498db},
    "meeting": {"label": "ミーティング", "emoji": "👥", "tag": "[会議]", "color": 0x2ecc71},
    "event": {"label": "本番・行事", "emoji": "✨", "tag": "[行事]", "color": 0xf1c40f},
    "important": {"label": "重要・締切", "emoji": "⚠️", "tag": "[重要]", "color": 0xe74c3c},
    "other": {"label": "その他", "emoji": "📝", "tag": "[他]", "color": 0x95a5a6}
}

WEATHER_CODES = {
    0: "☀️快晴", 1: "🌤️晴れ", 2: "⛅くもり", 3: "☁️曇り",
    45: "🌫️霧", 48: "🌫️霧", 51: "🚿小雨", 53: "🚿小雨", 55: "🚿小雨",
    61: "☔雨", 63: "☔雨", 65: "☔激しい雨", 71: "❄️雪", 73: "❄️雪", 75: "❄️激しい雪",
    80: "🌦️にわか雨", 81: "🌦️にわか雨", 82: "🌦️激しいにわか雨", 95: "⚡雷雨"
}

# --- 雑学取得関数 ---
def get_trivia():
    now = datetime.now(JST)
    # CSVのA列に合わせて「3/31」のような形式の文字列を作る
    today_str = f"{now.month}/{now.day}"
    
    # 雑学ファイルのパス（ファイル名は trivia.csv と仮定します）
    file_path = "trivia.csv" 
    
    if not os.path.exists(file_path):
        return None

    try:
        # エンコーディングは、Excelで作ったCSVなら 'utf-8-sig' か 'cp932' が一般的です
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2 and row[0] == today_str:
                    return row[1] # B列の雑学内容を返す
    except Exception as e:
        print(f"❌ 雑学取得エラー: {e}")
    return None

# --- ヘルパー関数 ---
def parse_extended_datetime(date_str, time_str):
    """25:00 などの表記を翌日として処理する"""
    base_dt = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=JST)
    time_str = time_str.replace('.', ':')
    match = re.match(r"(\d{1,2}):(\d{2})", time_str)
    if not match:
        raise ValueError("時間形式エラー")
    hours, minutes = map(int, match.groups())
    return base_dt + timedelta(days=(hours // 24)) + timedelta(hours=(hours % 24), minutes=minutes)

# --- 天気予報取得関数 ---
def get_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=31.9111&longitude=131.4239&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=Asia%2FTokyo"
        r = requests.get(url, timeout=5).json()
        forecast = {}
        for i, d in enumerate(r['daily']['time']):
            code = r['daily']['weathercode'][i]
            w_text = WEATHER_CODES.get(code, "❓")
            t_max = r['daily']['temperature_2m_max'][i]
            t_min = r['daily']['temperature_2m_min'][i]
            forecast[d] = f"{w_text} ({t_max}℃/{t_min}℃)"
        return forecast
    except:
        return {}
    
# --- 通知用Embed作成関数 ---
def create_daily_embed(now, weather_forecast, trivia, all_evs, is_test=False):
    today_str = now.strftime('%Y-%m-%d')
    wd = WEEKDAYS[now.weekday()]
    
    # 【修正】今日の天気だけをピンポイントで抽出
    today_weather = weather_forecast.get(today_str, "取得失敗")

    # 今日の予定を抽出・ソート
    today_evs = [e for e in all_evs if e['start'].get('dateTime', e['start'].get('date'))[:10] == today_str]
    today_evs.sort(key=lambda x: x['start'].get('dateTime', x['start'].get('date')))

    # 明日以降の予定（5件まで）
    future_evs = [e for e in all_evs if e['start'].get('dateTime', e['start'].get('date'))[:10] > today_str]
    future_evs.sort(key=lambda x: x['start'].get('dateTime', x['start'].get('date')))

    # タイトル作成
    title_text = f"🗓️ {now.month}/{now.day} ({wd}) の定期連絡"
    if is_test: title_text += " [TEST]"

    data = {
    "date": f"{now.month}/{now.day} ({WEEKDAYS[now.weekday()]})",
    "weather": today_weather,
    "trivia": get_trivia(),
    "today_events": today_evs,
    "future_events": future_evs
    }
    
    emb = layout_engine.build_embed(data, GENRES)
    
    return emb

# --- Google Calendar 管理クラス ---
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
    start_input = ui.TextInput(label="開始時間", placeholder="19:00", required=False)
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
        await it.response.send_modal(UniversalEditModal(self.gcal, self.cid, self.event_id, self.event_data.get('summary', ''), date_val, s_time, e_time))

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
        await it.response.edit_message(content=f"📅 **{selected_date}** の種類は？", view=genre_view)

    @ui.button(label="➕ 予定を追加", style=discord.ButtonStyle.success, emoji="📆")
    async def quick_add(self, it: discord.Interaction, button: ui.Button):
        data = self.dm.get_guild_data(it.guild_id)
        cids = data.get("calendar_ids", [])
        if not cids: return await it.response.send_message("❌ カレンダーを登録してください。", ephemeral=True)
        cid = cids[0] # 複数ある場合は1つ目に追加
        
        now = datetime.now(JST)
        date_view = ui.View()
        date_select = ui.Select(placeholder="日付を選ぶ...")
        for label, diff in [("今日", 0), ("明日", 1), ("明後日", 2), ("明々後日", 3), ("4日後", 4), ("5日後", 5), ("6日後", 6), ("来週の今日", 7)]:
            d = (now + timedelta(days=diff))
            date_select.add_option(label=f"{label} ({d.strftime('%m/%d')})", value=d.strftime('%Y-%m-%d'))
        
        async def date_callback(sit: discord.Interaction):
            await self.prompt_genre_selection(sit, cid, date_select.values[0])
        date_select.callback = date_callback
        date_view.add_item(date_select)
        await it.response.send_message("予定の追加：日付を選択", view=date_view, ephemeral=True)

    @ui.button(label="🔍 予定を確認", style=discord.ButtonStyle.primary, emoji="📋")
    async def list_events(self, it: discord.Interaction, button: ui.Button):
        await it.response.defer(ephemeral=True)
        data = self.dm.get_guild_data(it.guild_id)
        cids = data.get("calendar_ids", [])
        if not cids: return await it.followup.send("❌ カレンダー未登録です。", ephemeral=True)

        weather = get_weather()
        all_events = []
        for cid in cids:
            all_events.extend(self.gcal.get_events(cid, days=7))
        
        if not all_events: return await it.followup.send("✨ 予定はありません。", ephemeral=True)
        all_events.sort(key=lambda x: x['start'].get('dateTime', x['start'].get('date')))

        grouped = {}
        for e in all_events:
            d = e['start'].get('dateTime', e['start'].get('date'))[:10]
            if d not in grouped: grouped[d] = []
            grouped[d].append(e)

        embeds = []
        for d, evs in sorted(grouped.items())[:5]:
            dt = datetime.strptime(d, '%Y-%m-%d')
            emb = discord.Embed(title=f"📅 {dt.strftime('%m/%d')} ({WEEKDAYS[dt.weekday()]}) ｜ {weather.get(d, '')}", color=0x4285F4)
            lines = []
            for e in evs:
                st = e['start'].get('dateTime')
                t = f"`{st[11:16]}`" if st else "` 終日 `"
                lines.append(f"{t} **{e.get('summary', '無題')}**\n 　 ID: `{e['id']}`")
            emb.description = "\n".join(lines)
            embeds.append(emb)
        await it.followup.send(embeds=embeds, ephemeral=True)

    @ui.button(label="📝 編集/🗑️ 削除", style=discord.ButtonStyle.danger, emoji="⚙️")
    async def manage_event(self, it: discord.Interaction, button: ui.Button):
        data = self.dm.get_guild_data(it.guild_id)
        cids = data.get("calendar_ids", [])
        if not cids: return await it.response.send_message("❌ カレンダー未登録です。", ephemeral=True)

        class ManageModal(ui.Modal, title="予定の編集・削除"):
            ev_id_input = ui.TextInput(label="イベントIDを入力", required=True)
            def __init__(self, gcal, cid):
                super().__init__(); self.gcal, self.cid = gcal, cid
            async def on_submit(self, sit: discord.Interaction):
                raw_id = self.ev_id_input.value.strip().replace("`","")
                try:
                    event = self.gcal.service.events().get(calendarId=self.cid, eventId=raw_id).execute()
                    view = EditLaunchView(self.gcal, self.cid, raw_id, event)
                    
                    async def del_callback(dit: discord.Interaction):
                        self.gcal.service.events().delete(calendarId=self.cid, eventId=raw_id).execute()
                        await dit.response.edit_message(content="🗑️ 削除しました。", embed=None, view=None)
                    
                    del_btn = ui.Button(label="🗑️ 削除する", style=discord.ButtonStyle.danger)
                    del_btn.callback = del_callback
                    view.add_item(del_btn)
                    
                    emb = discord.Embed(title="🔍 予定を確認", description=f"予定名: **{event.get('summary')}**", color=0x3498db)
                    await sit.response.send_message(embed=emb, view=view, ephemeral=True)
                except: await sit.response.send_message("❌ IDが見つかりません。", ephemeral=True)
        
        await it.response.send_modal(ManageModal(self.gcal, cids[0]))

    @ui.button(label="📅 カレンダー設定", style=discord.ButtonStyle.gray, emoji="🔧")
    async def config_cal(self, it: discord.Interaction, button: ui.Button):
        class CalModal(ui.Modal, title="カレンダーIDの登録"):
            cid_input = ui.TextInput(label="GoogleカレンダーID", placeholder="example@group.calendar.google.com")
            def __init__(self, dm): super().__init__(); self.dm = dm
            async def on_submit(self, sit: discord.Interaction):
                d = self.dm.get_guild_data(sit.guild_id)
                if "calendar_ids" not in d: d["calendar_ids"] = []
                val = self.cid_input.value.strip()
                if val not in d["calendar_ids"]: d["calendar_ids"].append(val)
                await self.dm.save_all()
                await sit.response.send_message(f"✅ 追加しました: `{val}`", ephemeral=True)
        await it.response.send_modal(CalModal(self.dm))

# --- コマンド登録と通知ループ ---
def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self): super().__init__(name="rem", description="カレンダー管理")
        @app_commands.command(name="setup", description="通知先を設定")
        async def setup(self, it: discord.Interaction):
            data = data_manager.get_guild_data(it.guild_id)
            data["reminder"] = {"enabled": True, "channel_id": it.channel_id}
            await data_manager.save_all()
            await it.response.send_message(f"✅ <#{it.channel_id}> を通知先に設定しました。", ephemeral=True)

        @app_commands.command(name="menu", description="管理パネルを表示")
        async def menu(self, it: discord.Interaction):
            emb = discord.Embed(title="🗓️ カレンダー操作パネル", description="複数カレンダー対応・予定の管理が可能です。", color=0x4285F4)
            await it.response.send_message(embed=emb, view=ReminderMenuView(gcal, data_manager), ephemeral=True)

        @app_commands.command(name="test", description="【管理者用】通知テストを行います")
        async def rem_test(self, it: discord.Interaction):
            if not it.user.guild_permissions.manage_guild:
                return await it.response.send_message("管理者のみ実行可能です。", ephemeral=True)

            await it.response.defer(ephemeral=True)
            
            gid = str(it.guild_id)
            gdata = data_manager.get_guild_data(gid)
            cids = gdata.get("calendar_ids", [])
            target_ch_id = gdata.get("reminder", {}).get("channel_id")
            
            if not cids or not target_ch_id:
                return await it.followup.send("❌ 設定が足りません。")

            try:
                now = datetime.now(JST)
                today = now.strftime('%Y-%m-%d')
                # 全てのカレンダーから予定を取得
                all_evs = []
                for cid in cids:
                    all_evs.extend(gcal.get_events(cid, days=7))
                
                # 共通関数でEmbedを作成
                emb = create_daily_embed(now, get_weather(), get_trivia(), all_evs, is_test=True)
                
                target_ch = bot.get_channel(target_ch_id)
                if target_ch:
                    await target_ch.send(embed=emb)

                    # --- ここから追加：出欠確認パネルの送信 ---
                    att_emb = discord.Embed(
                        title=f"📝 {today} 出欠確認",
                        description="今日の活動に参加できるか、下のボタンを押して教えてください！ @everyone",
                        color=0x2ecc71 # 出席用の緑色
                    )
                    # AttendanceViewを初期化して送信
                    view = AttendanceView(data_manager, gid, today)
                    await target_ch.send(embed=att_emb, view=view)
                    # --- ここまで追加 ---

                    await it.followup.send(f"✅ <#{target_ch_id}> にテスト送信しました。")
            except Exception as e:
                print(traceback.format_exc())
                await it.followup.send(f"❌ エラー: `{e}`")

    bot.tree.add_command(Reminder())

    # --- ループ処理 ---
    async def status_loop():
        await bot.wait_until_ready()
        
        # 切り替えるステータスのリスト
        statuses = [
            "宮崎の空を監視中 ☁️",
            "ハッキング中．．．💻",
            "いたずら中... 😈",
            "競プロ練習中... 🎓",
            "数学の証明を考え中... 📐",
            "雑学収集中... 📚",
            "まーじゃん中... 🀄",
            "ゲーム中... 🎮"
        ]
        
        while not bot.is_closed():
            try:
                # リストの中からランダムに1つ選ぶ
                current_status = random.choice(statuses)
                await bot.change_presence(activity=discord.Game(name=current_status))
            except Exception as e:
                print(f"❌ ステータス更新エラー: {e}")
            
            # 1時間(180秒)ごとに切り替え
            await asyncio.sleep(180)

    async def notification_loop():
        await bot.wait_until_ready()
        reminded_ids = set()
        last_morning = ""
        while not bot.is_closed():
            now = datetime.now(JST)
            today = now.strftime('%Y-%m-%d')
            is_weekday = now.weekday() < 5
            for gid, gd in data_manager.data.items():
                r = gd.get("reminder", {})
                if not r.get("enabled"): continue
                ch = bot.get_channel(r.get("channel_id"))
                cids = gd.get("calendar_ids", [])
                if not ch or not cids: continue

                # 朝6時の通知
                if now.hour == 6 and now.minute == 0 and last_morning != today:
                    all_evs = []
                    for cid in cids:
                        all_evs.extend(gcal.get_events(cid, days=7))
                    
                    # 共通関数を呼び出し（is_testはデフォルトFalse）
                    emb = create_daily_embed(now, get_weather(), get_trivia(), all_evs)
                    
                    await ch.send(embed=emb)
                    
                    if is_weekday:
                        # --- ここから追加：出欠確認パネルの送信 ---
                        att_emb = discord.Embed(
                            title=f"📝 {today} 出欠確認",
                            description="今日の活動に参加できるか、下のボタンを押して教えてください！ @everyone",
                            color=0x2ecc71 # 出席用の緑色
                        )
                        # AttendanceViewを初期化して送信
                        view = AttendanceView(data_manager, gid, today)
                        await ch.send(embed=att_emb, view=view)
                        # --- ここまで追加 ---
                        
                        if gid == list(data_manager.data.keys())[-1]: 
                            last_morning = today

                # 10分前通知
                for cid in cids:
                    try:
                        for e in gcal.get_events(cid, days=1):
                            st = e['start'].get('dateTime')
                            if st and e['id'] not in reminded_ids:
                                dt = datetime.fromisoformat(st.replace('Z', '+00:00')).astimezone(JST)
                                if 0 < (dt - now).total_seconds() <= 605:
                                    summary = e.get('summary', '無題')
                                    color = 0xe74c3c
                                    for k, info in GENRES.items():
                                        if info["tag"] in summary: color = info["color"]; break
                                    await ch.send(content="🕒 10分前", embed=discord.Embed(title=summary, description="間もなく開始します。", color=color))
                                    reminded_ids.add(e['id'])
                    except: pass
            if len(reminded_ids) > 200: reminded_ids.clear()
            await asyncio.sleep(60)

    if not hasattr(bot, "_reminder_loops"):
        bot._reminder_loops = True
        asyncio.create_task(status_loop())
        asyncio.create_task(notification_loop())