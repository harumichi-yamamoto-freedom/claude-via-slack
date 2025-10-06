import os
import json
import ssl
import certifi
import logging
import threading
import time
import re
from subprocess import Popen, PIPE
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient

logging.basicConfig(level=logging.INFO)
load_dotenv("config/.env")

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/usr/local/bin/claude")
DEFAULT_CWD = os.environ.get("DEFAULT_CWD", os.getcwd())
MAX_LEN = 39000
FLUSH_INTERVAL = 1.0  # バッファフラッシュ間隔（秒）
PROGRESS_INTERVAL = 60.0  # 進捗メッセージ送信間隔（秒）

ssl_ctx = ssl.create_default_context(cafile=certifi.where())
bot_token = os.environ["SLACK_BOT_TOKEN"]
app_token = os.environ["SLACK_APP_TOKEN"]
client = WebClient(token=bot_token, ssl=ssl_ctx)
app = App(client=client)

# スレッド(ts)単位で管理
active_processes: dict[str, Popen] = {}
active_lock = threading.RLock()
stopped_threads: set[str] = set()

ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

def sanitize(s: str) -> str:
    # Slack表示が崩れないようにANSIを取り除く＆CRをLFに
    s = ANSI_RE.sub("", s)
    s = s.replace("\r", "")
    return s

def chunk(s: str, n: int):
    for i in range(0, len(s), n):
        yield s[i : i + n]

def run_claude_streaming(
    prompt: str,
    on_stdout: callable,
    on_stderr: callable,
    resume_sid: str | None = None,
    thread_ts: str | None = None,
    current_tools: dict | None = None,
    message_stopped: list | None = None,
) -> int:
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
        "--permission-mode", "bypassPermissions",  # 全ての確認プロンプトをバイパス
    ]
    if resume_sid:
        args += ["--resume", resume_sid]
    args += [prompt]

    env = {
        **os.environ,
        "PATH": f"/opt/homebrew/bin:/usr/local/bin:{os.environ.get('PATH', '')}",
    }

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
            bufsize=1,  # line-buffered
        )
        logging.info("Claude process started with PID: %s", proc.pid)

        # このスレッド(ts)にぶら下がるプロセスとして登録（ロック付き）
        if thread_ts:
            with active_lock:
                active_processes[thread_ts] = proc

        # STDERR は別スレッドで先頭/末尾のみ保持して後で吐く
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

        # STDOUT を逐次パース
        if proc.stdout:
            for raw in proc.stdout:
                if not raw:
                    continue
                line = raw.strip()
                if not line:
                    continue

                # デバッグ: 生の行をログ出力
                logging.info("RAW STDOUT: %s", line[:200])

                # JSON 以外は捨てる（CLIが余計な行を出すことがある）
                try:
                    evt = json.loads(line)
                except Exception as e:
                    logging.info("JSON parse failed: %s (line: %s)", e, line[:100])
                    continue

                etype = (evt.get("type") or "")

                # stream_event の場合は、ネストされた event を取得
                if etype == "stream_event":
                    nested_event = evt.get("event", {})
                    etype = nested_event.get("type", "")
                    evt = nested_event  # 以降の処理でネストされたイベントを使用

                ntype = etype.replace(".", "_")  # "message.delta" -> "message_delta"

                # デバッグ: イベントタイプをログ出力
                logging.info("Event type: %s, full event: %s", etype, json.dumps(evt)[:300])

                # 0) 最終結果イベントを検出（最終出力テキストを抽出）
                if etype == "result":
                    logging.info("!!! result event detected - this is final output !!!")
                    message_stopped[0] = True
                    # resultフィールドから最終出力を取得
                    final_result = evt.get("result", "")
                    if final_result:
                        on_stdout(final_result)
                    continue

                # 1) ツール使用開始
                if ntype == "content_block_start":
                    content_block = evt.get("content_block", {})
                    if content_block.get("type") == "tool_use":
                        index = evt.get("index", 0)
                        tool_name = content_block.get("name", "Unknown")
                        tool_id = content_block.get("id", "")
                        current_tools[index] = {
                            "name": tool_name,
                            "input_parts": [],
                            "id": tool_id
                        }
                    continue

                # 2) ツール入力完了時の表示
                if ntype == "content_block_stop":
                    index = evt.get("index", 0)
                    if index in current_tools:
                        tool_info = current_tools.pop(index)
                        full_input = "".join(tool_info["input_parts"])
                        try:
                            input_json = json.loads(full_input) if full_input else {}
                        except:
                            input_json = full_input

                        tool_msg = f"\n⏺ {tool_info['name']}({json.dumps(input_json, ensure_ascii=False)})\n  ⎿ Running…\n"
                        on_stdout(tool_msg)
                    continue

                # 3) 増分テキスト
                if ntype in ("content_block_delta", "message_delta"):
                    delta = evt.get("delta") or {}
                    delta_type = delta.get("type", "")

                    # 3a) ツール入力の蓄積
                    if delta_type == "input_json_delta":
                        index = evt.get("index", 0)
                        if index in current_tools:
                            partial_json = delta.get("partial_json", "")
                            current_tools[index]["input_parts"].append(partial_json)
                        continue

                    # 3b) テキストデルタ
                    if delta_type in ("text_delta", "output_text_delta"):
                        text = delta.get("text", "")
                        logging.info("Extracted text (content_block_delta): %s", text[:50])
                        on_stdout(text)
                    continue

                # 4) ツールの増分テキスト
                if ntype == "tool_result_delta":
                    delta = evt.get("delta") or {}
                    if delta.get("type") == "output_text_delta":
                        text = delta.get("text", "")
                        logging.info("Extracted text (tool_result_delta): %s", text[:50])
                        on_stdout(text)
                    continue

                # 5) ツールの最終まとめ
                if ntype == "tool_result":
                    for c in (evt.get("content") or []):
                        if isinstance(c, dict) and c.get("type") == "output_text":
                            text = c.get("text", "")
                            logging.info("Extracted text (tool_result): %s", text[:50])
                            on_stdout(text)
                    continue

                # 6) 互換: トップレベル text をそのまま
                if isinstance(evt.get("text"), str):
                    text = evt["text"]
                    logging.info("Extracted text (top-level): %s", text[:50])
                    on_stdout(text)
                    continue

                # 7) ツール結果 (type: "user" のメッセージ)
                if etype == "user":
                    message = evt.get("message", {})
                    content_list = message.get("content", [])
                    for item in content_list:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            result_content = item.get("content", "")
                            # 結果が長い場合は省略
                            if isinstance(result_content, str):
                                lines = result_content.split("\n")
                                if len(lines) > 5:
                                    preview = "\n".join(lines[:5]) + f"\n  … +{len(lines) - 5} lines"
                                else:
                                    preview = result_content
                                # ツール結果を投稿
                                on_stdout(f"\n{preview}\n")
                    continue

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
        # 終了時はこのスレッド(ts)から除外（ロック付き）
        if thread_ts:
            with active_lock:
                active_processes.pop(thread_ts, None)

@app.event("app_mention")
def on_mention(body, say, logger):
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

    # status は実行状態を確認
    if prompt.lower() == "status":
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
        return

    # stop は同じスレッド単位で停止
    if prompt.lower() == "stop":
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
        return

    if not prompt:
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            text="プロンプトが空です。`@Bot 〜〜` の形で送ってください。"
        )
        return

    # 最初の投稿も"同じ thread_ts" に返信（ここが肝）
    client.chat_postMessage(channel=channel, thread_ts=thread_ts, text="開始します...")

    # セッションID
    sid_path = os.path.join(DEFAULT_CWD, ".claude_session")
    resume_sid = None
    if os.path.exists(sid_path):
        try:
            with open(sid_path, "r", encoding="utf-8") as f:
                resume_sid = (f.read() or "").strip() or None
        except Exception:
            resume_sid = None

    # バッファ
    output_buffer, stderr_buffer = [], []
    buffer_lock = threading.RLock()
    buffered_len = [0]
    last_post_time = [0]  # 0で初期化、初回データ受信時に設定
    stop_flusher = [False]  # フラッシャースレッド停止フラグ
    message_stopped = [False]  # message_stopイベントを受信したか
    start_time = time.time()  # 実行開始時刻
    last_progress_time = [time.time()]  # 最後の進捗メッセージ送信時刻

    # ツール実行追跡用
    current_tools = {}  # index -> {name, input_parts, id}

    def _post(content: str, wrap_code: bool = False):
        logging.info("_post called with content length: %d, wrap_code: %s", len(content), wrap_code)
        content = sanitize(content)
        if wrap_code and content.strip():
            content = f"```\n{content}\n```"
        for part in chunk(content, MAX_LEN):
            time.sleep(0.2)  # rate limit 緩和
            try:
                logging.info("Posting to Slack: %s", part[:100])
                result = client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=part  # マークダウンをそのまま表示
                )
                logging.info("Posted successfully: %s", result.get("ok"))
            except Exception as e:
                logging.exception("Failed to post to Slack: %s", e)

    def post_buffer_content():
        stdout_payload = ""
        stderr_payload = ""
        is_final_output = False
        with buffer_lock:
            if output_buffer:
                stdout_payload = "".join(output_buffer)
                output_buffer.clear()
            if stderr_buffer:
                stderr_payload = "".join(stderr_buffer)
                stderr_buffer.clear()
            buffered_len[0] = 0
            is_final_output = message_stopped[0]
        logging.info("post_buffer_content: is_final_output=%s, message_stopped=%s", is_final_output, message_stopped[0])
        if stdout_payload:
            _post(stdout_payload, wrap_code=not is_final_output)
        if stderr_payload:
            _post(f"[STDERR]\n{stderr_payload}")

    def on_stdout(line: str):
        logging.info("on_stdout called with: %s", line[:100])

        # 最終出力の場合
        if message_stopped[0]:
            # まず残っているバッファをフラッシュ（```付き）
            if enable_streaming:
                post_buffer_content()
            # 最終出力を```なしで投稿
            _post(line, wrap_code=False)
            return

        # ストリーミング無効時は中間出力を無視
        if not enable_streaming:
            return

        flush = False
        now = time.time()
        with buffer_lock:
            output_buffer.append(line)
            buffered_len[0] += len(line)
            # 初回は last_post_time を設定
            if last_post_time[0] == 0:
                last_post_time[0] = now
            logging.info("Buffer size: %d, time since last post: %.2f", buffered_len[0], now - last_post_time[0])

            # ツール実行メッセージ（⏺で始まる）は即座にフラッシュ
            if "⏺" in line:
                flush = True
                last_post_time[0] = now
            # FLUSH_INTERVAL秒ごと、または3900文字以上でフラッシュ
            elif (now - last_post_time[0] >= FLUSH_INTERVAL) or (buffered_len[0] >= 3900):
                flush = True
                last_post_time[0] = now
        if flush:
            logging.info("Flushing buffer...")
            post_buffer_content()

    def on_stderr(line: str):
        flush = False
        now = time.time()
        with buffer_lock:
            stderr_buffer.append(line)
            # stderr はFLUSH_INTERVALで優先フラッシュ
            if (now - last_post_time[0] >= FLUSH_INTERVAL):
                flush = True
                last_post_time[0] = now
        if flush:
            post_buffer_content()

    # 定期的にバッファをチェックしてフラッシュするスレッド
    def auto_flusher():
        while not stop_flusher[0]:
            time.sleep(0.5)  # 0.5秒ごとにチェック
            if stop_flusher[0]:
                break
            now = time.time()
            should_flush = False

            # ストリーミング無効時はPROGRESS_INTERVAL秒ごとに進捗メッセージを送信
            if not enable_streaming:
                if now - last_progress_time[0] >= PROGRESS_INTERVAL:
                    elapsed_seconds = int(now - start_time)
                    elapsed_minutes = elapsed_seconds // 60
                    elapsed_secs = elapsed_seconds % 60
                    elapsed_str = f"{elapsed_minutes}分{elapsed_secs}秒" if elapsed_minutes > 0 else f"{elapsed_secs}秒"
                    try:
                        client.chat_postMessage(
                            channel=channel,
                            thread_ts=thread_ts,
                            text=f"実行中...（経過時間: {elapsed_str}）"
                        )
                        last_progress_time[0] = now
                    except Exception as e:
                        logging.error("Failed to post progress message: %s", e)

            # ストリーミング有効時のみバッファをチェック
            if enable_streaming:
                with buffer_lock:
                    # データがあり、かつFLUSH_INTERVAL以上経過している場合
                    if (output_buffer or stderr_buffer) and last_post_time[0] > 0:
                        if now - last_post_time[0] >= FLUSH_INTERVAL:
                            should_flush = True
                            last_post_time[0] = now
                if should_flush:
                    logging.info("Auto-flushing buffer...")
                    post_buffer_content()

    flusher_thread = threading.Thread(target=auto_flusher, daemon=True)
    flusher_thread.start()

    code = run_claude_streaming(
        prompt,
        on_stdout,
        on_stderr,
        resume_sid=resume_sid,
        thread_ts=thread_ts,  # 常にこの thread_ts を使う
        current_tools=current_tools,
        message_stopped=message_stopped,
    )

    # フラッシャースレッドを停止
    stop_flusher[0] = True
    flusher_thread.join(timeout=1)

    # 手動停止された場合はバッファをクリアして終了
    if thread_ts in stopped_threads:
        stopped_threads.discard(thread_ts)
        # バッファをクリア（投稿しない）
        with buffer_lock:
            output_buffer.clear()
            stderr_buffer.clear()
            buffered_len[0] = 0
        return

    # 残りのバッファをすべて投稿
    post_buffer_content()

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

if __name__ == "__main__":
    handler = SocketModeHandler(app, app_token, web_client=client)
    handler.start()
