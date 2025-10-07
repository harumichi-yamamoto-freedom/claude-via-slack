"""
会話履歴管理モジュール
Slackスレッドから会話履歴を取得・フォーマット
"""
import re
import logging

from ..config import MAX_HISTORY_MESSAGES


def get_thread_history(client, channel, thread_ts, bot_user_id):
    """
    Slackスレッドから会話履歴を取得

    Args:
        client: Slack WebClient
        channel: チャンネルID
        thread_ts: スレッドID
        bot_user_id: ボットのユーザーID

    Returns:
        list: [(role, content), ...] のタプルリスト
              role: 'user' または 'assistant'
    """
    try:
        # スレッドの全メッセージを取得
        response = client.conversations_replies(
            channel=channel,
            ts=thread_ts,
            limit=100  # 十分な数を取得
        )

        messages = response.get("messages", [])
        if not messages:
            return []

        history = []

        for msg in messages:
            user = msg.get("user")
            text = msg.get("text", "").strip()

            if not text:
                continue

            # ボットのメッセージかどうか
            is_bot = (user == bot_user_id or msg.get("bot_id"))

            if is_bot:
                # ボットのメッセージ: 最終出力のみを抽出
                final_output = extract_final_output(text)
                if final_output:
                    history.append(("assistant", final_output))
            else:
                # ユーザーのメッセージ: メンション部分を除去
                clean_text = remove_mention(text)
                # streamプレフィックスを除去
                clean_text = remove_stream_prefix(clean_text)
                if clean_text:
                    history.append(("user", clean_text))

        # 最新のMAX_HISTORY_MESSAGES件のみ返す
        return history[-MAX_HISTORY_MESSAGES:]

    except Exception as e:
        logging.error(f"Failed to get thread history: {e}")
        return []


def extract_final_output(text):
    """
    ボットのメッセージから最終出力のみを抽出

    Args:
        text: ボットのメッセージ全体

    Returns:
        str: 最終出力部分、またはNone
    """
    # "開始します！", "完了しました！", "エラーが発生しました", "[STDERR]" などは除外
    if any(keyword in text for keyword in ["開始します！", "完了しました！", "エラーが発生しました", "[STDERR]", "[DEBUG]"]):
        return None

    # コードブロック（```）で囲まれた部分は途中経過なので除外
    if text.startswith("```") and text.endswith("```"):
        return None

    # 区切り線を含む場合は除外（途中経過の区切り）
    if "━━━" in text or "---" in text or "***" in text:
        return None

    # 実行中メッセージを除外
    if "実行中" in text or "経過時間" in text:
        return None

    # 残ったテキストが最終出力
    return text.strip()


def remove_mention(text):
    """
    テキストからメンション部分を除去

    Args:
        text: メンション付きテキスト

    Returns:
        str: メンション除去後のテキスト
    """
    return re.sub(r"<@[^>]+>\s*", "", text).strip()


def remove_stream_prefix(text):
    """
    テキストから'stream'プレフィックスを除去

    Args:
        text: プロンプトテキスト

    Returns:
        str: streamプレフィックス除去後のテキスト
    """
    if text.lower().startswith("stream"):
        return text[6:].strip()
    return text


def format_history_for_prompt(history):
    """
    会話履歴をプロンプト用にフォーマット

    Args:
        history: [(role, content), ...] のリスト

    Returns:
        str: フォーマットされた会話履歴
    """
    if not history:
        return ""

    formatted_lines = ["これまでの会話履歴:"]
    formatted_lines.append("")

    for role, content in history:
        if role == "user":
            formatted_lines.append(f"ユーザー: {content}")
        else:
            formatted_lines.append(f"アシスタント: {content}")
        formatted_lines.append("")

    formatted_lines.append("---")
    formatted_lines.append("")

    return "\n".join(formatted_lines)
