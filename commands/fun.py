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
    def __init__(self, target_message: discord.Message, action_type: str):
        self.target_message = target_message
        self.action_type = action_type # "添削" または "全肯定"
        
        # モード（添削か全肯定か）によって、メニューの説明文を変化させる
        options_config = [
            {
                "label": "夏井先生風",
                "emoji": "👘",
                "desc_edit": "容赦ない辛口添削と才能査定",
                "desc_affirm": "どんな内容でも特待生並みに大絶賛"
            },
            {
                "label": "中二病風",
                "emoji": "🗡️",
                "desc_edit": "闇の力が目覚めそうな痛いセリフ",
                "desc_affirm": "選ばれし勇者として崇め奉る"
            },
            {
                "label": "ジョジョ風",
                "emoji": "🌟",
                "desc_edit": "奇妙な擬音と独特な言い回しでツッコミ",
                "desc_affirm": "スゲーッ！と奇妙な擬音で全力賛美"
            },
            {
                "label": "お嬢様風",
                "emoji": "☕",
                "desc_edit": "優雅で高飛車な口調でございますわ",
                "desc_affirm": "素晴らしいお方ですわ！と優雅に拍手喝采"
            },
            {
                "label": "関西弁のオカン風",
                "emoji": "🍳",
                "desc_edit": "世話焼きでちょっとお節介なツッコミ",
                "desc_affirm": "あんたはホンマに天才や！とベタ褒め"
            },
            {
                "label": "武士風",
                "emoji": "⚔️",
                "desc_edit": "義理人情に厚い侍言葉でござる",
                "desc_affirm": "天晴れなり！と武士の魂で大絶賛"
            },
            {
                "label": "おじさん構文風",
                "emoji": "👴",
                "desc_edit": "絵文字たっぷりのねっとりした長文でツッコミ😅💦",
                "desc_affirm": "絵文字乱舞で〇〇チャンをひたすら褒めちぎるヨ❗"
            },
            {
                "label": "呪術廻戦の禪院直哉風",
                "emoji": "🦊",
                "desc_edit": "呪術廻戦の禪院直哉風にプライド激高の京都弁で上から目線で煽る",
                "desc_affirm": "呪術廻戦の禪院直哉風に上から目線の傲慢な京都弁やけど実はめっちゃ認めてる"
            },
            {
                "label": "ランダム",
                "emoji": "🎲",
                "desc_edit": "AIの気分に任せる",
                "desc_affirm": "AIの気分に任せる"
            }
        ]

        options = [
            discord.SelectOption(
                label=cfg["label"], 
                description=cfg["desc_edit"] if action_type == "添削" else cfg["desc_affirm"], 
                emoji=cfg["emoji"]
            ) for cfg in options_config
        ]

        super().__init__(placeholder=f"{action_type}のスタイルを選んでください...", min_values=1, max_values=1, options=options)

    # ユーザーがメニューを選んだ時の処理
    async def callback(self, interaction: discord.Interaction):
        # 処理中...の表示を出す
        await interaction.response.defer(ephemeral=True)

        persona = self.values[0]
        original_text = self.target_message.content

        # 添削と全肯定でAIへの指示（プロンプト）を切り替える
        if self.action_type == "添削":
            prompt_instruction = "面白おかしく添削、または強烈なツッコミを入れてください。"
            condition_extra = "・元のメッセージを引用しつつ、過剰に装飾したり、斜め上の解釈をしてください。\n・サーバーのメンバーが笑えるような、愛のあるイジりにしてください。"
        else:
            prompt_instruction = "どんな内容でも【全力で全肯定】し、相手を限界まで褒めちぎってください。"
            condition_extra = "・元のメッセージを引用しつつ、強引なまでに素晴らしい点を見つけて褒めてください。\n・否定、ツッコミ、ダメ出しは一切禁止です。すべてを肯定し、相手を最高にポジティブな気持ちにさせてください。"

        prompt = f"""
        あなたはDiscordサーバーのユーモアあふれるエンターテイナーです。
        以下のユーザーのメッセージを、「{persona}」のキャラクターになりきって{prompt_instruction}
        
        【条件】
        {condition_extra}
        ・出力は結果の文章のみにしてください。（挨拶などは不要です）
        
        【元のメッセージ】
        「{original_text}」
        """

        try:
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
            final_message = f"**🤖 AIによる {self.target_message.author.display_name} への{self.action_type}結果（{persona}）**\n> {original_text}\n\n{edited_text}"
            await interaction.channel.send(final_message)
            
            # ドロップダウンメニューのメッセージを消してスッキリさせる
            await interaction.delete_original_response()

        except Exception as e:
            print(f"Gemini API Error: {e}")
            await interaction.followup.send(f"❌ AIの調子が悪いみたいです...\n（エラー原因: `{e}`）", ephemeral=True)

class PersonaView(discord.ui.View):
    def __init__(self, target_message: discord.Message, action_type: str):
        super().__init__(timeout=60) # 60秒でメニューが消えるように設定
        self.add_item(PersonaSelect(target_message, action_type))


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

    # 🌟 右クリックメニュー1：AIで面白く添削
    @bot.tree.context_menu(name="AIで面白く添削")
    async def funny_edit(interaction: discord.Interaction, message: discord.Message):
        # 最初に「考え中...」状態にして、3秒でタイムアウトするのを防ぐ
        await interaction.response.defer(ephemeral=True)
        
        if not message.content:
            return await interaction.followup.send("📝 テキストがないメッセージは処理できないみたいです！")
        if not client:
            return await interaction.followup.send("❌ Gemini APIキーが設定されていません。")

        view = PersonaView(message, "添削")
        await interaction.followup.send("どのスタイルで【添削】しますか？", view=view)

    # 🌟 右クリックメニュー2：AIで全肯定
    @bot.tree.context_menu(name="AIで全肯定")
    async def funny_affirm(interaction: discord.Interaction, message: discord.Message):
        # 最初に「考え中...」状態にして、3秒でタイムアウトするのを防ぐ
        await interaction.response.defer(ephemeral=True)
        
        if not message.content:
            return await interaction.followup.send("📝 テキストがないメッセージは処理できないみたいです！")
        if not client:
            return await interaction.followup.send("❌ Gemini APIキーが設定されていません。")

        view = PersonaView(message, "全肯定")
        await interaction.followup.send("どのスタイルで【全肯定】しますか？", view=view)