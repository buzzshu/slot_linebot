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

# 分析基本遊戲特徵

def analyze_game_features(description: str) -> str:
    desc = description.lower()
    features = {
        "🎲 基本玩法": [],
        "💥 特色機制": [],
        "🛠️ 功能特色": [],
        "💰 中獎潛力": [],
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

    maxwin = re.search(r'(\d{1,3}(,\d{3})*x)', desc)
    if maxwin:
        features["💰 中獎潛力"].append(f"最大中獎：{maxwin.group()}")

    summary = []
    for section, items in features.items():
        if items:
            summary.append(f"{section}：\n• " + "\n• ".join(items))
    return "\n\n".join(summary) if summary else "⚠️ 無法從描述中解析出玩法資訊。"

# 遊戲說明整理

def summarize_game(description: str) -> str:
    desc = description.lower()
    summary_parts = []
    if "5 reels" in desc or "5-reel" in desc:
        summary_parts.append("• 5 軸 3 列，經典盤面配置。")
    if "20 paylines" in desc:
        summary_parts.append("• 20 條固定賠付線。")
    if "cluster pays" in desc:
        summary_parts.append("• 採用 Cluster Pays 群組支付機制。")

    if "wild transformation" in desc:
        summary_parts.append("• 隨機 Wild 轉換功能，可將多個符號轉為 Wild。")
    if "free spins" in desc:
        summary_parts.append("• 具備免費旋轉功能，可由 Scatter 符號或特殊圖案觸發。")
    if "symbol to wild" in desc:
        summary_parts.append("• 特定符號轉為 Wild，持續整個免費遊戲。")
    if "merlin" in desc or "orb" in desc:
        summary_parts.append("• Merlin's Orb Bonus 可提供現金獎或更多免費旋轉。")

    max_win_match = re.search(r"(\d{1,3}(,\d{3})*x) the stake", desc)
    if max_win_match:
        summary_parts.append(f"• 最大中獎：{max_win_match.group(1)} 賭注。")

    return "🔍 玩法說明：\n" + "\n".join(summary_parts) if summary_parts else "🔍 玩法說明：尚無明確資訊。"

# 進階玩法規則辨識
GAME_FEATURE_RULES = {
    "基本盤面": [r"\d+\s*x\s*\d+", r"\d+\s*reels?", r"\d+\s*rows?"],
    "支付方式": ["cluster pays", "megaways", "ways to win", "payline"],
    "免費遊戲": ["free spins?", "scatter", "bonus round"],
    "wild 特性": ["wild transformation", "walking wild", "sticky wild", "expanding wild"],
    "特殊功能": ["buy feature", "bonus buy", "orb bonus", "super bonus", "hold and win"],
    "中獎潛力": [r"\d{1,3}(,\d{3})*x the stake", "max win"],
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
    combined_df = pd.concat([bigwinboard_df, demoslot_df], ignore_index=True)

    def get_title(row):
        return row.get("Title") or row.get("game_name") or ""

    matches = []
    for _, row in combined_df.iterrows():
        title = get_title(row)
        if keyword.lower() in title.lower():
            matches.append(row)
        if len(matches) >= max_results:
            break

    if not matches:
        return "❌ 找不到相關遊戲。"

    messages = []
    for row in matches:
        name = row.get("Title", row.get("game_name", "未知遊戲"))
        rtp = row.get("RTP", "N/A")
        url = row.get("URL", row.get("url", ""))
        desc = row.get("Description", row.get("description", ""))
        short_desc = desc[:200].strip().replace("\n", " ") + "..." if len(desc) > 200 else desc.strip()
        img = row.get("Image", row.get("image_url", "（無圖片）"))
        feature_summary = analyze_game_features(desc)
        game_summary = summarize_game(desc)
        advanced_features = advanced_analyze_game(desc)

        message = (
            f"🎰 {name}\n"
            f"🎯 RTP: {rtp}\n"
            f"📖 {short_desc}\n"
            f"🖼️ 圖片：{img}\n"
            f"🔗 {url}\n\n"
            f"{feature_summary}\n\n{game_summary}\n\n{advanced_features}"
        )
        messages.append(message)

    return "\n\n" + "\n\n".join(messages)

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
    print("📩 收到 LINE 請求：", body)  # <-- 新增這行

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
    app.run(debug=True, port=8080)
