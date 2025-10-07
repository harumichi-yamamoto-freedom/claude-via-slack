"""
テキスト処理ユーティリティ
"""
import re

ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def sanitize(s: str) -> str:
    """
    Slack表示が崩れないようにANSIエスケープシーケンスを取り除き、CRをLFに変換

    Args:
        s: 入力文字列

    Returns:
        サニタイズされた文字列
    """
    s = ANSI_RE.sub("", s)
    s = s.replace("\r", "")
    return s


def chunk(s: str, n: int):
    """
    文字列を指定サイズのチャンクに分割

    Args:
        s: 入力文字列
        n: チャンクサイズ

    Yields:
        チャンク文字列
    """
    for i in range(0, len(s), n):
        yield s[i : i + n]
