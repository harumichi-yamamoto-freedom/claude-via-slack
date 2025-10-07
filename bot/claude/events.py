"""
Claude CLIイベント処理モジュール
"""
import json
import logging


class EventHandler:
    """Claude CLIのイベントを処理するクラス"""

    def __init__(self, on_stdout, current_tools, message_stopped):
        """
        Args:
            on_stdout: 標準出力コールバック
            current_tools: ツール実行状態を保持する辞書
            message_stopped: メッセージ停止フラグ
        """
        self.on_stdout = on_stdout
        self.current_tools = current_tools
        self.message_stopped = message_stopped

    def handle_event(self, evt: dict):
        """
        イベントを処理

        Args:
            evt: イベント辞書
        """
        etype = evt.get("type", "")

        # stream_event の場合は、ネストされた event を取得
        if etype == "stream_event":
            nested_event = evt.get("event", {})
            etype = nested_event.get("type", "")
            evt = nested_event

        logging.info("Event type: %s, full event: %s", etype, json.dumps(evt)[:300])

        # イベントタイプごとに処理
        if etype == "result":
            self._handle_result(evt)
        elif etype == "content_block_start":
            self._handle_content_block_start(evt)
        elif etype == "content_block_stop":
            self._handle_content_block_stop(evt)
        elif etype in ("content_block_delta", "message_delta"):
            self._handle_delta(evt)
        elif etype == "tool_result_delta":
            self._handle_tool_result_delta(evt)
        elif etype == "tool_result":
            self._handle_tool_result(evt)
        elif etype == "user":
            self._handle_user_message(evt)
        elif isinstance(evt.get("text"), str):
            # トップレベルのtext
            text = evt["text"]
            logging.info("Extracted text (top-level): %s", text[:50])
            self.on_stdout(text)

    def _handle_result(self, evt: dict):
        """resultイベント処理（最終出力）"""
        logging.info("!!! result event detected - this is final output !!!")
        self.message_stopped[0] = True
        final_result = evt.get("result", "")
        if final_result:
            self.on_stdout(final_result)

    def _handle_content_block_start(self, evt: dict):
        """content_block_startイベント処理（ツール使用開始）"""
        content_block = evt.get("content_block", {})
        if content_block.get("type") == "tool_use":
            index = evt.get("index", 0)
            tool_name = content_block.get("name", "Unknown")
            tool_id = content_block.get("id", "")
            self.current_tools[index] = {
                "name": tool_name,
                "input_parts": [],
                "id": tool_id
            }

    def _handle_content_block_stop(self, evt: dict):
        """content_block_stopイベント処理（ツール入力完了）"""
        index = evt.get("index", 0)
        if index in self.current_tools:
            tool_info = self.current_tools.pop(index)
            full_input = "".join(tool_info["input_parts"])
            try:
                input_json = json.loads(full_input) if full_input else {}
            except (json.JSONDecodeError, ValueError, TypeError):
                input_json = full_input

            tool_msg = f"\n⏺ {tool_info['name']}({json.dumps(input_json, ensure_ascii=False)})\n  ⎿ Running…\n"
            self.on_stdout(tool_msg)

    def _handle_delta(self, evt: dict):
        """content_block_delta/message_deltaイベント処理（増分テキスト）"""
        delta = evt.get("delta") or {}
        delta_type = delta.get("type", "")

        # ツール入力の蓄積
        if delta_type == "input_json_delta":
            index = evt.get("index", 0)
            if index in self.current_tools:
                partial_json = delta.get("partial_json", "")
                self.current_tools[index]["input_parts"].append(partial_json)
            return

        # テキストデルタ
        if delta_type in ("text_delta", "output_text_delta"):
            text = delta.get("text", "")
            logging.info("Extracted text (delta): %s", text[:50])
            self.on_stdout(text)

    def _handle_tool_result_delta(self, evt: dict):
        """tool_result_deltaイベント処理（ツールの増分テキスト）"""
        delta = evt.get("delta") or {}
        if delta.get("type") == "output_text_delta":
            text = delta.get("text", "")
            logging.info("Extracted text (tool_result_delta): %s", text[:50])
            self.on_stdout(text)

    def _handle_tool_result(self, evt: dict):
        """tool_resultイベント処理（ツールの最終まとめ）"""
        for c in (evt.get("content") or []):
            if isinstance(c, dict) and c.get("type") == "output_text":
                text = c.get("text", "")
                logging.info("Extracted text (tool_result): %s", text[:50])
                self.on_stdout(text)

    def _handle_user_message(self, evt: dict):
        """userイベント処理（ツール結果）"""
        message = evt.get("message", {})
        content_list = message.get("content", [])
        for item in content_list:
            if isinstance(item, dict) and item.get("type") == "tool_result":
                result_content = item.get("content", "")
                # 結果が長い場合は省略
                if isinstance(result_content, str):
                    lines = result_content.split("\n")
                    if len(lines) > 5:
                        preview = "\n".join(lines[:5]) + f"\n  … +{len(lines) - 5} lines"
                    else:
                        preview = result_content
                    # ツール結果を投稿
                    self.on_stdout(f"\n{preview}\n")
