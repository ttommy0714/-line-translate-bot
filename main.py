import logging
import os
import re

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


def normalize_text(text):
    replacements = {
        "，": ", ",
        "。": ". ",
        "！": "! ",
        "？": "? ",
        "；": "; ",
        "：": ": ",
        "、": ", ",
        "「": " ",
        "」": " ",
        "『": " ",
        "』": " ",
        "（": "(",
        "）": ")",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def split_text(text):
    parts = re.split(r"[，。！？；：、,!.?;:\n]+", text)
    return [part.strip() for part in parts if part.strip()]


def try_translate_once(text, source, target):
    translated = GoogleTranslator(source=source, target=target).translate(text)
    logger.info(
        "Translation attempt source=%s target=%s input=%r output=%r",
        source,
        target,
        text,
        translated,
    )

    if translated and translated.strip() and translated.strip() != text.strip():
        return translated.strip()

    return None


def direct_translate(text, target):
    if target == "id":
        attempts = [
            (text, "auto", "id"),
            (text, "auto", "indonesian"),
            (normalize_text(text), "auto", "id"),
            (normalize_text(text), "auto", "indonesian"),
            (normalize_text(text), "chinese (traditional)", "indonesian"),
            (normalize_text(text), "chinese (simplified)", "indonesian"),
        ]
    else:
        attempts = [
            (text, "auto", "zh-TW"),
            (text, "auto", "chinese (traditional)"),
            (normalize_text(text), "auto", "zh-TW"),
            (normalize_text(text), "auto", "chinese (traditional)"),
            (normalize_text(text), "indonesian", "chinese (traditional)"),
            (normalize_text(text), "english", "chinese (traditional)"),
        ]

    errors = []
    for candidate_text, source_code, target_code in attempts:
        if not candidate_text:
            continue
        try:
            translated = try_translate_once(candidate_text, source_code, target_code)
            if translated:
                return translated
        except Exception as exc:
            errors.append(f"{source_code}->{target_code}: {exc}")

    logger.warning("Direct translation failed. input=%r target=%s errors=%s", text, target, errors)
    return None


def two_step_translate(text, target):
    try:
        normalized = normalize_text(text)
        if target == "id":
            english = try_translate_once(normalized, "auto", "english")
            if english:
                return try_translate_once(english, "english", "indonesian")
        else:
            english = try_translate_once(normalized, "auto", "english")
            if english:
                return try_translate_once(english, "english", "chinese (traditional)")
    except Exception:
        logger.exception("Two-step translation failed. input=%r target=%s", text, target)

    return None


def chunk_translate(text, target):
    chunks = split_text(text)
    if len(chunks) <= 1:
        return None

    translated_chunks = []
    for chunk in chunks:
        translated = direct_translate(chunk, target) or two_step_translate(chunk, target)
        if not translated:
            return None
        translated_chunks.append(translated)

    return " ".join(translated_chunks).strip()


def translate_with_fallback(text, target):
    translated = direct_translate(text, target)
    if translated:
        return translated

    translated = two_step_translate(text, target)
    if translated:
        return translated

    translated = chunk_translate(text, target)
    if translated:
        return translated

    logger.warning("Translation fallback exhausted. input=%r target=%s", text, target)
    return "Maaf, layanan terjemahan sementara tidak dapat memproses pesan ini. Silakan coba lagi."


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
            "normalized_input": normalize_text(text),
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
        logger.exception("Translation failed. input=%r", text)
        reply_text = "Maaf, layanan terjemahan sementara gagal. Silakan coba lagi."

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
