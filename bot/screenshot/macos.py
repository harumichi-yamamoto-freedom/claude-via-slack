"""
macOS用スクリーンショット実装
PyObjCとAppleScriptを使用
"""
import os
import time
import tempfile
import logging
from subprocess import run
from typing import Tuple, Optional

from .base import ScreenshotHandler

# PyObjC for window management
try:
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
        kCGWindowOwnerName,
        kCGWindowLayer,
        kCGWindowNumber
    )
    PYOBJC_AVAILABLE = True
except ImportError:
    PYOBJC_AVAILABLE = False
    logging.warning("PyObjC not available. Screenshot feature may not work properly.")


class MacOSScreenshotHandler(ScreenshotHandler):
    """macOS用スクリーンショットハンドラー"""

    def __init__(self, editor_cmd: str, default_cwd: str):
        super().__init__(editor_cmd, default_cwd)

        # エディタの設定
        self.is_cursor = editor_cmd == "cursor"
        self.app_name = "Cursor" if self.is_cursor else "Visual Studio Code"
        self.process_name = "Cursor" if self.is_cursor else "Code"

    def take_screenshot(
        self,
        file_path: str,
        line_number: Optional[int] = None,
        output_path: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        スクリーンショットを撮影する

        Args:
            file_path: ファイルパス
            line_number: ジャンプする行番号
            output_path: 出力先パス

        Returns:
            (成功フラグ, メッセージ, スクリーンショットファイルパス)
        """
        try:
            # ファイルパスを解決
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.default_cwd, file_path)

            if not os.path.exists(file_path):
                return False, f"ファイルが見つかりません: {file_path}", None

            abs_path = os.path.abspath(file_path)

            # 出力先を決定
            if output_path is None:
                temp_screenshot = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                screenshot_path = temp_screenshot.name
                temp_screenshot.close()
            else:
                screenshot_path = output_path

            # エディタで新しいウィンドウで開く
            if line_number:
                open_cmd = [self.editor_cmd, "--new-window", "--goto", f"{abs_path}:{line_number}"]
            else:
                open_cmd = [self.editor_cmd, "--new-window", abs_path]

            logging.info(f"Opening file with command: {' '.join(open_cmd)}")
            result = run(open_cmd, capture_output=True, text=True)

            if result.returncode != 0:
                return False, f"ファイルを開けませんでした: {result.stderr}", None

            # エディタが起動するまで待機
            time.sleep(3)

            # エディタをアクティブにする
            activate_script = f'tell application "{self.app_name}" to activate'
            run(["osascript", "-e", activate_script], capture_output=True, text=True)
            time.sleep(2)

            # ウィンドウを最大化
            self._maximize_window()
            time.sleep(1.5)

            # スクリーンショット撮影
            screenshot_success = self._capture_screenshot(screenshot_path)

            if not screenshot_success:
                return False, "スクリーンショットの撮影に失敗しました", None

            # ウィンドウを閉じる
            self._close_window()

            return True, "スクリーンショットを撮影しました", screenshot_path

        except Exception as e:
            logging.exception("Screenshot error")
            return False, f"エラーが発生しました: {str(e)}", None

    def _maximize_window(self):
        """ウィンドウを最大化"""
        maximize_script = f"""
        tell application "System Events"
            tell process "{self.process_name}"
                if exists window 1 then
                    tell window 1
                        set position to {{0, 23}}
                        set size to {{1920, 1057}}
                    end tell
                end if
            end tell
        end tell
        """
        result = run(["osascript", "-e", maximize_script], capture_output=True, text=True)
        if result.returncode != 0:
            logging.warning(f"Failed to maximize window: {result.stderr}")
        else:
            logging.info("Window maximized successfully")

    def _capture_screenshot(self, screenshot_path: str) -> bool:
        """
        スクリーンショットを撮影

        Returns:
            成功フラグ
        """
        # 方法1: PyObjCでウィンドウIDを取得
        window_id = self._find_window_id()

        if window_id:
            try:
                result = run(
                    ["screencapture", "-o", "-l", str(window_id), screenshot_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0 and os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 0:
                    logging.info(f"Screenshot captured with window ID: {window_id}")
                    return True
            except Exception as e:
                logging.warning(f"Failed to capture with window ID {window_id}: {e}")

        # 方法2（フォールバック）: AXで座標/サイズを取得して矩形キャプチャ
        logging.info("Trying fallback method: AX bounds + screencapture -R")
        bounds = self._get_window_bounds()
        if bounds:
            x, y, w, h = bounds
            try:
                result = run(
                    ["screencapture", "-o", "-R", f"{x},{y},{w},{h}", screenshot_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0 and os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 0:
                    logging.info(f"Screenshot captured with bounds: {bounds}")
                    return True
            except Exception as e:
                logging.error(f"Failed to capture with bounds: {e}")

        return False

    def _find_window_id(self, retry: int = 20, sleep_sec: float = 0.25) -> Optional[int]:
        """
        CGWindowListを使用してウィンドウIDを取得

        Returns:
            CGWindowID または None
        """
        if not PYOBJC_AVAILABLE:
            logging.error("PyObjC is not available")
            return None

        for attempt in range(retry):
            try:
                window_list = CGWindowListCopyWindowInfo(
                    kCGWindowListOptionOnScreenOnly,
                    kCGNullWindowID
                )

                if not window_list:
                    logging.warning(f"No windows found (attempt {attempt + 1}/{retry})")
                    time.sleep(sleep_sec)
                    continue

                for window in window_list:
                    owner = window.get(kCGWindowOwnerName, "")
                    layer = window.get(kCGWindowLayer, -1)
                    window_id = window.get(kCGWindowNumber, 0)

                    if self.process_name in owner and layer == 0:
                        logging.info(f"Found window: owner={owner}, id={window_id}, layer={layer}")
                        return int(window_id)

                logging.debug(f"Window not found for owner={self.process_name} (attempt {attempt + 1}/{retry})")
                time.sleep(sleep_sec)

            except Exception as e:
                logging.error(f"Error finding window ID: {e}")
                time.sleep(sleep_sec)

        return None

    def _get_window_bounds(self) -> Optional[Tuple[int, int, int, int]]:
        """
        AppleScriptを使用してウィンドウの座標とサイズを取得

        Returns:
            (x, y, width, height) または None
        """
        script = f'''
        tell application "System Events"
            if not (exists process "{self.process_name}") then return "ERR"
            tell process "{self.process_name}"
                if (count of windows) < 1 then return "ERR"
                set p to position of window 1
                set s to size of window 1
                return ((item 1 of p) as text) & "," & ((item 2 of p) as text) & "," & ((item 1 of s) as text) & "," & ((item 2 of s) as text)
            end tell
        end tell
        '''

        try:
            result = run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            logging.info(f"AppleScript result: returncode={result.returncode}, stdout='{result.stdout.strip()}', stderr='{result.stderr.strip()}'")

            if result.returncode == 0 and result.stdout and "ERR" not in result.stdout:
                parts = [p.strip() for p in result.stdout.strip().split(",") if p.strip()]
                if len(parts) == 4:
                    try:
                        x, y, w, h = [int(float(v)) for v in parts]
                        logging.info(f"Got window bounds via AppleScript: x={x}, y={y}, w={w}, h={h}")
                        return x, y, w, h
                    except ValueError as e:
                        logging.warning(f"Failed to parse window bounds: {parts}, error: {e}")
                else:
                    logging.warning(f"Unexpected AppleScript output format: {parts} (expected 4 values, got {len(parts)})")
            else:
                logging.warning(f"AppleScript failed or returned ERR")
        except Exception as e:
            logging.error(f"Error getting window bounds: {e}")

        return None

    def _close_window(self):
        """ウィンドウを閉じる"""
        close_window_script = f"""
        tell application "System Events"
            tell process "{self.process_name}"
                if exists window 1 then
                    set frontmost to true
                    keystroke "w" using {{command down, shift down}}
                end if
            end tell
        end tell
        """
        result = run(["osascript", "-e", close_window_script], capture_output=True, text=True)
        if result.returncode != 0:
            logging.warning(f"Failed to close window: {result.stderr}")
        else:
            logging.info("Window closed successfully")
        time.sleep(0.5)

    def cleanup(self):
        """リソースのクリーンアップ"""
        pass
