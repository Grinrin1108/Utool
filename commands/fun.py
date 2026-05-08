import random
from discord import app_commands
import discord
import os
from google import genai # 新しいライブラリのインポート

# --- Gemini APIの初期設定 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    # 新しいクライアントの作り方
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

def register_fun_commands(bot):
    
    # 既存の /roll コマンド
    @bot.tree.command(name="roll", description="サイコロを振ります (例: 2d6)")
    async def roll(interaction: discord.Interaction, dice: str):
        await interaction.response.defer(ephemeral=True)
        try:
            rolls, limit = map(int, dice.lower().split('d'))
        except:
            await interaction.followup.send("形式が違います。例: `/roll 2d6`", ephemeral=True)
            return
        results = [random.randint(1, limit) for _ in range(rolls)]
        await interaction.followup.send(f"{interaction.user.mention} rolled {dice}: {results} → 合計: {sum(results)}", ephemeral=True)

    # 既存の /poll コマンド
    @bot.tree.command(name="poll", description="投票を作成します")
    async def poll(interaction: discord.Interaction, question: str, option1: str, option2: str, option3: str = None, option4: str = None):
        await interaction.response.defer(ephemeral=True)
        options = [opt for opt in [option1, option2, option3, option4] if opt]
        if len(options) < 2:
            await interaction.followup.send("選択肢は2つ以上必要です。", ephemeral=True)
            return
        emojis = ["1️⃣","2️⃣","3️⃣","4️⃣"]
        description = "\n".join(f"{emojis[i]} {opt}" for i,opt in enumerate(options))
        embed = discord.Embed(title=question, description=description, color=0x3498db)
        msg = await interaction.channel.send(embed=embed)
        for i in range(len(options)):
            await msg.add_reaction(emojis[i])
        await interaction.followup.send("✅ 投票を作成しました", ephemeral=True)

    # 🌟 メッセージの右クリックメニュー（AI添削）
    @bot.tree.context_menu(name="AIで面白く添削")
    async def funny_edit(interaction: discord.Interaction, message: discord.Message):
        await interaction.response.defer()

        original_text = message.content

        if not original_text:
            return await interaction.followup.send("📝 テキストがないメッセージは添削できないみたいです！", ephemeral=True)

        if not client:
            return await interaction.followup.send("❌ Gemini APIキーが設定されていません。`.env` を確認してください。", ephemeral=True)

        try:
            prompt = f"""
            あなたはDiscordサーバーのユーモアあふれるエンターテイナーです。
            以下のユーザーのメッセージを、面白おかしく添削、または強烈なツッコミを入れてください。
            
            【条件】
            ・口調は毎回ランダムに変えてください（例：ルー大柴風、中二病風、お嬢様風、関西弁のオカン風、武士風など）
            ・元のメッセージを引用しつつ、過剰に装飾したり、斜め上の解釈をしてください。
            ・サーバーのメンバーが笑えるような、愛のあるイジりにしてください。
            ・出力は添削結果の文章のみにしてください。
            
            【元のメッセージ】
            「{original_text}」
            """
            
            # 最新の非同期処理の呼び出し方（高速な gemini-2.5-flash モデルを使用）
            response = await client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            
            # 安全フィルターチェック
            if not response.text:
                return await interaction.followup.send("⚠️ 内容が過激すぎてAIの安全フィルターに止められました...！", ephemeral=True)
                
            edited_text = response.text

            # 文字数制限対策
            if len(edited_text) > 1800:
                edited_text = edited_text[:1800] + "\n...(長すぎたのでカットしたぜ！)"

            final_message = f"**🤖 AIによる {message.author.display_name} への添削結果**\n> {original_text}\n\n{edited_text}"
            await interaction.followup.send(final_message)

        except Exception as e:
            print(f"Gemini API Error: {e}")
            await interaction.followup.send(f"❌ AIの調子が悪いみたいです...\n（エラー原因: `{e}`）", ephemeral=True)