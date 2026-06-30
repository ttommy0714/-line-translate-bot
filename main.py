import logging
import os

from flask import Flask, abort, jsonify, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from deep_translator import GoogleTranslator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "").strip()
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


def is_config_ready():
    return bool(LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN)


def is_chinese(text):
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def translate_with_fallback(text, target):
    errors = []
    attempts = [
        ("auto", target),
        ("auto", "indonesian" if target == "id" else "chinese (traditional)"),
        ("auto", "zh-TW" if target == "zh-TW" else "id"),
    ]

    for source_code, target_code in attempts:
        try:
            translated = GoogleTranslator(source=source_code, target=target_code).translate(text)
            if translated and translated.strip() and translated.strip() != text.strip():
                return translated
        except Exception as exc:
            errors.append(f"{source_code}->{target_code}: {exc}")

    logger.warning("Translation fallback exhausted. errors=%s", errors)
    return "Translation unavailable for this message."


def auto_translate(text):
    target = "id" if is_chinese(text) else "zh-TW"
    return translate_with_fallback(text, target)


@app.route("/", methods=["GET"])
def health():
    return "OK"


@app.route("/health", methods=["GET"])
def health_detail():
    return jsonify(
        {
            "status": "OK" if is_config_ready() else "CONFIG_MISSING",
            "line_channel_secret_set": bool(LINE_CHANNEL_SECRET),
            "line_channel_access_token_set": bool(LINE_CHANNEL_ACCESS_TOKEN),
        }
    )


@app.route("/test-translate", methods=["GET"])
def test_translate():
    text = request.args.get("q", "你好")
    return jsonify(
        {
            "input": text,
            "contains_chinese": is_chinese(text),
            "output": auto_translate(text),
            "target": "id" if is_chinese(text) else "zh-TW",
        }
    )


@app.route("/callback", methods=["POST"])
def callback():
    if not is_config_ready():
        logger.error("LINE environment variables are missing.")
        abort(500)

    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    logger.info("LINE webhook received. body_length=%s", len(body))

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.warning("Invalid LINE signature. Check LINE_CHANNEL_SECRET.")
        abort(400)
    except Exception:
        logger.exception("Unhandled callback error.")
        abort(500)

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()

    if not text:
        return

    try:
        reply_text = auto_translate(text)
    except Exception:
        logger.exception("Translation failed.")
        reply_text = "Translation failed, please try again."

    try:
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)],
                )
            )
    except Exception:
        logger.exception("LINE reply failed. Check LINE_CHANNEL_ACCESS_TOKEN.")
        raise


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
