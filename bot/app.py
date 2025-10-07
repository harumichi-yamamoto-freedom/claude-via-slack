"""
Slack Bot メインアプリケーション
"""
import ssl
import certifi
import logging
import threading

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient

import sys
from pathlib import Path

# botディレクトリの親をsys.pathに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.config import SLACK_BOT_TOKEN, SLACK_APP_TOKEN, DEFAULT_CWD
from bot.handlers.message import create_mention_handler

logging.basicConfig(level=logging.INFO)

# Slack クライアント初期化
ssl_ctx = ssl.create_default_context(cafile=certifi.where())
client = WebClient(token=SLACK_BOT_TOKEN, ssl=ssl_ctx)
app = App(client=client)

# グローバル状態管理
active_processes: dict = {}
active_lock = threading.RLock()
stopped_threads: set = set()

# ハンドラー登録
app.event("app_mention")(
    create_mention_handler(client, active_processes, active_lock, stopped_threads)
)

if __name__ == "__main__":
    # 作業ディレクトリの確認
    print(f"\n作業ディレクトリ: {DEFAULT_CWD}")
    print("このディレクトリでClaude CLIが実行されます。")
    confirm = input("このディレクトリで実行しますか？ (y/n): ").strip().lower()

    if confirm != 'y':
        print("\n起動をキャンセルしました。")
        print(f"作業ディレクトリを変更する場合は、config/.env ファイルの DEFAULT_CWD を編集してください。")
        sys.exit(0)

    print("\nSlack Botを起動しています...\n")

    handler = SocketModeHandler(app, SLACK_APP_TOKEN, web_client=client)
    handler.start()
