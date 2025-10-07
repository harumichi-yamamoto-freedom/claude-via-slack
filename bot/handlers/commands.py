"""
コマンド処理モジュール
status, stop, screenshotの各コマンドを処理
"""
import os
import re
import logging


def handle_status(client, channel, thread_ts, user_id, active_processes, active_lock):
    """
    statusコマンドの処理

    Args:
        client: Slack WebClient
        channel: チャンネルID
        thread_ts: スレッドID
        user_id: ユーザーID
        active_processes: アクティブプロセスの辞書
        active_lock: プロセス管理用のロック
    """
    with active_lock:
        proc = active_processes.get(thread_ts)
    if proc and proc.poll() is None:
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            text=f"<@{user_id}> 実行中です（PID: {proc.pid}）"
        )
    else:
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            text=f"<@{user_id}> 実行中のプロセスはありません。"
        )


def handle_stop(client, channel, thread_ts, user_id, active_processes, active_lock, stopped_threads):
    """
    stopコマンドの処理

    Args:
        client: Slack WebClient
        channel: チャンネルID
        thread_ts: スレッドID
        user_id: ユーザーID
        active_processes: アクティブプロセスの辞書
        active_lock: プロセス管理用のロック
        stopped_threads: 停止されたスレッドのセット
    """
    with active_lock:
        proc = active_processes.get(thread_ts)
    if proc and proc.poll() is None:
        stopped_threads.add(thread_ts)
        try:
            proc.kill()
        finally:
            with active_lock:
                active_processes.pop(thread_ts, None)
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            text=f"<@{user_id}> Claudeプロセスを停止しました。"
        )
    else:
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            text=f"<@{user_id}> このスレッドに実行中のプロセスはありません。"
        )


def handle_screenshot(client, channel, thread_ts, user_id, prompt, take_screenshot):
    """
    screenshotコマンドの処理

    Args:
        client: Slack WebClient
        channel: チャンネルID
        thread_ts: スレッドID
        user_id: ユーザーID
        prompt: コマンド文字列
        take_screenshot: スクリーンショット撮影関数
    """
    parts = prompt.split(maxsplit=1)
    if len(parts) < 2:
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            text="使い方:\n`@Bot screenshot <file_path>`\n`@Bot screenshot <file_path> --line 10`"
        )
        return

    # ファイルパスとオプションを解析
    args = parts[1]
    file_path = None
    line_range = None

    # --line オプションの解析（単一行番号）
    lines_match = re.search(r"--line\s+(\d+)", args)
    if lines_match:
        line_range = lines_match.group(1)
        # --lineより前の部分をファイルパスとして取得
        file_path = args[:lines_match.start()].strip()
    else:
        file_path = args.strip()

    if not file_path:
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            text="使い方:\n`@Bot screenshot <file_path>`\n`@Bot screenshot <file_path> --line 10`"
        )
        return

    client.chat_postMessage(
        channel=channel, thread_ts=thread_ts,
        text=f"スクリーンショットを撮影します: {file_path}" + (f" (行 {line_range}から)" if line_range else "")
    )

    # スクリーンショットを撮影
    line_number = int(line_range) if line_range else None
    success, message, screenshot_path = take_screenshot(file_path, line_number)

    if success and screenshot_path:
        try:
            # Slackにファイルをアップロード
            with open(screenshot_path, "rb") as f:
                client.files_upload_v2(
                    channel=channel,
                    thread_ts=thread_ts,
                    file=f,
                    filename=f"screenshot_{os.path.basename(file_path)}.png",
                    title=f"Screenshot: {file_path}",
                    initial_comment=f"<@{user_id}> {message}"
                )
            # 一時ファイルを削除
            os.unlink(screenshot_path)
        except Exception as e:
            logging.exception("Failed to upload screenshot")
            client.chat_postMessage(
                channel=channel, thread_ts=thread_ts,
                text=f"<@{user_id}> スクリーンショットのアップロードに失敗しました: {str(e)}"
            )
    else:
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            text=f"<@{user_id}> {message}"
        )
