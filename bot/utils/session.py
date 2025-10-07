"""
ユーティリティ関数モジュール
"""
import uuid


def thread_ts_to_session_id(thread_ts: str) -> str:
    """
    スレッドIDから一貫性のあるUUIDを生成
    同じthread_tsからは常に同じUUIDが生成される

    Args:
        thread_ts: SlackスレッドのタイムスタンプID

    Returns:
        UUID文字列
    """
    # thread_tsをハッシュ化してUUIDv5を生成
    namespace = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')  # DNS namespace UUID
    return str(uuid.uuid5(namespace, thread_ts))
