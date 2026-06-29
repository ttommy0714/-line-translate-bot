import os
import anthropic
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

LANG_MAP = {
    "英文": "English", "en": "English",
    "日文": "Japanese", "jp": "Japanese",
    "韓文": "Korean", "kr": "Korean",
    "中文": "Traditional Chinese", "zh": "Traditional Chinese",
    "泰文": "Thai", "th": "Thai",
    "越南文": "Vietnamese", "vn": "Vietnamese",
    "法文": "French", "fr": "French",
    "德文": "German", "de": "German",
    "西班牙文": "Spanish", "es": "Spanish",
    "印尼文": "Indonesian", "id": "Indonesian",
}

HELP_TEXT = "翻譯機器人使用說明\n\n指令格式：翻[語言] [文字]\n\n範例：\n  翻英文 今天天氣真好\n  翻印尼文 謝謝你\n  翻中文 Terima kasih\n\n支援語言：英文、日文、韓文、中文、泰文、越南文、印尼文、法文、德文、西班牙文\n\n輸入 說明 顯示此訊息"

def translate_with_claude(text, target_lang):
    message = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Translate to " + target_lang + ". Return ONLY the translated text.\n\n" + text}]
    )
    return message.content[0].text.strip()

def parse_command(text):
    text = text.strip()
    if text == "說明" or text.lower() == "help":
        return ("help", "")
    if text.startswith("翻"):
        rest = text[1:].strip()
        for key, lang in LANG_MAP.items():
            if rest.lower().startswith(key):
                content = rest[len(key):].strip()
                return (lang, content) if content else ("missing_text", key)
    return None

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    result = parse_command(event.message.text)
    if result is None:
        return
    target_lang, content = result
    if target_lang == "help":
        reply = HELP_TEXT
    elif target_lang == "missing_text":
        reply = "請輸入要翻譯的文字，範例：翻" + content + " 你好"
    else:
        try:
            translated = translate_with_claude(content, target_lang)
            reply = target_lang + "\n" + translated
        except Exception:
            reply = "翻譯失敗，請稍後再試"
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)])
        )

@app.route("/", methods=["GET"])
def health():
    return "LINE Translate Bot is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
