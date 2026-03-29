from discord import app_commands
import discord

def register_help_command(bot):
    @bot.tree.command(name="help", description="Botの使い方（説明書）を表示します")
    async def help_command(interaction: discord.Interaction):
        embed = discord.Embed(
            title="📌 運営支援Bot 使いかたガイド",
            description="このBotは、予定の管理や通知を自動で行い、みんなの活動をサポートします！",
            color=0x3498db # 清潔感のある青色
        )

        # ステップ1：どうすれば通知が来るか
        embed.add_field(
            name="1️⃣ 予定の入れかた（Googleカレンダー）",
            value=(
                "①`/rem menu` と入力\n"
                "②表示されたメニューからやりたいものを選択\n"
                "③メニューに沿って選択\n"
                "カレンダーの予定名の先頭に以下の文字を入れると、Botが自動で色分けして分かりやすくしてくれます。\n"
                "┣ `[活動]` … 🎺 **練習・通常活動**（青色の通知）\n"
                "┣ `[会議]` … 👥 **ミーティング**（緑色の通知）\n"
                "┣ `[行事]` … ✨ **本番・イベント**（金色の通知）\n"
                "┗ `[重要]` … ⚠️ **提出期限・重要事項**（赤色の通知）"
            ),
            inline=False
        )

        # ステップ2：魔法のタグ（ここが一番重要）
        embed.add_field(
            name="2️⃣ 通知機能",
            value=(
                "┃ **朝 7:00** ―― 今日の予定を一覧で投稿します。\n"
                "┃ **開始10分前** ―― `@everyone` で開始をお知らせします。"
            ),
            inline=False
        )

        # ステップ3：その他の便利機能
        embed.add_field(
            name="3️⃣ 知っておくと便利なコマンド",
            value=(
                "**`/poll`** … 簡単にアンケートが取れます（2〜4択）。\n"
                "**`/roll`** … 迷った時のサイコロ。（例：`/roll 1d10`）\n"
                "**`/userinfo`** … サーバーに入った日などを確認できます。\n"
                "**`/help`** … いつでもこの説明を見返せます！"
            ),
            inline=False
        )

        # おまけ情報
        embed.add_field(
            name="☀️ おまけ",
            value="毎朝の通知と一緒に、**宮崎市の天気予報**もお知らせします。傘が必要かチェックしてね！",
            inline=False
        )

        embed.set_footer(text="※使い方がわからない場合は、管理者`@grinrin`に聞いてくださいね。")
        
        # ユーザーにだけ見えるようにしたい場合は ephemeral=True を追加
        await interaction.response.send_message(embed=embed, ephemeral=True)