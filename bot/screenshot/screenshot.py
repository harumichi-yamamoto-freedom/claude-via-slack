"""
スクリーンショット機能のメインスクリプト
独立実行可能・他モジュールからimport可能
"""
import sys
import argparse
import logging
from pathlib import Path

# 親ディレクトリをパスに追加（独立実行時のため）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot.config import SCREENSHOT_OS, EDITOR_CMD, DEFAULT_CWD
from bot.screenshot.base import ScreenshotHandler
from bot.screenshot.macos import MacOSScreenshotHandler
from bot.screenshot.windows import WindowsScreenshotHandler
from bot.screenshot.linux import LinuxScreenshotHandler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def get_screenshot_handler(os_type: str = None) -> ScreenshotHandler:
    """
    OS別のスクリーンショットハンドラーを取得

    Args:
        os_type: OS種別（"macos", "windows", "linux"）

    Returns:
        ScreenshotHandler
    """
    if os_type is None:
        os_type = SCREENSHOT_OS

    os_type = os_type.lower()

    if os_type == "macos":
        return MacOSScreenshotHandler(EDITOR_CMD, DEFAULT_CWD)
    elif os_type == "windows":
        return WindowsScreenshotHandler(EDITOR_CMD, DEFAULT_CWD)
    elif os_type == "linux":
        return LinuxScreenshotHandler(EDITOR_CMD, DEFAULT_CWD)
    else:
        raise ValueError(f"Unsupported OS: {os_type}")


def take_screenshot(
    file_path: str,
    line_number: int = None,
    output_path: str = None,
    os_type: str = None
):
    """
    スクリーンショットを撮影する（ファサード関数）

    Args:
        file_path: ファイルパス
        line_number: ジャンプする行番号
        output_path: 出力先パス
        os_type: OS種別

    Returns:
        (成功フラグ, メッセージ, スクリーンショットファイルパス)
    """
    handler = get_screenshot_handler(os_type)
    try:
        return handler.take_screenshot(file_path, line_number, output_path)
    finally:
        handler.cleanup()


def main():
    """CLIエントリーポイント"""
    parser = argparse.ArgumentParser(
        description="エディタでファイルを開いてスクリーンショットを撮影"
    )
    parser.add_argument(
        "file_path",
        help="スクリーンショットを撮影するファイルのパス"
    )
    parser.add_argument(
        "--line",
        type=int,
        help="ジャンプする行番号"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="出力先ファイルパス（指定しない場合は一時ファイル）"
    )
    parser.add_argument(
        "--os",
        choices=["macos", "windows", "linux"],
        help=f"OS種別（デフォルト: {SCREENSHOT_OS}）"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="詳細ログを出力"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # スクリーンショット撮影
    success, message, screenshot_path = take_screenshot(
        args.file_path,
        args.line,
        args.output,
        args.os
    )

    if success:
        print(f"✓ {message}")
        print(f"📸 {screenshot_path}")
        return 0
    else:
        print(f"✗ {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
