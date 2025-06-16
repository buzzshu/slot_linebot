import os
import re
import pandas as pd
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# 載入環境變數
load_dotenv()
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

# 初始化 LINE Bot
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 載入遊戲資料
bigwinboard_df = pd.read_csv("bigwinboard_slots_with_full_features.csv")
demoslot_df = pd.read_csv("demoslot_games_full_data.csv")

# 分析遊戲統計欄位
STAT_FIELDS = [
    ("Reels", "🎰 Reels"),
    ("Rows", "🎰 Rows"),
    ("Paylines", "📈 Paylines"),
    ("Hit Frequency", "🎯 Hit Freq"),
    ("Free Spins Frequency", "🎯 Free Spins Freq"),
    ("Max Win", "💰 Max Win"),
    ("Max Win Probability", "📊 Max Win Probability"),
    ("Volatility", "⚖️ Volatility"),
    ("Min/Max Bet", "💵 Min/Max Bet"),
    ("Release Date", "🗓️ Release Date")
]

def format_game_stats(row) -> str:
    lines = []
    for key, label in STAT_FIELDS:
        value = row.get(key)
        if pd.notna(value):
            lines.append(f"{label}: {value}")
    return "\n".join(lines)

# 分析基本遊戲特徵
def analyze_game_features(description: str) -> str:
    desc = description.lower()
    features = {
        "🎲 基本玩法": [],
        "💥 特色機制": [],
        "🛠️ 功能特色": []
    }
    if re.search(r"\d+x\d+", desc):
        match = re.search(r"\d+x\d+", desc)
        features["🎲 基本玩法"].append(f"格子結構：{match.group()}")
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

# 遊戲說明整理
def summarize_game(description: str) -> str:
    desc = description.lower()
    summary_parts = []
    if re.search(r"\b5[- ]reels?\b", desc):
        summary_parts.append("• 5 軸盤面，常見配置。")
    if re.search(r"\b20 paylines?\b", desc):
        summary_parts.append("• 20 條固定賠付線。")
    if "cluster pays" in desc:
        summary_parts.append("• 採用 Cluster Pays 群組支付機制。")
    if "megaways" in desc:
        summary_parts.append("• Megaways 機制，連動格數變化增加中獎方式。")

    if "wild transformation" in desc:
        summary_parts.append("• Wild 轉換機制，可將特定符號變為 Wild。")
    if "free spins" in desc:
        summary_parts.append("• 免費旋轉功能，由 Scatter 符號或特殊條件觸發。")
    if "symbol to wild" in desc:
        summary_parts.append("• 特定符號可永久轉換為 Wild 進行高配。")
    if "multiplier" in desc:
        summary_parts.append("• 可疊加或遞增的倍數增益。")
    if "mystery symbol" in desc:
        summary_parts.append("• 神秘符號機制，轉軸後同步顯示相同圖案。")
    if "buy feature" in desc or "bonus buy" in desc:
        summary_parts.append("• 可付費直接進入免費遊戲模式。")

    return "🔍 玩法說明：\n" + "\n".join(summary_parts) if summary_parts else "🔍 玩法說明：尚無明確資訊。"

# 進階玩法規則辨識
GAME_FEATURE_RULES = {
    "基本盤面": [r"\d+\s*x\s*\d+", r"\d+\s*reels?", r"\d+\s*rows?"],
    "支付方式": ["cluster pays", "megaways", "ways to win", "payline"],
    "免費遊戲": ["free spins?", "scatter", "bonus round"],
    "wild 特性": ["wild transformation", "walking wild", "sticky wild", "expanding wild"],
    "特殊功能": ["buy feature", "bonus buy", "orb bonus", "super bonus", "hold and win"]
}

def advanced_analyze_game(description: str) -> str:
    desc = description.lower()
    features = []
    for category, patterns in GAME_FEATURE_RULES.items():
        for pattern in patterns:
            if isinstance(pattern, str) and pattern in desc:
                features.append(f"• {category}：包含 {pattern}")
                break
            elif re.search(pattern, desc):
                features.append(f"• {category}：符合 {pattern}")
                break
    return "📊 進階玩法解析：\n" + "\n".join(features) if features else "⚠️ 無法解析明確玩法資訊"

# 查詢遊戲邏輯
def search_game(keyword, max_results=3):
    result = bigwinboard_df[bigwinboard_df["Title"].astype(str).str.contains(keyword, case=False, na=False)]
    if result.empty:
        result = demoslot_df[demoslot_df["game_name"].astype(str).str.contains(keyword, case=False, na=False)]

    if result.empty:
        return "❌ 找不到相關遊戲。"

    result = result.head(max_results)
    messages = []

    for _, row in result.iterrows():
        name = row.get("Title", row.get("game_name", "未知遊戲"))
        rtp = row.get("RTP", "N/A")
        url = row.get("URL", row.get("url", ""))
        desc = row.get("Description", row.get("description", ""))
        img = row.get("Image", row.get("image_url", "（無圖片）"))
        short_desc = desc[:200].strip().replace("\n", " ") + "..." if len(desc) > 200 else desc.strip()

        feature_summary = analyze_game_features(desc)
        game_summary = summarize_game(desc)
        advanced_features = advanced_analyze_game(desc)
        stat_block = format_game_stats(row)

        message = (
            f"🎰 遊戲：{name}\n"
            f"🎯 RTP：{rtp}\n"
            f"🔗 {url}\n"
            f"📖 遊戲簡介：\n{short_desc}\n\n"
            f"{game_summary}\n\n"
            f"{feature_summary}\n\n"
            f"{advanced_features}\n\n"
            f"📊 遊戲數據：\n{stat_block}\n\n"
            f"🖼️ 圖片：{img}"
        )
        messages.append(message)

    return "\n\n".join(messages)

# 查詢特定機制的遊戲
def search_by_feature(keyword):
    results = []
    keyword = keyword.lower()
    combined_df = pd.concat([bigwinboard_df, demoslot_df], ignore_index=True)
    for _, row in combined_df.iterrows():
        desc = str(row.get("Description") or row.get("description") or "").lower()
        name = row.get("Title", row.get("game_name", "未知遊戲"))
        url = row.get("URL", row.get("url", ""))
        if keyword in desc:
            results.append(f"🎰 {name}\n🔗 {url}")
        if len(results) >= 10:
            break
    return "\n\n".join(results) if results else "❌ 找不到包含該機制的遊戲。"

# 建立 Flask 應用
app = Flask(__name__)

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

# 處理訊息事件
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_input = event.message.text.strip()
    if user_input.startswith("查遊戲"):
        keyword = user_input.replace("查遊戲", "").strip()
        reply = search_game(keyword)
    elif user_input.startswith("查機制"):
        keyword = user_input.replace("查機制", "").strip()
        reply = search_by_feature(keyword)
    else:
        reply = "請輸入：\n•『查遊戲 遊戲名稱』來查詢遊戲\n•『查機制 機制關鍵字』來查詢包含某機制的遊戲"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
