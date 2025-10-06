"""
設定管理モジュール
環境変数の読み込みと設定の一元管理
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# スクリプトのディレクトリを基準にして.envファイルを読み込む
script_dir = Path(__file__).parent.parent
env_path = script_dir / "config" / ".env"
load_dotenv(env_path)

# Claude CLI設定
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/usr/local/bin/claude")
DEFAULT_CWD = os.environ.get("DEFAULT_CWD", os.getcwd())

# エディタ設定
EDITOR_CMD = os.environ.get("EDITOR_CMD", "code")  # code or cursor

# Slack設定
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]

# スクリーンショット設定
SCREENSHOT_OS = os.environ.get("SCREENSHOT_OS", "macos")  # macos, windows, linux

# その他の設定
MAX_LEN = 39000  # Slackメッセージの最大文字数
FLUSH_INTERVAL = 1.0  # バッファフラッシュ間隔（秒）
PROGRESS_INTERVAL = 10.0  # 進捗メッセージ送信間隔（秒）
