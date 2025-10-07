"""
Slackメッセージハンドラー
"""
import re
import time
import logging

from ..utils.session import thread_ts_to_session_id
from ..utils.buffer import OutputBuffer
from ..claude.runner import run_claude_streaming
from ..screenshot.screenshot import take_screenshot
from .commands import handle_status, handle_stop, handle_screenshot


def create_mention_handler(client, active_processes, active_lock, stopped_threads):
    """
    app_mentionイベントハンドラーを作成

    Args:
        client: Slack WebClient
        active_processes: アクティブプロセスの辞書
        active_lock: プロセス管理用のロック
        stopped_threads: 停止されたスレッドのセット

    Returns:
        ハンドラー関数
    """
    def on_mention(body, _say, _logger):
        event = body.get("event", {})
        channel = event.get("channel")
        user_id = event.get("user")
        text = event.get("text", "") or ""

        # このイベントの親: 返信ならそのthread_ts、そうでなければ自身のts
        thread_ts = event.get("thread_ts") or event.get("ts")

        # メンションを除去してプロンプト化
        prompt = re.sub(r"<@[^>]+>\s*", "", text).strip()

        # ストリーミング有効フラグ（streamで始まる場合のみストリーミング）
        enable_streaming = prompt.lower().startswith("stream")
        if enable_streaming:
            prompt = prompt[6:].strip()  # "stream"を除去

        # status コマンド
        if prompt.lower() == "status":
            handle_status(client, channel, thread_ts, user_id, active_processes, active_lock)
            return

        # stop コマンド
        if prompt.lower() == "stop":
            handle_stop(client, channel, thread_ts, user_id, active_processes, active_lock, stopped_threads)
            return

        # screenshot コマンド
        if prompt.lower().startswith("screenshot"):
            handle_screenshot(client, channel, thread_ts, user_id, prompt, take_screenshot)
            return

        if not prompt:
            client.chat_postMessage(
                channel=channel, thread_ts=thread_ts,
                text="プロンプトが空です。`@Bot 〜〜` の形で送ってください。"
            )
            return

        # 実行開始メッセージ
        client.chat_postMessage(channel=channel, thread_ts=thread_ts, text="開始します！")

        # スレッドごとのセッションID生成
        session_id = thread_ts_to_session_id(thread_ts)
        logging.info(f"Using session ID: {session_id} for thread: {thread_ts}")

        # バッファ初期化
        start_time = time.time()
        buffer = OutputBuffer(client, channel, thread_ts, enable_streaming, start_time)

        # ツール実行追跡用
        current_tools = {}  # index -> {name, input_parts, id}

        # 自動フラッシュスレッド開始
        flusher_thread = buffer.start_auto_flusher()

        # Claude実行
        code = run_claude_streaming(
            prompt,
            buffer.append_stdout,
            buffer.append_stderr,
            session_id=session_id,
            thread_ts=thread_ts,
            current_tools=current_tools,
            message_stopped=buffer.message_stopped,
            active_processes=active_processes,
            active_lock=active_lock,
        )

        # フラッシャースレッドを停止
        buffer.stop_auto_flusher()

        # 手動停止された場合はバッファをクリアして終了
        if thread_ts in stopped_threads:
            stopped_threads.discard(thread_ts)
            buffer.clear()
            return

        # 残りのバッファをすべて投稿
        buffer.flush()

        # 最終メッセージ
        if code == 0:
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"<@{user_id}> 完了しました！"
            )
        else:
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"<@{user_id}> エラーが発生しました（code={code}）"
            )

    return on_mention
