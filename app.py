import os
import re
import pandas as pd
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage

# 載入環境變數
load_dotenv()
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

# 初始化 Flask 與 LINE Bot
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 載入遊戲資料
bigwinboard_df = pd.read_csv("bigwinboard_slots_with_full_features_with_similar.csv")
demoslot_df = pd.read_csv("demoslot_games_full_data.csv")

if "Score" in bigwinboard_df.columns:
    bigwinboard_df = bigwinboard_df.sort_values(by="Score", ascending=False, na_position='last').reset_index(drop=True)
if "Score" in demoslot_df.columns:
    demoslot_df = demoslot_df.sort_values(by="Score", ascending=False, na_position='last').reset_index(drop=True)

STAT_FIELDS = [
    ("Reels", "🌀 Reels"),
    ("Rows", "🌀 Rows"),
    ("Paylines", "📈 Paylines"),
    ("Hit Freq", "🎯 Hit Freq"),
    ("Free Spins Freq", "🎯 Free Spins Freq"),
    ("Max Win", "💰 Max Win"),
    ("Max Win Probability", "📊 Max Win Probability"),
    ("Volatility", "⚖️ Volatility"),
    ("Min/Max Bet", "💵 Min/Max Bet"),
    ("Release Date", "🗓️ Release Date")
]

SUPPORTED_FEATURES = [
    "tumble", "cascade", "sticky", "multiplier", "bonus buy", "jackpot",
    "megaways", "cluster", "free spins", "walking wild", "expanding symbol"
]

def format_game_stats(row) -> str:
    lines = []
    for key, label in STAT_FIELDS:
        value = row.get(key)
        if pd.notna(value):
            lines.append(f"{label}: {value}")
    return "\n".join(lines)

def analyze_game_features(description: str) -> str:
    desc = description.lower()
    features = {
        "🎲 基本玩法": [],
        "💥 特色機制": [],
        "🛠️ 功能特色": []
    }
    if re.search(r"\d+x\d+", desc):
        match = re.search(r"\d+x\d+", desc)
        features["🎲 基本玩法"].append(f"格子組合：{match.group()}")
    if "cluster pays" in desc:
        features["🎲 基本玩法"].append("Cluster Pays")
    if "megaways" in desc:
        features["🎲 基本玩法"].append("Megaways")
    if "ways to win" in desc:
        features["🎲 基本玩法"].append("多線中獎")

    if "tumble" in desc or "cascade" in desc:
        features["💥 特色機制"].append("滾落/連擊機制")
    if "expanding symbol" in desc:
        features["💥 特色機制"].append("擴展符號")
    if "sticky" in desc:
        features["💥 特色機制"].append("黏性符號")
    if "walking wild" in desc:
        features["💥 特色機制"].append("移動 wild")

    if "free spin" in desc:
        features["🛠️ 功能特色"].append("免費旋轉")
    if "multiplier" in desc:
        features["🛠️ 功能特色"].append("乘數機制")
    if "bonus buy" in desc or "buy feature" in desc:
        features["🛠️ 功能特色"].append("購買功能")
    if "jackpot" in desc:
        features["🛠️ 功能特色"].append("獎池/大獎")

    summary = []
    for section, items in features.items():
        if items:
            summary.append(f"{section}：\n• " + "\n• ".join(items))
    return "\n\n".join(summary) if summary else "⚠️ 無法從描述中解析出玩法資訊。"

def get_supported_mechanisms() -> str:
    return "🎮 可查詢的機制類型包括：\n" + "\n".join([f"• {kw}" for kw in SUPPORTED_FEATURES])

def get_supported_commands() -> str:
    return (
        "📘 支援指令一覽：\n"
        "• 查遊戲 xxx\n"
        "• 查機制 xxx\n"
        "• 查機制（列出支援類型）\n"
        "• 查指令"
    )

def search_feature(keyword: str) -> str:
    matched = bigwinboard_df[bigwinboard_df['Description'].str.contains(keyword, case=False, na=False)]
    if matched.empty:
        return f"❌ 找不到包含「{keyword}」機制的遊戲。"
    titles = matched['Title'].head(10).tolist()
    return f"🎮 包含「{keyword}」機制的遊戲：\n" + "\n".join([f"• {title}" for title in titles])

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    print("📩 收到 LINE 請求")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_input = event.message.text.strip()

    if user_input.startswith("查遊戲"):
        keyword = user_input.replace("查遊戲", "").strip()
        if not keyword:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入遊戲名稱，例如：查遊戲 bonanza"))
            return
        matches = bigwinboard_df[bigwinboard_df['Title'].str.contains(keyword, case=False, na=False)].head(5)
        reply_batches = []

        for _, row in matches.iterrows():
            # 文字區塊
            texts = [f"🎰 遊戲：{row['Title']}"]
            if pd.notna(row.get("RTP")):
                texts.append(f"🎯 RTP：{row['RTP']}")
            if pd.notna(row.get("URL")):
                texts.append(f"🔗 {row['URL']}")
            if pd.notna(row.get("Description")):
                desc = row["Description"]
                texts.append(f"📖 遊戲簡介：\n{desc[:120]}{'...' if len(desc)>120 else ''}")
                texts.append("🔍 玩法說明：\n" + analyze_game_features(desc))
            texts.append(format_game_stats(row))

            if pd.notna(row.get("Similar Titles")):
                similar = row["Similar Titles"]
                texts.append("🔁 類似遊戲推薦：\n" + "\n".join(f"• {t.strip()}" for t in similar.split(",")[:5]))

            # 將文字訊息加入批次
            reply_batches.append(TextSendMessage("\n\n".join(texts)))

            # 如果有圖片，加入圖片訊息
            if pd.notna(row.get("Image URL")):
                image_url = row["Image URL"]
                reply_batches.append(ImageSendMessage(
                    original_content_url=image_url,
                    preview_image_url=image_url
                ))

        if reply_batches:
            # 回傳最多 5 則訊息（LINE 限制）
            line_bot_api.reply_message(event.reply_token, reply_batches[:5])
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"找不到「{keyword}」相關的遊戲。"))
        return

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
