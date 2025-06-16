import os
import pandas as pd
from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# 載入 .env
load_dotenv()
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 載入資料
bigwinboard_df = pd.read_csv("bigwinboard_slots_with_full_features.csv")
demoslot_df = pd.read_csv("demoslot_games_full_data.csv")

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "✅ LINE Bot 已部署成功，Webhook 在 /callback"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_input = event.message.text.strip().lower()
    print("📩 使用者輸入：", user_input)

    if user_input.startswith("查遊戲"):
        keyword = user_input.replace("查遊戲", "").strip()
        reply_text = search_game(keyword)
    elif user_input.startswith("查功能"):
        feature = user_input.replace("查功能", "").strip()
        reply_text = search_by_feature(feature)
    else:
        reply_text = (
            "請輸入：\n"
            "🔍 查遊戲 [遊戲名稱]\n"
            "🛠️ 查功能 [功能名，例如 Buy Feature]"
        )

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

def search_game(keyword, max_results=3):
    result = bigwinboard_df[bigwinboard_df["Title"].str.contains(keyword, case=False, na=False)]
    if result.empty:
        result = demoslot_df[demoslot_df["game_name"].str.contains(keyword, case=False, na=False)]

    if result.empty:
        return "❌ 找不到相關遊戲。"

    result = result.head(max_results)

    messages = []
    for _, row in result.iterrows():
        name = row.get("Title", row.get("game_name", "未知遊戲"))
        rtp = row.get("RTP", "N/A")
        url = row.get("URL", row.get("url", ""))
        desc = row.get("Description", row.get("description", ""))
        short_desc = desc[:200].strip().replace("\n", " ") + "..." if len(desc) > 200 else desc.strip()

        msg = f"🎰 {name}\n🎯 RTP: {rtp}\n📖 {short_desc}\n🔗 {url}"
        messages.append(msg)

    return "\n\n".join(messages)

def search_by_feature(feature):
    candidates = [col for col in bigwinboard_df.columns if feature.lower() in col.lower()]
    if not candidates:
        return "❌ 找不到符合的功能欄位。"

    col = candidates[0]
    result = bigwinboard_df[bigwinboard_df[col] == 'Yes']
    if result.empty:
        result = demoslot_df[demoslot_df[col] == 'Yes']

    if result.empty:
        return f"❌ 找不到包含「{feature}」的遊戲。"

    names = result.head(5)["Title"].fillna(result["game_name"]).tolist()
    return f"🎯 有「{col}」的前幾款遊戲：\n" + "\n".join(["• " + name for name in names])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
