import os
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from deep_translator import GoogleTranslator

app = Flask(__name__)
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

def is_chinese(text):
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            return True
    return False

def auto_translate(text):
    if is_chinese(text):
        target = "id"
        source = "zh-TW"
    else:
        target = "zh-TW"
        source = "auto"
    result = GoogleTranslator(source=source, target=target).translate(text)
    if result is None or result.strip() == text.strip():
        result = GoogleTranslator(source="auto", target=target).translate(text)
    if result is None or result.strip() == text.strip():
        return "Translation unavailable for this message."
    return result

@app.route("/callback", methods=["POST"])
def callback():
    sig = request.headers.get("X-Line-Signature","")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, sig)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()
    if not text:
        return
    try:
        reply = auto_translate(text)
    except Exception:
        reply = "Translation failed, please try again."
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(reply_token=event.reply_token,messages=[TextMessage(text=reply)])
        )

@app.route("/", methods=["GET"])
def health():
    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
