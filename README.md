# Claude via Slack

SlackからClaude Code CLIを操作するためのボットです。

## 概要

Slackのメンション経由でClaude Code CLIを実行し、結果をスレッド内にストリーミング表示します。
スレッド単位で会話履歴が管理され、同じスレッド内では会話の文脈が保持されます。

## 必要要件

- Python 3.12以上
- Claude Code CLI (Pro/Maxプラン)
- Slackワークスペースとボット権限

## セットアップ

### 1. 依存パッケージのインストール

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 環境変数の設定

`config/.env.example`を`config/.env`にコピーして編集：

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

**機密情報**（次の手順3で取得します）
- `SLACK_BOT_TOKEN`: Slack Bot Token（`xoxb-...`形式）
- `SLACK_APP_TOKEN`: Slack App Token（`xapp-...`形式）

**環境依存パス**
- `CLAUDE_BIN`: Claude CLIの実行パス（デフォルト: `/usr/local/bin/claude`）
- `DEFAULT_CWD`: コマンド実行時のデフォルト作業ディレクトリ（デフォルト: カレントディレクトリ）

**ユーザー設定**
- `EDITOR_CMD`: スクリーンショット撮影に使用するエディタ（`code` または `cursor`、デフォルト: `code`）
- `SCREENSHOT_OS`: OS種別（`macos`, `windows`, `linux`、デフォルト: `macos`）

まずは`SLACK_BOT_TOKEN`と`SLACK_APP_TOKEN`を空欄にしたまま次の手順に進み、トークンを取得後にこのファイルに貼り付けます。

### 3. Slackアプリの作成とトークン取得

1. https://api.slack.com/apps にアクセス

2. 「Create New App」→「From scratch」を選択

3. App NameとWorkspaceを設定

4. **Socket Mode**を有効化：
   - **Socket Mode**ページで「Enable Socket Mode」をONにする
   - **App-Level Token**を作成（`connections:write` スコープが自動で付与されます）
   - トークン名（例: `socket-token`）を入力して作成
   - **App-Level Token** (`xapp-...`)をコピー
   - → `config/.env`の`SLACK_APP_TOKEN`に貼り付け

5. **Event Subscriptions**を設定：
   - **Event Subscriptions**ページで「Enable Events」をONにする
   - **Subscribe to bot events**セクションで以下のイベントを追加：
     - `app_mention` - ボットがメンションされたときのイベント
   - 「Save Changes」をクリック

6. **OAuth & Permissions**で以下のBot Token Scopesを追加：
   - `app_mentions:read` - メンション読み取り
   - `chat:write` - メッセージ送信
   - `channels:history` - 公開チャンネル内の会話履歴取得（スレッド履歴の読み取りに必要）
   - `groups:history` - プライベートチャンネル内の会話履歴取得（スレッド履歴の読み取りに必要）
   - `im:history` - ダイレクトメッセージ内の会話履歴取得（スレッド履歴の読み取りに必要）
   - `mpim:history` - グループダイレクトメッセージ内の会話履歴取得（スレッド履歴の読み取りに必要）
   - `files:write` - ファイルアップロード（スクリーンショット機能で使用）

7. **Install App**からワークスペースにインストール：
   - 「Install to Workspace」をクリック
   - 権限を確認して「許可する」
   - **Bot User OAuth Token** (`xoxb-...`)をコピー
   - → `config/.env`の`SLACK_BOT_TOKEN`に貼り付け

**重要**: Socket Modeを使用するため、Request URLの設定は不要です。

### 4. macOSでのスクリーンショット権限設定

スクリーンショット機能を使用する場合、以下の権限が必要です：

**アクセシビリティ権限の付与**

1. **システム設定** → **プライバシーとセキュリティ** → **アクセシビリティ** を開く
2. 以下のアプリケーションを追加して有効化：
   - ボットを実行するターミナルアプリ（**Terminal.app**、**iTerm2**、**Cursor**、**VS Code**など）
   - スクリーンショット撮影に使用するエディタ（**Visual Studio Code** または **Cursor**）

**画面収録権限の付与**

1. **システム設定** → **プライバシーとセキュリティ** → **画面収録** を開く
2. 以下のアプリケーションを追加して有効化：
   - ボットを実行するターミナルアプリ（**Terminal.app**、**iTerm2**、**Cursor**、**VS Code**など）

**注意**:
- 権限を付与した後は、ターミナルやアプリケーションを再起動してください
- どのターミナルで実行するかによって、権限を付与するアプリが異なります

### 5. Claude Code CLIの認証

**すでにClaude Code CLIのセットアップが完了している場合は、この手順をスキップして手順6に進んでください。**

#### オプションA: Claude Pro/Maxプランを使用する場合（推奨）

1. Claude Code CLIにログイン：
```bash
claude
# ブラウザでOAuth認証を完了
```

2. 環境変数に`ANTHROPIC_API_KEY`が設定されていないことを確認：
```bash
# 現在のセッションで確認
echo $ANTHROPIC_API_KEY

# もし設定されていたら削除
unset ANTHROPIC_API_KEY
```

3. シェル設定ファイル（`.zshrc`, `.bashrc`など）にも`ANTHROPIC_API_KEY`が設定されていないか確認してください。

#### オプションB: Anthropic APIキーを使用する場合

1. https://console.anthropic.com/settings/keys からAPIキーを取得

2. 環境変数を設定（シェル設定ファイルに追加）：
```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
```

3. または、ボット起動前に一時的に設定：
```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
python bot/app.py
```

**注意**: APIキーを使用する場合は従量課金となります。Pro/Maxプランの定額利用とは異なります。

## セキュリティに関する注意

このボットを使用する際は、以下のセキュリティ上の重要な点に注意してください：

### Claude CLIの権限

このボットはClaude CLIを`--permission-mode bypassPermissions`で実行します。これにより：

- **すべての権限確認がスキップされます**
- ファイルの読み取り・書き込み・削除が自動的に許可されます
- シェルコマンドの実行が自動的に許可されます
- ネットワークアクセスが自動的に許可されます

**推奨事項**:
- 信頼できる環境でのみ使用してください
- 重要なファイルがあるディレクトリでの実行は避けてください
- `DEFAULT_CWD`を専用の作業ディレクトリに設定することを推奨します
- 本番環境での使用は十分に注意してください

### Slackボットの権限

このボットは以下のSlackメッセージ履歴を読み取る権限を持ちます：

- 公開チャンネル内のすべてのメッセージ
- プライベートチャンネル内のすべてのメッセージ（ボットが追加されている場合）
- ダイレクトメッセージ
- グループダイレクトメッセージ

**推奨事項**:
- 機密情報を含むチャンネルにはボットを追加しないでください
- 信頼できるワークスペースでのみ使用してください

## 使い方

### ボットの起動

```bash
# 仮想環境をアクティベート（まだの場合）
source venv/bin/activate  # Windows: venv\Scripts\activate

# ボットを起動
python bot/app.py
```

起動時に作業ディレクトリの確認が表示されます：

```
作業ディレクトリ: /path/to/your/project
このディレクトリでClaude CLIが実行されます。
このディレクトリで実行しますか？ (y/n): y

Slack Botを起動しています...
```

- `y`を入力すると起動が続行されます
- `n`を入力すると起動がキャンセルされます
- 作業ディレクトリを変更したい場合は、`config/.env`ファイルの`DEFAULT_CWD`を編集してください

ボットはフォアグラウンドで動作し続けます。外出先から使用する場合は、PCを起動したままにする必要があります。

**リモート使用時の注意事項**:
- **スリープ無効化**: システム設定でスリープを無効にしてください
  - macOS: **システム設定** → **ロックスクリーンとスクリーンセーバー** → **ディスプレイがオフのときにコンピュータを自動でスリープさせない**
  - または、`caffeinate`コマンドを使用:
    ```bash
    caffeinate -i python bot/app.py
    ```
- **ネットワーク接続**: 安定したネットワーク接続を維持してください
- **バックグラウンド実行**: `nohup`や`screen`/`tmux`を使うと、SSH接続が切れても動作し続けます
  ```bash
  # nohupを使う場合（作業ディレクトリ確認で自動的にyを入力）
  echo "y" | nohup python bot/app.py > bot.log 2>&1 &

  # tmuxを使う場合（推奨）
  tmux new -s slack-bot
  python bot/app.py
  # Ctrl+B, D でデタッチ
  ```

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

## 機能

### 会話履歴管理
- **スレッド単位での会話履歴保持**: 同じスレッド内では会話の文脈が自動的に保持されます
- **新規スレッドで新規会話**: 新しいメッセージでは新しい会話が開始されます
- Slackの`conversations.replies` APIを使用して、スレッドから会話履歴を取得
- ユーザーのメッセージとClaudeの最終出力のみを抽出（途中経過やシステムメッセージは除外）
- 最新10往復分の会話を保持（`config.py`の`MAX_HISTORY_MESSAGES`で変更可能）
- 履歴はプロンプトに追加されます

### 実行管理
- リアルタイムストリーミング出力（`stream`モード）
- ツール実行の進捗表示
- バッファリングによるSlack API rate limitの回避
- プロセスの停止・状態確認コマンド

### その他
- 最終出力の自動フォーマット（マークダウン対応）
- スクリーンショット撮影（macOS対応）
- Claude Code CLI Pro/Max プランまたはAnthropic API対応

## アーキテクチャ

```
bot/
├── app.py              # メインアプリケーション
├── config.py           # 設定管理
├── handlers/           # イベントハンドラー
│   ├── message.py      # メンションハンドラー
│   └── commands.py     # コマンド処理
├── claude/             # Claude CLI実行
│   ├── runner.py       # プロセス管理
│   └── events.py       # イベント処理
├── utils/              # ユーティリティ
│   ├── session.py      # セッションID生成
│   ├── buffer.py       # 出力バッファ
│   ├── history.py      # 会話履歴管理
│   └── text.py         # テキスト処理
└── screenshot/         # スクリーンショット
    ├── screenshot.py   # メイン実装
    ├── base.py         # 基底クラス
    └── macos.py        # macOS実装
```

## トラブルシューティング

### `Invalid API key` エラーが出る

環境変数に無効な`ANTHROPIC_API_KEY`が設定されている可能性があります：

```bash
# 環境変数を確認
env | grep ANTHROPIC

# 削除
unset ANTHROPIC_API_KEY
```

### Slackトークンエラー

`config/.env`ファイルが正しく設定されているか確認してください：

```bash
# .envファイルの存在確認
ls -la config/.env

# 内容確認（トークンは表示されないよう注意）
cat config/.env
```
