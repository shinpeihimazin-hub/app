# Claude Code リファレンス④ フック・プラグイン・配布

「決定的な自動化」と「まとめて配布」の実装。公式仕様（`code.claude.com/docs/en/hooks`, `.../plugins`, `.../plugins-reference`, `.../output-styles`）ベース。

> 仕様の細部はバージョンで変わる。実装時に公式ドキュメントで確認する。

---

## パート1: フック（Hooks）— 確定的にワークフローを強制する

LLMの判断に任せず、ライフサイクルの特定点で**必ず**スクリプト/HTTP/プロンプトを走らせる。プロンプトでは保証できない挙動（危険コマンドのブロック、編集後のlint強制、ログ記録）に使う。

### フックイベント一覧
| イベント | 発火点 |
|---|---|
| `SessionStart` / `SessionEnd` | セッション開始・終了 |
| `UserPromptSubmit` | Claudeがプロンプト処理する前（ブロック可） |
| `PreToolUse` | ツール実行前（**ブロック可**） |
| `PostToolUse` | ツール成功後 |
| `PostToolBatch` | 並列ツール解決後 |
| `PermissionRequest` | 権限ダイアログ表示時 |
| `Stop` | Claudeの応答終了時 |
| `SubagentStart` / `SubagentStop` | サブエージェント開始・終了 |
| `Notification` | 通知送信時 |
| `PreCompact` / `ConfigChange` / `FileChanged` | 圧縮前 / 設定変更 / 監視ファイル変更 |

### 設定（`settings.json` / plugin の `hooks/hooks.json`）
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "if": "Bash(rm *)",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/block-rm.sh",
            "args": [],
            "timeout": 600
          }
        ]
      }
    ]
  }
}
```
- **3層**: イベント → matcher グループ（`"Bash"`, `"Edit|Write"`, `"*"`=全て。特殊文字はJS正規表現） → ハンドラ。
- **ハンドラtype**: `command` / `http` / `mcp_tool` / `prompt` / `agent`。
- `if`: permissionルール風の絞り込み（`"Bash(git *)"`, `"Edit(*.ts)"`）。
- パス変数: `${CLAUDE_PROJECT_DIR}` / `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}`。

### 入出力プロトコル（command フック）
- **stdin にJSON**が渡る: `session_id`, `hook_event_name`, `cwd`, `permission_mode`, `tool_name`, `tool_input` 等（イベント依存）。
- **終了コード**:
  | code | 意味 | 挙動 |
  |---|---|---|
  | `0` | 成功 | stdoutのJSONを解釈。ツール続行 |
  | `2` | ブロッキングエラー | stderrをClaude/ユーザーに表示し**アクションをブロック** |
  | その他 | 非ブロッキング | stderr先頭行を出し続行 |
- **JSON出力は exit 0 の時だけ**処理。10,000字上限。`/dev/tty` 不可（`terminalSequence` で通知）。
- 決定制御: `PreToolUse` は `hookSpecificOutput.permissionDecision`（`allow`/`deny`/`ask`/`defer`）、`UserPromptSubmit`/`Stop` は top-level `decision: "block"` + `reason`、`PostToolUse` は `updatedToolOutput` で結果差し替え。

### 例: 破壊的Bashをブロック
`.claude/hooks/block-rm.sh`:
```bash
#!/bin/bash
COMMAND=$(jq -r '.tool_input.command')
if echo "$COMMAND" | grep -q 'rm -rf'; then
  jq -n '{hookSpecificOutput: {hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: "破壊的な rm -rf をポリシーでブロック"}}'
else
  exit 0
fi
```

### フックの主な用途
- 危険操作のブロック（`PreToolUse`）／編集後の自動lint・format（`PostToolUse` + `Edit|Write`）／コミット前チェック／セッション開始時の環境準備（`SessionStart`）／プロンプト前の文脈注入（`UserPromptSubmit`）／読み取り専用DBサブエージェントの検証（[`08`](./08-agent-primitives-and-composition.md) の db-reader 例）。

---

## パート2: プラグイン（Plugins）— まとめて配布する

スキル・サブエージェント・フック・MCPサーバー・LSP・output styles を1ディレクトリに束ねて配布・共有する単位。

### ディレクトリ構成
```text
my-plugin/
├── .claude-plugin/
│   └── plugin.json        # マニフェスト（必須）
├── skills/
│   └── my-skill/SKILL.md
├── agents/
│   └── reviewer.md
├── commands/
│   └── deploy.md
├── hooks/
│   └── hooks.json
├── .mcp.json              # 同梱MCPサーバー
└── output-styles/
```
- コンポーネントは既定ディレクトリ（`skills/`, `agents/`, `commands/`, `hooks/`, `.mcp.json`, `output-styles/`）に置けば**自動発見**される。
- プラグイン内のパスは `${CLAUDE_PLUGIN_ROOT}`（同梱ファイル）/ `${CLAUDE_PLUGIN_DATA}`（更新をまたぐ永続データ）。
- 制約: プラグイン由来のサブエージェントは `hooks`/`mcpServers`/`permissionMode` を無視。

### `plugin.json`（`.claude-plugin/plugin.json`）
```json
{
  "name": "deployment-tools",
  "version": "1.2.0",
  "description": "デプロイ関連のスキル・フック・MCPを束ねる",
  "author": { "name": "Dev Team", "email": "dev@company.com" }
}
```
- 必須は実質 `name`（kebab-case）。`version` を設定すると**その文字列を上げた時だけ**ユーザーに更新が届く（開発中は省略してcommit SHA運用が楽）。
- 既定パス以外を使うなら `skills`/`commands`/`agents`/`hooks`/`mcpServers`/`outputStyles` で明示。`defaultEnabled: false` でオプトイン配布。

### マーケットプレイスで配布
`marketplace.json`（`.claude-plugin/marketplace.json`）にプラグインを列挙して公開。ユーザーは:
```text
/plugin marketplace add <owner>/<repo>
/plugin install <plugin>@<marketplace>
/reload-plugins
```
- スキルフォルダに `.claude-plugin/plugin.json` を置くだけで `<name>@skills-dir` プラグインとして**その場で**ロードされる（マーケット不要）。

---

## パート3: Output Styles（出力スタイル）

Claudeの応答の型・トーンを再利用可能な形で切り替える。`.claude/output-styles/` かプラグインの `output-styles/` に置く。用途例: レビュー報告の定型フォーマット、教育的な説明モード、簡潔モード。手順・チェックリストを持たせたいなら[スキル](./09-claude-code-skill-authoring.md)、応答の様式そのものを変えたいなら output style。

---

## この4リファレンスの使い分け（要件 → 実装物）

| やりたいこと | 実装物 | 参照 |
|---|---|---|
| 再利用したい手順・知識・チェックリスト | スキル | [`09`](./09-claude-code-skill-authoring.md) |
| 外部システム/API/DBへの接続（ツール追加） | MCPサーバー（接続 or 自作） | [`10`](./10-claude-code-mcp-servers.md) |
| Claude Code外の自前アプリでツールを持つエージェント | Agent SDK in-processツール / API tool use | [`11`](./11-claude-code-tool-use-and-sdk.md) |
| 独立コンテキストで隔離作業・要約返却 | サブエージェント | [`08`](./08-agent-primitives-and-composition.md) |
| 特定タイミングで確定的に強制する処理 | フック | このファイル パート1 |
| 上記をチームに配布 | プラグイン（＋マーケットプレイス） | このファイル パート2 |
| 応答の様式・トーンを切替 | Output style | このファイル パート3 |

---

## チェックリスト
- [ ] 「LLMの判断」で足りるものをフックにしていない（フックは確定的強制が要る時だけ）
- [ ] フックの終了コード（0/2/その他）と matcher を正しく設計した
- [ ] 破壊的操作・機密に触れる箇所に `PreToolUse` ガードを置いた
- [ ] 配布物は plugin.json の `name`/`version` 運用を決めた
- [ ] プラグイン内パスは `${CLAUDE_PLUGIN_ROOT}` で書いた
