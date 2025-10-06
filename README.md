# Remote Dev Agent

SlackからClaude CLIを操作するためのボットです。

## 概要

Slackのメンション経由でClaude CLIコマンドを実行し、結果をスレッド内にストリーミング表示します。

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

`config/.env` ファイルを作成し、以下の内容を設定：

```
# 機密情報
SLACK_BOT_TOKEN=xoxb-xxx
SLACK_APP_TOKEN=xapp-1-xxx

# 環境依存パス
CLAUDE_BIN=/usr/local/bin/claude
DEFAULT_CWD=/path/to/your/project

# ユーザー設定
EDITOR_CMD=cursor
SCREENSHOT_OS=macos
```

**機密情報**
- `SLACK_BOT_TOKEN`: Slack Bot Token
- `SLACK_APP_TOKEN`: Slack App Token

**環境依存パス**
- `CLAUDE_BIN`: Claude CLIの実行パス（デフォルト: `/usr/local/bin/claude`）
- `DEFAULT_CWD`: コマンド実行時のデフォルト作業ディレクトリ（デフォルト: カレントディレクトリ）

**ユーザー設定**
- `EDITOR_CMD`: スクリーンショット撮影に使用するエディタ（`code` または `cursor`、デフォルト: `code`）
- `SCREENSHOT_OS`: OS種別（`macos`, `windows`, `linux`、デフォルト: `macos`）

### 3. macOSでのスクリーンショット権限設定

スクリーンショット機能を使用する場合、以下の権限が必要です：

**アクセシビリティ権限の付与**

1. **システム設定** → **プライバシーとセキュリティ** → **アクセシビリティ** を開く
2. 以下のアプリケーションを追加して有効化：
   - **Terminal.app**（Terminalから実行する場合）
   - **Python**（直接Pythonを実行する場合）
   - 使用しているエディタ（**Visual Studio Code** または **Cursor**）

**画面収録権限の付与**

1. **システム設定** → **プライバシーとセキュリティ** → **画面収録** を開く
2. 以下のアプリケーションを追加して有効化：
   - **Terminal.app**（Terminalから実行する場合）
   - **Python**（直接Pythonを実行する場合）

※権限を付与した後は、ターミナルやアプリケーションを再起動してください。

### 4. ボットの起動

```bash
python bot/app.py
```

## 使い方

### 基本的な使い方

Slackでボットをメンションしてプロンプトを送信：

```
@Bot プロンプトをここに書く
```

### ストリーミングモード

`stream` を先頭につけると、実行中の出力をリアルタイムで表示：

```
@Bot stream プロンプトをここに書く
```

※ `stream`なしの場合は、実行完了後に最終結果のみが表示されます（進捗メッセージは1分ごと）。

### コントロールコマンド

- **`@Bot status`**: 実行中のプロセスの状態を確認
- **`@Bot stop`**: 実行中のプロセスを停止

### スクリーンショット機能

ファイルのスクリーンショットを撮影してSlackに送信できます：

```
@Bot screenshot /path/to/file.py --line 42
```

- `--line` オプションで指定行にジャンプしてから撮影
- エディタを自動起動・最大化・撮影・クローズ
- macOS版実装済み（Windows/Linux版は将来実装予定）

**スタンドアロン実行**

```bash
python bot/screenshot/screenshot.py /path/to/file.py --line 42 --output screenshot.png
```

## 機能

- スレッド単位での実行管理
- ツール実行の進捗表示
- バッファリングによるSlack API rate limitの回避
- 最終出力の自動フォーマット（マークダウン対応）
- セッション継続（`.claude_session`ファイル）
- スクリーンショット撮影（macOS対応）
