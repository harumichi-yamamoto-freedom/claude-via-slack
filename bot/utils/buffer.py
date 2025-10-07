"""
バッファ管理モジュール
出力バッファの管理とフラッシュ処理
"""
import time
import logging
import threading

from ..config import FLUSH_INTERVAL, PROGRESS_INTERVAL


class OutputBuffer:
    """出力バッファを管理するクラス"""

    def __init__(self, client, channel, thread_ts, enable_streaming, start_time):
        """
        Args:
            client: Slack WebClient
            channel: チャンネルID
            thread_ts: スレッドID
            enable_streaming: ストリーミング有効フラグ
            start_time: 実行開始時刻
        """
        self.client = client
        self.channel = channel
        self.thread_ts = thread_ts
        self.enable_streaming = enable_streaming
        self.start_time = start_time

        self.output_buffer = []
        self.stderr_buffer = []
        self.buffer_lock = threading.RLock()
        self.buffered_len = [0]
        self.last_post_time = [0]
        self.last_progress_time = [time.time()]
        self.stop_flusher = [False]
        self.message_stopped = [False]

    def post_content(self, content: str, wrap_code: bool = False, post_func=None):
        """
        コンテンツをSlackに投稿

        Args:
            content: 投稿内容
            wrap_code: コードブロックで囲むか
            post_func: カスタム投稿関数
        """
        from ..utils.text import sanitize, chunk
        from ..config import MAX_LEN

        logging.info("post_content called with content length: %d, wrap_code: %s", len(content), wrap_code)
        content = sanitize(content)
        if wrap_code and content.strip():
            content = f"```\n{content}\n```"
        for part in chunk(content, MAX_LEN):
            time.sleep(0.2)  # rate limit 緩和
            try:
                logging.info("Posting to Slack: %s", part[:100])
                if post_func:
                    post_func(part)
                else:
                    result = self.client.chat_postMessage(
                        channel=self.channel,
                        thread_ts=self.thread_ts,
                        text=part
                    )
                    logging.info("Posted successfully: %s", result.get("ok"))
            except Exception as e:
                logging.exception("Failed to post to Slack: %s", e)

    def flush(self):
        """バッファの内容をフラッシュ"""
        stdout_payload = ""
        stderr_payload = ""
        is_final_output = False

        with self.buffer_lock:
            if self.output_buffer:
                stdout_payload = "".join(self.output_buffer)
                self.output_buffer.clear()
            if self.stderr_buffer:
                stderr_payload = "".join(self.stderr_buffer)
                self.stderr_buffer.clear()
            self.buffered_len[0] = 0
            is_final_output = self.message_stopped[0]

        logging.info("flush: is_final_output=%s, message_stopped=%s", is_final_output, self.message_stopped[0])

        if stdout_payload:
            self.post_content(stdout_payload, wrap_code=not is_final_output)
        if stderr_payload:
            self.post_content(f"[STDERR]\n{stderr_payload}")

    def append_stdout(self, line: str):
        """標準出力をバッファに追加"""
        logging.info("append_stdout called with: %s", line[:100])

        # 最終出力の場合
        if self.message_stopped[0]:
            # まず残っているバッファをフラッシュ（```付き）
            if self.enable_streaming:
                self.flush()
            # 最終出力を```なしで投稿
            self.post_content(line, wrap_code=False)
            return

        # ストリーミング無効時は中間出力を無視
        if not self.enable_streaming:
            return

        flush = False
        now = time.time()
        with self.buffer_lock:
            self.output_buffer.append(line)
            self.buffered_len[0] += len(line)
            # 初回は last_post_time を設定
            if self.last_post_time[0] == 0:
                self.last_post_time[0] = now
            logging.info("Buffer size: %d, time since last post: %.2f",
                        self.buffered_len[0], now - self.last_post_time[0])

            # ツール実行メッセージ（⏺で始まる）は即座にフラッシュ
            if "⏺" in line:
                flush = True
                self.last_post_time[0] = now
            # FLUSH_INTERVAL秒ごと、または3900文字以上でフラッシュ
            elif (now - self.last_post_time[0] >= FLUSH_INTERVAL) or (self.buffered_len[0] >= 3900):
                flush = True
                self.last_post_time[0] = now

        if flush:
            logging.info("Flushing buffer...")
            self.flush()

    def append_stderr(self, line: str):
        """標準エラーをバッファに追加"""
        flush = False
        now = time.time()
        with self.buffer_lock:
            self.stderr_buffer.append(line)
            # stderr はFLUSH_INTERVALで優先フラッシュ
            if (now - self.last_post_time[0] >= FLUSH_INTERVAL):
                flush = True
                self.last_post_time[0] = now
        if flush:
            self.flush()

    def start_auto_flusher(self):
        """自動フラッシュスレッドを開始"""
        def auto_flusher():
            while not self.stop_flusher[0]:
                time.sleep(0.5)
                if self.stop_flusher[0]:
                    break

                now = time.time()
                should_flush = False

                # ストリーミング無効時はPROGRESS_INTERVAL秒ごとに進捗メッセージを送信
                if not self.enable_streaming:
                    if now - self.last_progress_time[0] >= PROGRESS_INTERVAL:
                        elapsed_seconds = int(now - self.start_time)
                        elapsed_minutes = elapsed_seconds // 60
                        elapsed_secs = elapsed_seconds % 60
                        elapsed_str = f"{elapsed_minutes}分{elapsed_secs}秒" if elapsed_minutes > 0 else f"{elapsed_secs}秒"
                        try:
                            self.client.chat_postMessage(
                                channel=self.channel,
                                thread_ts=self.thread_ts,
                                text=f"実行中...（経過時間: {elapsed_str}）"
                            )
                            self.last_progress_time[0] = now
                        except Exception as e:
                            logging.error("Failed to post progress message: %s", e)

                # ストリーミング有効時のみバッファをチェック
                if self.enable_streaming:
                    with self.buffer_lock:
                        # データがあり、かつFLUSH_INTERVAL以上経過している場合
                        if (self.output_buffer or self.stderr_buffer) and self.last_post_time[0] > 0:
                            if now - self.last_post_time[0] >= FLUSH_INTERVAL:
                                should_flush = True
                                self.last_post_time[0] = now
                    if should_flush:
                        logging.info("Auto-flushing buffer...")
                        self.flush()

        self.flusher_thread = threading.Thread(target=auto_flusher, daemon=True)
        self.flusher_thread.start()
        return self.flusher_thread

    def stop_auto_flusher(self):
        """自動フラッシュスレッドを停止"""
        self.stop_flusher[0] = True
        if hasattr(self, 'flusher_thread'):
            self.flusher_thread.join(timeout=1)

    def clear(self):
        """バッファをクリア"""
        with self.buffer_lock:
            self.output_buffer.clear()
            self.stderr_buffer.clear()
            self.buffered_len[0] = 0
