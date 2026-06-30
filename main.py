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

# Render free instances do not keep memory permanently.
# These per-user language settings reset when the service restarts.
USER_TARGET_LANG = {}

LANGUAGES = {
    "id": {"name_zh": "印尼文", "name_en": "Indonesian", "translator_targets": ["id", "indonesian"]},
    "zh-TW": {"name_zh": "繁體中文", "name_en": "Traditional Chinese", "translator_targets": ["zh-TW", "chinese (traditional)"]},
    "en": {"name_zh": "英文", "name_en": "English", "translator_targets": ["en", "english"]},
    "ja": {"name_zh": "日文", "name_en": "Japanese", "translator_targets": ["ja", "japanese"]},
    "ko": {"name_zh": "韓文", "name_en": "Korean", "translator_targets": ["ko", "korean"]},
    "vi": {"name_zh": "越南文", "name_en": "Vietnamese", "translator_targets": ["vi", "vietnamese"]},
    "th": {"name_zh": "泰文", "name_en": "Thai", "translator_targets": ["th", "thai"]},
    "ms": {"name_zh": "馬來文", "name_en": "Malay", "translator_targets": ["ms", "malay"]},
    "fil": {"name_zh": "菲律賓文", "name_en": "Filipino", "translator_targets": ["filipino", "tagalog"]},
    "es": {"name_zh": "西班牙文", "name_en": "Spanish", "translator_targets": ["es", "spanish"]},
}

ALIASES = {
    "zh": "zh-TW",
    "tw": "zh-TW",
    "cn": "zh-TW",
    "chinese": "zh-TW",
    "中文": "zh-TW",
    "繁中": "zh-TW",
    "繁體": "zh-TW",
    "indonesia": "id",
    "indonesian": "id",
    "印尼": "id",
    "印尼文": "id",
    "english": "en",
    "英文": "en",
    "日本": "ja",
    "日文": "ja",
    "japanese": "ja",
    "韓文": "ko",
    "korean": "ko",
    "越南": "vi",
    "越南文": "vi",
    "vietnamese": "vi",
    "泰文": "th",
    "thai": "th",
    "malay": "ms",
    "馬來": "ms",
    "菲律賓": "fil",
    "filipino": "fil",
    "tagalog": "fil",
    "spanish": "es",
    "西班牙": "es",
}


def is_config_ready():
    return bool(LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN)


def is_chinese(text):
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def normalize_language_code(raw_code):
    code = raw_code.strip()
    if not code:
        return None

    if code in LANGUAGES:
        return code

    lower_code = code.lower()
    if lower_code in LANGUAGES:
        return lower_code

    return ALIASES.get(lower_code) or ALIASES.get(code)


def get_user_key(event):
    source = event.source
    if hasattr(source, "user_id") and source.user_id:
        return source.user_id
    if hasattr(source, "group_id") and source.group_id:
        return source.group_id
    if hasattr(source, "room_id") and source.room_id:
        return source.room_id
    return "default"


def set_user_target(user_key, lang_code):
    USER_TARGET_LANG[user_key] = lang_code


def get_user_target(user_key, text):
    return USER_TARGET_LANG.get(user_key) or ("id" if is_chinese(text) else "zh-TW")


def help_text():
    return (
        "翻譯機器人指令：\n"
        "/to id：切換成印尼文\n"
        "/to zh-TW：切換成繁體中文\n"
        "/to en：切換成英文\n"
        "/to ja：切換成日文\n"
        "/to ko：切換成韓文\n"
        "/to vi：切換成越南文\n"
        "/to th：切換成泰文\n"
        "/to ms：切換成馬來文\n"
        "/to fil：切換成菲律賓文\n"
        "/to es：切換成西班牙文\n"
        "/auto：恢復自動模式，中文→印尼文，非中文→繁中\n"
        "/lang：查看目前目標語言"
    )


def handle_command(text, user_key):
    normalized = text.strip()
    lower = normalized.lower()

    if lower in ["/help", "help", "說明"]:
        return help_text()

    if lower == "/auto":
        USER_TARGET_LANG.pop(user_key, None)
        return "已切換為自動模式：中文→印尼文；非中文→繁體中文。"

    if lower == "/lang":
        lang_code = USER_TARGET_LANG.get(user_key)
        if not lang_code:
            return "目前是自動模式：中文→印尼文；非中文→繁體中文。"
        lang = LANGUAGES[lang_code]
        return f"目前目標語言：{lang['name_zh']}（{lang_code}）"

    if lower.startswith("/to "):
        raw_code = normalized.split(maxsplit=1)[1]
        lang_code = normalize_language_code(raw_code)
        if not lang_code:
            return "不支援這個語言代碼。\n\n" + help_text()

        set_user_target(user_key, lang_code)
        lang = LANGUAGES[lang_code]
        return f"已切換翻譯目標語言：{lang['name_zh']}（{lang_code}）。"

    return None


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


def get_target_candidates(target):
    if target in LANGUAGES:
        return LANGUAGES[target]["translator_targets"]
    return [target]


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
    normalized = normalize_text(text)
    candidates = []

    for target_code in get_target_candidates(target):
        candidates.append((text, "auto", target_code))
        if normalized != text:
            candidates.append((normalized, "auto", target_code))

    if target == "id":
        candidates.extend([
            (normalized, "chinese (traditional)", "indonesian"),
            (normalized, "chinese (simplified)", "indonesian"),
        ])
    elif target == "zh-TW":
        candidates.extend([
            (normalized, "indonesian", "chinese (traditional)"),
            (normalized, "english", "chinese (traditional)"),
        ])

    errors = []
    for candidate_text, source_code, target_code in candidates:
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
        if target == "en":
            return None

        english = try_translate_once(normalized, "auto", "english")
        if not english:
            return None

        for target_code in get_target_candidates(target):
            try:
                translated = try_translate_once(english, "english", target_code)
                if translated:
                    return translated
            except Exception:
                logger.exception("Two-step target attempt failed. target_code=%s", target_code)
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


def auto_translate(text, user_key=None):
    target = get_user_target(user_key or "default", text)
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
    target = normalize_language_code(request.args.get("to", "")) or ("id" if is_chinese(text) else "zh-TW")
    return jsonify(
        {
            "input": text,
            "normalized_input": normalize_text(text),
            "contains_chinese": is_chinese(text),
            "output": translate_with_fallback(text, target),
            "target": target,
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

    user_key = get_user_key(event)
    command_reply = handle_command(text, user_key)

    if command_reply is not None:
        reply_text = command_reply
    else:
        try:
            reply_text = auto_translate(text, user_key)
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
