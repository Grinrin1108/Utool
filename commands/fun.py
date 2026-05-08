import random
from discord import app_commands
import discord
import os
from google import genai

# --- Gemini APIの初期設定 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

# --- 🌟 新機能：キャラ選択用ドロップダウンメニュー ---
class PersonaSelect(discord.ui.Select):
    def __init__(self, target_message: discord.Message):
        self.target_message = target_message
        
        # ユーザーが選べる選択肢リスト
        options = [
            discord.SelectOption(label="夏井先生風", description="容赦ない辛口添削と才能査定", emoji="👘"),
            discord.SelectOption(label="中二病風", description="闇の力が目覚めそうな痛いセリフ", emoji="🗡️"),
            discord.SelectOption(label="ジョジョ風", description="奇妙な擬音と独特な言い回し", emoji="🌟"),
            discord.SelectOption(label="お嬢様風", description="優雅で高飛車な口調でございますわ", emoji="☕"),
            discord.SelectOption(label="関西弁のオカン風", description="世話焼きでちょっとお節介なツッコミ", emoji="🍳"),
            discord.SelectOption(label="武士風", description="義理人情に厚い侍言葉でござる", emoji="⚔️"),
            discord.SelectOption(label="ランダム", description="AIの気分に任せる", emoji="🎲")
        ]
        super().__init__(placeholder="添削のスタイルを選んでください...", min_values=1, max_values=1, options=options)

    # ユーザーがメニューを選んだ時の処理
    async def callback(self, interaction: discord.Interaction):
        # 処理中...の表示を出す（これがないと3秒でエラーになります）
        await interaction.response.defer(ephemeral=True)

        persona = self.values[0]
        original_text = self.target_message.content

        prompt = f"""
        あなたはDiscordサーバーのユーモアあふれるエンターテイナーです。
        以下のユーザーのメッセージを、「{persona}」のキャラクターになりきって面白おかしく添削、または強烈なツッコミを入れてください。
        
        【条件】
        ・元のメッセージを引用しつつ、過剰に装飾したり、斜め上の解釈をしてください。
        ・サーバーのメンバーが笑えるような、愛のあるイジりにしてください。
        ・出力は添削結果の文章のみにしてください。（挨拶などは不要です）
        
        【元のメッセージ】
        「{original_text}」
        """

        try:
            # 最新の非同期処理の呼び出し方
            response = await client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            
            if not response.text:
                return await interaction.followup.send("⚠️ 安全フィルターに止められました...！", ephemeral=True)
                
            edited_text = response.text
            if len(edited_text) > 1800:
                edited_text = edited_text[:1800] + "\n...(長すぎたのでカットしたぜ！)"

            # パブリック（みんなが見える）チャンネルに結果を送信
            final_message = f"**🤖 AIによる {self.target_message.author.display_name} への添削結果（{persona}）**\n> {original_text}\n\n{edited_text}"
            await interaction.channel.send(final_message)
            
            # ドロップダウンメニューのメッセージを消してスッキリさせる
            await interaction.delete_original_response()

        except Exception as e:
            print(f"Gemini API Error: {e}")
            await interaction.followup.send(f"❌ AIの調子が悪いみたいです...\n（エラー原因: `{e}`）", ephemeral=True)

class PersonaView(discord.ui.View):
    def __init__(self, target_message: discord.Message):
        super().__init__(timeout=60) # 60秒でメニューが消えるように設定
        self.add_item(PersonaSelect(target_message))


# --- コマンド登録部分 ---
def register_fun_commands(bot):
    
    # /roll コマンド
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

    # /poll コマンド
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

    # 🌟 メッセージの右クリックメニュー
    @bot.tree.context_menu(name="AIで面白く添削")
    async def funny_edit(interaction: discord.Interaction, message: discord.Message):
        if not message.content:
            return await interaction.response.send_message("📝 テキストがないメッセージは添削できないみたいです！", ephemeral=True)

        if not client:
            return await interaction.response.send_message("❌ Gemini APIキーが設定されていません。`.env` を確認してください。", ephemeral=True)

        # 実行した人にだけ見えるドロップダウンメニューを送信
        view = PersonaView(message)
        await interaction.response.send_message("どのスタイルで添削しますか？", view=view, ephemeral=True)