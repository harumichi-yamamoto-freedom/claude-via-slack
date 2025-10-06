"""
Linux用スクリーンショット実装（プレースホルダー）
将来的に実装予定
"""
import logging
from typing import Tuple, Optional

from .base import ScreenshotHandler


class LinuxScreenshotHandler(ScreenshotHandler):
    """Linux用スクリーンショットハンドラー（未実装）"""

    def __init__(self, editor_cmd: str, default_cwd: str):
        super().__init__(editor_cmd, default_cwd)
        logging.warning("Linux screenshot handler is not yet implemented")

    def take_screenshot(
        self,
        file_path: str,
        line_number: Optional[int] = None,
        output_path: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        スクリーンショットを撮影する（未実装）

        TODO: Linux実装
        - xdotool でウィンドウを操作
        - scrot または import (ImageMagick) でスクリーンショット撮影
        - または、Wayland環境では grim を使用
        """
        return False, "Linux版は未実装です", None

    def cleanup(self):
        """リソースのクリーンアップ"""
        pass
