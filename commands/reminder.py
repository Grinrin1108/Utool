# commands/reminder.py
from discord import app_commands, ui
import discord
import asyncio
import os
import json
import requests
from datetime import datetime, timezone, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- 基本設定 ---
JST = timezone(timedelta(hours=9))
SCOPES = ['https://www.googleapis.com/auth/calendar']
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

WEATHER_CODES = {
    0: "☀️快晴", 1: "🌤️晴れ", 2: "⛅くもり", 3: "☁️曇り",
    45: "🌫️霧", 48: "🌫️霧", 51: "🚿小雨", 53: "🚿小雨", 55: "🚿小雨",
    61: "☔雨", 63: "☔雨", 65: "☔激しい雨", 71: "❄️雪", 73: "❄️雪", 75: "❄️激しい雪",
    80: "🌦️にわか雨", 81: "🌦️にわか雨", 82: "🌦️激しいにわか雨", 95: "⚡雷雨"
}

# --- 解析ユーティリティ ---
def get_weather():
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=35.6895&longitude=139.6917&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=Asia%2FTokyo").json()
        forecast = {}
        for i, d in enumerate(r['daily']['time']):
            forecast[d] = f"{WEATHER_CODES.get(r['daily']['weathercode'][i], '❓')} ({r['daily']['temperature_2m_max'][i]}℃/{r['daily']['temperature_2m_min'][i]}℃)"
        return forecast
    except: return {}

# --- Google Calendar Manager ---
class GoogleCalendarManager:
    def __init__(self):
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            try:
                info = json.loads(creds_json)
                self.creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
                self.service = build('calendar', 'v3', credentials=self.creds)
            except: self.service = None
        else: self.service = None

    def get_events(self, calendar_id, days=7):
        if not self.service: return []
        now = datetime.now(JST)
        time_min = now.replace(hour=0, minute=0, second=0).isoformat()
        time_max = (now + timedelta(days=days)).replace(hour=23, minute=59, second=59).isoformat()
        try:
            res = self.service.events().list(calendarId=calendar_id, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
            return res.get('items', [])
        except: return []

    def add_event(self, calendar_id, title, date_str, start_time=None, end_time=None):
        # date_str は "2024-05-20" の形式
        if start_time:
            # 開始時間の作成
            s_dt = datetime.strptime(f"{date_str} {start_time}", '%Y-%m-%d %H:%M').replace(tzinfo=JST)
            
            if end_time:
                # 終了時間の作成
                e_dt = datetime.strptime(f"{date_str} {end_time}", '%Y-%m-%d %H:%M').replace(tzinfo=JST)
                
                # 【重要】日またぎ（翌日）の判定
                # 終了時刻が開始時刻より前なら、翌日の予定として処理する
                if e_dt <= s_dt:
                    e_dt += timedelta(days=1)
            else:
                # 終了時間がなければ1時間後に設定
                e_dt = s_dt + timedelta(hours=1)
            
            body = {
                'summary': title,
                'start': {'dateTime': s_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
                'end': {'dateTime': e_dt.isoformat(), 'timeZone': 'Asia/Tokyo'}
            }
        else:
            # 終日の予定
            body = {
                'summary': title,
                'start': {'date': date_str},
                'end': {'date': (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')}
            }
        return self.service.events().insert(calendarId=calendar_id, body=body).execute()

# --- インタラクティブUIパーツ ---

class AddEventModal(ui.Modal, title="予定の入力"):
    event_title = ui.TextInput(label="タイトル", placeholder="例: 深夜のゲーム大会", required=True)
    start_t = ui.TextInput(label="開始時間 (24時間表記)", placeholder="23:00", min_length=4, max_length=5, required=False)
    end_t = ui.TextInput(label="終了時間 (日をまたぐ場合は 01:00 のように入力)", placeholder="01:30", min_length=4, max_length=5, required=False)

    def __init__(self, gcal, cid, date_val, date_label):
        super().__init__()
        self.gcal, self.cid, self.date_val, self.date_label = gcal, cid, date_val, date_label

    async def on_submit(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        try:
            # 時間のコロン抜けを補完する程度の簡易ケア
            st = self.start_t.value.replace(".", ":") if self.start_t.value else None
            et = self.end_t.value.replace(".", ":") if self.end_t.value else None
            
            self.gcal.add_event(self.cid, self.event_title.value, self.date_val, st, et)
            
            msg = f"✅ **{self.event_title.value}** を登録しました！\n📅 日付: {self.date_label}"
            if st: msg += f"\n⏰ 時間: {st} 〜 {et if et else '(1時間)'}"
            await it.followup.send(msg, ephemeral=True)
        except Exception as e:
            await it.followup.send(f"❌ 入力形式が正しくありません。\n時間は `14:00` や `01:30` のように入力してください。", ephemeral=True)

class ReminderMenuView(ui.View):
    def __init__(self, gcal, dm):
        super().__init__(timeout=None)
        self.gcal, self.dm = gcal, dm

    @ui.button(label="➕ 予定を追加", style=discord.ButtonStyle.success, emoji="📝")
    async def add_btn(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        if not cid: return await it.response.send_message("❌ 先に `/rem on カレンダーID` で設定を完了してください。", ephemeral=True)

        # --- カレンダー感覚の日付選択メニュー ---
        view = ui.View()
        select = ui.Select(placeholder="カレンダーから日付を選択...")
        
        now = datetime.now(JST)
        # 今日から14日分の日付をリスト化
        for i in range(14):
            target = now + timedelta(days=i)
            val = target.strftime('%Y-%m-%d')
            # 表示用ラベル (例: 05/20 (月) 今日)
            label = target.strftime('%m/%d') + f" ({WEEKDAYS[target.weekday()]})"
            if i == 0: label += " 【今日】"
            elif i == 1: label += " 【明日】"
            
            select.add_option(label=label, value=val, description=f"{val}")

        async def select_callback(sit: discord.Interaction):
            # 選んだ日付のラベルを取得
            chosen_label = [opt.label for opt in select.options if opt.value == select.values[0]][0]
            await sit.response.send_modal(AddEventModal(self.gcal, cid, select.values[0], chosen_label))

        select.callback = select_callback
        view.add_item(select)
        await it.response.send_message("まずは **日付** を選んでください：", view=view, ephemeral=True)

    @ui.button(label="📅 予定を確認", style=discord.ButtonStyle.primary, emoji="🔍")
    async def list_btn(self, it: discord.Interaction, button: ui.Button):
        await it.response.defer(ephemeral=True)
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        events = self.gcal.get_events(cid)
        weather = get_weather()
        
        embed = discord.Embed(title="🗓️ 直近1週間のスケジュール", color=0x4285F4)
        if not events:
            embed.description = "予定は入っていません。ゆっくり過ごしましょう！"
        else:
            grouped = {}
            for e in events:
                d = e['start'].get('dateTime', e['start'].get('date'))[:10]
                if d not in grouped: grouped[d] = []
                grouped[d].append(e)
            
            for d, evs in sorted(grouped.items()):
                dt = datetime.strptime(d, '%Y-%m-%d')
                w = weather.get(d, "")
                field_name = f"📅 {dt.strftime('%m/%d')}({WEEKDAYS[dt.weekday()]}) {w}"
                lines = []
                for e in evs:
                    st = e['start'].get('dateTime', "終日")
                    time_str = f"`{st[11:16]}`" if ":" in st else "☀️ `終日`"
                    lines.append(f"{time_str} **{e['summary']}**\n└ `{e['id']}`")
                embed.add_field(name=field_name, value="\n".join(lines) + "\n\u200b", inline=False)
        
        embed.set_footer(text="IDをコピーして下の『予定を削除』ボタンから消去できます")
        await it.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="🗑️ 予定を削除", style=discord.ButtonStyle.danger, emoji="🧹")
    async def delete_btn(self, it: discord.Interaction, button: ui.Button):
        cid = self.dm.get_guild_data(it.guild_id).get("google_calendar_id")
        
        class DelModal(ui.Modal, title="予定の削除"):
            ev_id = ui.TextInput(label="イベントIDを貼り付けてください", placeholder="一覧からコピーしたIDをここにペースト", required=True)
            def __init__(self, gcal, cid):
                super().__init__()
                self.gcal, self.cid = gcal, cid
            async def on_submit(self, sit: discord.Interaction):
                try:
                    self.gcal.service.events().delete(calendarId=self.cid, eventId=self.ev_id.value).execute()
                    await sit.response.send_message(f"🗑️ 予定（ID: {self.ev_id.value[:10]}...）を削除しました。", ephemeral=True)
                except: await sit.response.send_message("❌ 削除に失敗しました。IDが正しいか確認してください。", ephemeral=True)
        
        await it.response.send_modal(DelModal(self.gcal, cid))

# --- コマンド登録 ---
def register_reminder_commands(bot, data_manager):
    gcal = GoogleCalendarManager()

    class Reminder(app_commands.Group):
        def __init__(self): super().__init__(name="rem", description="Googleカレンダー連携操作")

        @app_commands.command(name="menu", description="直感的な操作パネルを開きます")
        async def menu(self, it: discord.Interaction):
            now = datetime.now(JST)
            embed = discord.Embed(
                title="🗓️ カレンダー操作パネル",
                description=f"現在は **{now.strftime('%Y/%m/%d')} ({WEEKDAYS[now.weekday()]})** です。\n下のボタンから操作を選んでください。",
                color=0x4285F4
            )
            embed.add_field(name="使い方", value="1. `➕ 予定を追加` を押す\n2. カレンダー(リスト)から日付を選ぶ\n3. 内容と時間を入力（日またぎ対応！）", inline=False)
            await it.response.send_message(embed=embed, view=ReminderMenuView(gcal, data_manager))

        @app_commands.command(name="on", description="初期設定：カレンダーIDを登録して通知を有効化")
        async def on(self, it: discord.Interaction, calendar_id: str):
            data = data_manager.get_guild_data(it.guild_id)
            data["google_calendar_id"] = calendar_id
            data["reminder"] = {"enabled": True, "channel_id": it.channel_id}
            await data_manager.save_all()
            await it.response.send_message(f"✅ 設定完了！このチャンネルで通知を行います。\n`/rem menu` で予定の管理を始めましょう。")

    bot.tree.add_command(Reminder())

    # --- バックグラウンド通知ループ ---
    async def loop():
        await bot.wait_until_ready()
        reminded_ids = set()
        while not bot.is_closed():
            now = datetime.now(JST)
            # 朝6時の定期通知
            if now.hour == 6 and now.minute == 0:
                weather = get_weather()
                for gid, gdata in data_manager.data.items():
                    r = gdata.get("reminder", {})
                    if r.get("enabled"):
                        ch, cid = bot.get_channel(r.get("channel_id")), gdata.get("google_calendar_id")
                        if ch and cid:
                            evs = gcal.get_events(cid, days=1)
                            embed = discord.Embed(title=f"☀️ {now.strftime('%m/%d')} 今日の予定", color=0x4285F4)
                            w = weather.get(now.strftime('%Y-%m-%d'), "")
                            lines = [f"・`{e['start'].get('dateTime', '  終日  ')[11:16]}` {e['summary']}" for e in evs]
                            embed.description = f"今日の天気: **{w}**\n\n" + ("\n".join(lines) if lines else "今日の予定はありません。")
                            await ch.send(embed=embed)
                await asyncio.sleep(60)

            # 10分前のリマインド
            for gid, gdata in data_manager.data.items():
                r = gdata.get("reminder", {})
                if r.get("enabled"):
                    ch, cid = bot.get_channel(r.get("channel_id")), gdata.get("google_calendar_id")
                    if ch and cid:
                        try:
                            for e in gcal.get_events(cid, days=1):
                                st = e['start'].get('dateTime')
                                if st and e['id'] not in reminded_ids:
                                    start_dt = datetime.fromisoformat(st.replace('Z', '+00:00')).astimezone(JST)
                                    diff = (start_dt - now).total_seconds()
                                    if 540 < diff <= 600: # 10分〜9分前
                                        await ch.send(f"🕒 **10分前リマインド**\n**{e['summary']}** がまもなく始まります！", content="@everyone")
                                        reminded_ids.add(e['id'])
                        except: pass
            
            if len(reminded_ids) > 100: reminded_ids.clear()
            await asyncio.sleep(30)

    if not hasattr(bot, "_rem_loop_v2"):
        bot._rem_loop_v2 = True
        asyncio.create_task(loop())
