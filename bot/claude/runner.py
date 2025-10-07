"""
Claude CLI実行モジュール
"""
import os
import json
import logging
import threading
from subprocess import Popen, PIPE

from ..config import CLAUDE_BIN, DEFAULT_CWD
from .events import EventHandler


def run_claude_streaming(
    prompt: str,
    on_stdout: callable,
    on_stderr: callable,
    session_id: str | None = None,
    thread_ts: str | None = None,
    current_tools: dict | None = None,
    message_stopped: list | None = None,
    active_processes: dict | None = None,
    active_lock = None,
) -> int:
    """
    Claude CLIをストリーミングモードで実行

    Args:
        prompt: プロンプト文字列
        on_stdout: 標準出力を受け取るコールバック
        on_stderr: 標準エラーを受け取るコールバック
        session_id: セッションID（スレッド固有）
        thread_ts: SlackスレッドID
        current_tools: ツール実行状態を保持する辞書
        message_stopped: メッセージ停止フラグ
        active_processes: アクティブプロセスの辞書
        active_lock: プロセス管理用のロック

    Returns:
        終了コード
    """
    if current_tools is None:
        current_tools = {}
    if message_stopped is None:
        message_stopped = [False]

    args = [
        CLAUDE_BIN,
        "--print",
        "--verbose",
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--permission-mode", "bypassPermissions",
    ]
    if session_id:
        args += ["--session-id", session_id]
    args += [prompt]

    env = {
        **os.environ,
        "PATH": f"/opt/homebrew/bin:/usr/local/bin:{os.environ.get('PATH', '')}",
    }
    # ANTHROPIC_API_KEYを削除してOAuth認証を使用
    env.pop("ANTHROPIC_API_KEY", None)

    proc: Popen | None = None
    try:
        logging.info("Starting claude process: %s", " ".join(args))
        proc = Popen(
            args,
            cwd=DEFAULT_CWD,
            env=env,
            stdout=PIPE,
            stderr=PIPE,
            text=True,
            bufsize=1,
        )
        logging.info("Claude process started with PID: %s", proc.pid)

        # このスレッド(ts)にぶら下がるプロセスとして登録
        if thread_ts and active_processes is not None and active_lock is not None:
            with active_lock:
                active_processes[thread_ts] = proc

        # STDERR を別スレッドで処理
        stderr_first, stderr_last = [], []

        def _drain_stderr():
            try:
                if proc.stderr:
                    for line in proc.stderr:
                        if not line:
                            continue
                        if sum(len(x.encode()) for x in stderr_first) < 2048:
                            stderr_first.append(line)
                        else:
                            stderr_last.append(line)
                            while sum(len(x.encode()) for x in stderr_last) > 2048:
                                stderr_last.pop(0)
            except Exception as e:
                logging.warning("stderr reader error: %s", e)
            finally:
                if stderr_first:
                    on_stderr("[DEBUG] stderr head\n" + "".join(stderr_first))
                if stderr_last:
                    on_stderr("[DEBUG] stderr tail\n" + "".join(stderr_last))

        t = threading.Thread(target=_drain_stderr, daemon=True)
        t.start()

        # イベントハンドラー初期化
        event_handler = EventHandler(on_stdout, current_tools, message_stopped)

        # STDOUT を逐次パース
        if proc.stdout:
            for raw in proc.stdout:
                if not raw:
                    continue
                line = raw.strip()
                if not line:
                    continue

                logging.info("RAW STDOUT: %s", line[:200])

                # JSON 以外は捨てる
                try:
                    evt = json.loads(line)
                except Exception as e:
                    logging.info("JSON parse failed: %s (line: %s)", e, line[:100])
                    continue

                # イベント処理
                event_handler.handle_event(evt)

        proc.wait()
        logging.info("Claude process finished with code: %s", proc.returncode)
        t.join(timeout=5)
        return int(proc.returncode or 0)

    except Exception as e:
        logging.exception("run_claude_streaming error")
        try:
            if proc and proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        on_stderr(f"[ERROR] {type(e).__name__}: {e}\n")
        return 1
    finally:
        # 終了時はこのスレッド(ts)から除外
        if thread_ts and active_processes is not None and active_lock is not None:
            with active_lock:
                active_processes.pop(thread_ts, None)
