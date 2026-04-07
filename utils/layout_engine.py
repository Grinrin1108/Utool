import os
import discord
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

class HTMLLayoutEngine:
    def __init__(self):
        self.template_dir = "templates"
        self.css_path = os.path.join(self.template_dir, "style.css")
        self.html_path = os.path.join(self.template_dir, "notification.html")

    def _get_css_var(self, var_name, default):
        """CSSファイルから変数の値を取得する簡易関数"""
        if not os.path.exists(self.css_path): return default
        with open(self.css_path, "r", encoding="utf-8") as f:
            for line in f:
                if var_name in line:
                    return line.split(":")[1].replace(";", "").strip().strip('"')
        return default

    def build_embed(self, data, genres_config):
        """
        HTML/CSSの構成を元に、Discord Embedを組み立てる
        """
        # CSSからデザイン設定を読み込む
        border = self._get_css_var("--border-style", "━━━━━━━━━━━━")
        color_hex = self._get_css_var("--primary-color", "#5865f2").replace("#", "")
        
        emb = discord.Embed(
            title=f"📅 {data['date']} の定期連絡",
            color=int(color_hex, 16)
        )

        # セクション1: インフォメーション
        info_val = f"> **🌡️ 天気**： {data['weather']}\n> **💡 雑学**： {data['trivia']}"
        emb.add_field(name=border, value=info_val, inline=False)

        # セクション2: 今日の予定（HTMLの構造をシミュレート）
        ev_lines = []
        for e in data['today_events']:
            st = e['start'].get('dateTime') or e['start'].get('date')
            time_str = datetime.fromisoformat(st.replace('Z', '+00:00')).astimezone(JST).strftime('%H:%M') if 'T' in st else " 終日 "
            
            summary = e.get('summary', '無題')
            emoji = "🔹"
            for k, info in genres_config.items():
                if info["tag"] in summary:
                    emoji = info["emoji"]; break
            ev_lines.append(f"{time_str} ┃ {emoji} {summary}")
        
        schedule_md = "```md\n" + ("\n".join(ev_lines) if ev_lines else "✨ 予定なし") + "\n```"
        emb.add_field(name="▽ Today's Schedule", value=schedule_md, inline=False)

        # セクション3: 週間予定
        weekly_lines = []
        for i, e in enumerate(data['future_events'][:5]):
            d_raw = e['start'].get('dateTime', e['start'].get('date'))[:10]
            d_dt = datetime.strptime(d_raw, '%Y-%m-%d')
            mark = "┗" if i == len(data['future_events'][:5]) - 1 else "┣"
            weekly_lines.append(f"{mark} {d_dt.strftime('%m/%d')}: {e.get('summary')}")
        
        weekly_md = "```\n" + ("\n".join(weekly_lines) if weekly_lines else "予定なし") + "\n```"
        emb.add_field(name="▽ Weekly Overview", value=weekly_md, inline=False)

        emb.set_footer(text="Have a nice day!")
        return emb

layout_engine = HTMLLayoutEngine()