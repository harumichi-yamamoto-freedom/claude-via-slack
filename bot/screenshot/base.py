"""
スクリーンショット機能の基底クラス
OS固有の実装はサブクラスで行う
"""
from abc import ABC, abstractmethod
from typing import Tuple, Optional


class ScreenshotHandler(ABC):
    """スクリーンショットハンドラーの基底クラス"""

    def __init__(self, editor_cmd: str, default_cwd: str):
        """
        Args:
            editor_cmd: エディタコマンド（"code" or "cursor"）
            default_cwd: デフォルト作業ディレクトリ
        """
        self.editor_cmd = editor_cmd
        self.default_cwd = default_cwd

    @abstractmethod
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
            line_number: ジャンプする行番号（オプション）
            output_path: 出力先パス（指定しない場合は一時ファイル）

        Returns:
            (成功フラグ, メッセージ, スクリーンショットファイルパス)
        """
        pass

    @abstractmethod
    def cleanup(self):
        """リソースのクリーンアップ"""
        pass
