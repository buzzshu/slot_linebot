import os
import re
import pandas as pd
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage

# 初始化
load_dotenv()
app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 載入資料
bigwinboard_df = pd.read_csv("bigwinboard_slots_with_full_features_with_similar.csv")
if "Score" in bigwinboard_df.columns:
    bigwinboard_df = bigwinboard_df.sort_values(by="Score", ascending=False).reset_index(drop=True)

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

def format_game_stats(row):
    lines = []
    for key, label in STAT_FIELDS:
        if pd.notna(row.get(key, "")):
            lines.append(f"{label}: {row[key]}")
    return "\n".join(lines)

def analyze_game_features(description: str) -> str:
    desc = description.lower()
    features = {
        "🎲 基本玩法": [],
        "💥 特色機制": [],
        "🛠️ 功能特色": []
    }

    if match := re.search(r"\d+\s*[xX]\s*\d+", desc):
        features["🎲 基本玩法"].append(f"格子組合：{match.group().replace(' ', '')}")
    if "cluster pays" in desc:
        features["🎲 基本玩法"].append("Cluster Pays")
    if "megaways" in desc:
        features["🎲 基本玩法"].append("Megaways")
    if "ways to win" in desc:
        features["🎲 基本玩法"].append("多線中獎")
    if any(w in desc for w in ["tumble", "cascade"]):
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
    return "\n\n".join(summary)

def get_supported_mechanisms():
    return "🎮 可查詢的機制類型包括：\n" + "\n".join([f"• {kw}" for kw in SUPPORTED_FEATURES])

def get_supported_commands():
    return (
        "📘 支援指令一覽：\n"
        "• 查遊戲 xxx\n"
        "• 查機制 xxx\n"
        "• 查機制（列出支援類型）\n"
        "• 查指令"
    )

def search_game(keyword: str) -> list:
    matches = bigwinboard_df[bigwinboard_df['Title'].str.contains(keyword, case=False, na=False)].head(5)
    results = []
    for _, row in matches.iterrows():
        parts = [f"🎰 遊戲：{row['Title']}"]
        if pd.notna(row.get('RTP')):
            parts.append(f"🎯 RTP：{row['RTP']}")
        if pd.notna(row.get('URL')):
            parts.append(f"🔗 {row['URL']}")
        if pd.notna(row.get("Description")):
            parts.append(f"📖 遊戲簡介：\n{row['Description'][:100]}...")

        if pd.notna(row.get("Image URL")):
            results.append(ImageSendMessage(original_content_url=row["Image URL"], preview_image_url=row["Image URL"]))

        parts.append("🔍 玩法說明：\n" + analyze_game_features(row.get("Description", "")))
        parts.append(format_game_stats(row))

        if pd.notna(row.get("Similar Titles")):
            parts.append("🔁 類似遊戲推薦：\n" + row["Similar Titles"])
        results.append(TextSendMessage("\n\n".join(parts[:5])))  # 避免超出 LINE 限制
    return results

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
        replies = search_game(keyword)
        if replies:
            for reply in replies[:5]:
                line_bot_api.reply_message(event.reply_token, reply)
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"找不到「{keyword}」相關的遊戲。"))
        return

    elif user_input.startswith("查機制"):
        keyword = user_input.replace("查機制", "").strip()
        if not keyword:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=get_supported_mechanisms()))
        else:
            reply = search_feature(keyword)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    elif user_input in ["機制選項", "支援機制"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=get_supported_mechanisms()))
        return

    elif user_input in ["查指令", "指令"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=get_supported_commands()))
        return

    # 忽略不合法指令
    return


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
