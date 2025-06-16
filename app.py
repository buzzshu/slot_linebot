import os
import pandas as pd
from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging import MessagingApi, Configuration
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhook.models import MessageEvent
from linebot.v3.messaging.models import TextMessage, ReplyMessageRequest

# 載入 .env 環境變數
load_dotenv()
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

# 防呆檢查
if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("❌ 請確認 .env 檔案包含 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET")

# 初始化 LINE Messaging API
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
line_bot_api = MessagingApi(configuration)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 載入遊戲資料
bigwinboard_df = pd.read_csv("bigwinboard_slots_with_full_features.csv")
demoslot_df = pd.read_csv("demoslot_games_full_data.csv")

# 建立 Flask App
app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "✅ LINE Bot 已部署成功，Webhook 請使用 /callback"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# 處理 LINE 文字訊息事件
@handler.add(MessageEvent)
def handle_message(event):
    if event.message.type != "text":
        print("⚠️ 收到非文字訊息，略過")
        return

    user_input = event.message.text.strip().lower()
    print("📩 使用者輸入：", user_input)

    # 決定回應內容
    if user_input.startswith("查遊戲"):
        keyword = user_input.replace("查遊戲", "").strip()
        reply_text = search_game(keyword)
    elif user_input.startswith("查功能"):
        feature = user_input.replace("查功能", "").strip()
        reply_text = search_by_feature(feature)
    else:
        reply_text = (
            "請輸入以下指令：\n"
            "🔍 查遊戲 [遊戲名稱]\n"
            "🛠️ 查功能 [功能名，例如 Buy Feature]"
        )

    if not isinstance(reply_text, str) or not reply_text.strip():
        reply_text = "⚠️ 無法產生回覆內容，請稍後再試。"

    try:
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )
        print("✅ 成功回覆訊息")
    except Exception as e:
        print("❌ 回覆訊息失敗：", e)

# 查詢遊戲名稱
def search_game(keyword):
    result = bigwinboard_df[bigwinboard_df["Title"].str.contains(keyword, case=False, na=False)]
    if result.empty:
        result = demoslot_df[demoslot_df["game_name"].str.contains(keyword, case=False, na=False)]

    if result.empty:
        return "❌ 找不到這款遊戲。"

    row = result.iloc[0]
    name = row.get("Title", row.get("game_name", "未知遊戲"))
    rtp = row.get("RTP", "N/A")
    vol = row.get("Volatility", "N/A")
    url = row.get("URL", row.get("url", ""))

    return f"🎰 遊戲：{name}\n🎯 RTP：{rtp}\n🔥 波動性：{vol}\n🔗 {url}"

# 查詢功能標籤
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

# 在 Railway / Heroku 上自動抓 PORT
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
