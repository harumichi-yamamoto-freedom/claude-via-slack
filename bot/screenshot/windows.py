"""
Windows用スクリーンショット実装（プレースホルダー）
将来的に実装予定
"""
import logging
from typing import Tuple, Optional

from .base import ScreenshotHandler


class WindowsScreenshotHandler(ScreenshotHandler):
    """Windows用スクリーンショットハンドラー（未実装）"""

    def __init__(self, editor_cmd: str, default_cwd: str):
        super().__init__(editor_cmd, default_cwd)
        logging.warning("Windows screenshot handler is not yet implemented")

    def take_screenshot(
        self,
        file_path: str,
        line_number: Optional[int] = None,
        output_path: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        スクリーンショットを撮影する（未実装）

        TODO: Windows実装
        - pywinauto または pyautogui を使用してウィンドウを操作
        - PIL (Pillow) でスクリーンショット撮影
        - または、Windows APIを直接呼び出し
        """
        return False, "Windows版は未実装です", None

    def cleanup(self):
        """リソースのクリーンアップ"""
        pass
