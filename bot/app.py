import os
import ssl
import certifi
import json
import logging
import threading
from time import sleep
from subprocess import Popen, PIPE, TimeoutExpired
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient

logging.basicConfig(level=logging.INFO)

load_dotenv("config/.env")

# ★ 環境に合わせて
CLAUDE_BIN = os.environ["CLAUDE_BIN"]
DEFAULT_CWD = os.environ["CLAUDE_BIN"]
MAX_LEN = 39000

ssl_ctx = ssl.create_default_context(cafile=certifi.where())
bot_token = os.environ["SLACK_BOT_TOKEN"]
app_token = os.environ["SLACK_APP_TOKEN"]
client = WebClient(token=bot_token, ssl=ssl_ctx)
app = App(client=client)


def chunk(s: str, n: int):
    for i in range(0, len(s), n):
        yield s[i : i + n]


def run_claude(prompt: str, resume_sid: str | None = None) -> tuple[int, str, str]:
    args = [CLAUDE_BIN, "--print"]
    if resume_sid:
        args += ["--resume", resume_sid]
    args += [prompt]
    env = {
        **os.environ,
        "PATH": f"/opt/homebrew/bin:/usr/local/bin:{os.environ.get('PATH', '')}",
    }
    try:
        proc = Popen(
            args, cwd=DEFAULT_CWD, env=env, stdout=PIPE, stderr=PIPE, text=True
        )
        out, err = proc.communicate(timeout=180)
        return proc.returncode, (out or ""), (err or "")
    except TimeoutExpired:
        return 124, "", "claude の応答がタイムアウトしました（180s）"
    except Exception as e:
        return 1, "", f"{type(e).__name__}: {e}"


def start_thinking_notifier(
    channel: str,
    thread_ts: str,
    stop_evt: threading.Event,
    interval_sec=10,
    max_ticks=12,
):
    """
    10秒おきに '考え中…' を同じスレッドに投稿。stop_evt.set() で停止。
    max_ticks を超えたら自動停止（暴走防止）。
    """
    tick = 0
    while not stop_evt.wait(interval_sec):
        tick += 1
        try:
            client.chat_postMessage(
                channel=channel,
                text=f"考え中…（{tick * interval_sec}秒経過）",
                thread_ts=thread_ts,
            )
        except Exception as e:
            logging.warning("thinking notifier error: %s", e)
        if tick >= max_ticks:
            break


@app.event("message")
def _any_message(body, logger):
    logger.debug("message event: %s", json.dumps(body))


@app.event("app_mention")
def on_mention(body, say, logger):
    event = body.get("event", {})
    channel = event.get("channel")
    text = event.get("text", "")
    prompt = text.split(">", 1)[-1].strip()
    if not prompt:
        say("プロンプトが空です。`@Bot 〜〜` の形で送ってください。")
        return

    # 最初の「考え中…」を投稿し、ts を控える
    first = say("考え中…")
    thread_ts = first["ts"] if isinstance(first, dict) and "ts" in first else None
    if thread_ts is None:
        # 念のためフォールバック（thread_tsなしで通常投稿）
        thread_ts = None

    # 10秒おき通知のスレッドを開始
    stop_evt = threading.Event()
    notifier = threading.Thread(
        target=start_thinking_notifier,
        args=(channel, thread_ts or first["ts"], stop_evt),
        daemon=True,
    )
    notifier.start()

    # セッションIDは現状 None のままでもOK
    sid_path = os.path.join(DEFAULT_CWD, ".claude_session")
    resume_sid = None
    if os.path.exists(sid_path):
        try:
            with open(sid_path) as f:
                resume_sid = (f.read() or "").strip() or None
        except Exception:
            resume_sid = None

    # 実行
    code, out, err = run_claude(prompt, resume_sid=resume_sid)

    # 通知を停止
    stop_evt.set()
    notifier.join(timeout=2)

    # 結果を同じスレッドに返信
    if code != 0:
        client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"エラーが発生しました（code={code}）:\n```{(err or 'unknown error')[:MAX_LEN]}```",
        )
        return

    output = out.strip() or "（出力なし）"
    for i, part in enumerate(chunk(output, MAX_LEN)):
        prefix = "" if i == 0 else f"(続き {i + 1})\n"
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts, text=f"{prefix}```\n{part}\n```"
        )


if __name__ == "__main__":
    # SSL設定付きの WebClient を handler に渡す（←重要）
    handler = SocketModeHandler(app, app_token, web_client=client)
    handler.start()
