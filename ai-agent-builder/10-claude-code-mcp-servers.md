# Claude Code リファレンス② MCPサーバーで外部ツールを実装・接続する

「あらゆるツールを実装できる」ための、外部システム接続の完全手順。公式仕様（`code.claude.com/docs/en/mcp`、`modelcontextprotocol.io`）ベース。MCPは Claude Code に**カスタムツールを足す標準の方法**（To add custom tools, connect an MCP server — 公式tools-reference）。

> 自作の前に、まず既存サーバーを探す（[Anthropic Directory](https://claude.ai/directory)、公式/コミュニティ）。[`08 §0`](./08-agent-primitives-and-composition.md) の再利用優先。

---

## 1. MCPの3プリミティブ（Academy「MCP入門」の核）

MCPサーバーが公開できるものは3種類。要件をこれに割り付ける。

| プリミティブ | 何か | 主導権 | 例 |
|---|---|---|---|
| **Tools** | Claudeが呼ぶ関数（副作用OK） | モデルが呼ぶ | `create_ticket`, `run_query`, `send_email` |
| **Resources** | Claudeが読めるデータ（URIで識別） | アプリ/ユーザーが渡す | ファイル内容、DBレコード、ドキュメント |
| **Prompts** | 再利用可能なプロンプトテンプレート | ユーザーが起動 | 定型の分析・レビュー手順 |

「呼ばせて動かす」= Tools、「読ませる文脈」= Resources、「定型プロンプト」= Prompts。多くの実装は Tools が中心。

---

## 2. 既存サーバーを接続する（`claude mcp add`）

### HTTP（リモート、OAuth対応。推奨の第一候補）
```bash
claude mcp add --transport http notion https://mcp.notion.com/mcp
# ヘッダ認証つき
claude mcp add --transport http secure-api https://api.example.com/mcp \
  --header "Authorization: Bearer TOKEN"
```
`.mcp.json` の `type` は `streamable-http` を `http` の別名として受ける（サーバー付属の設定をそのまま貼れる）。

### SSE（サーバー送信イベント）
```bash
claude mcp add --transport sse asana https://mcp.asana.com/sse
```

### stdio（ローカルプロセス。システムアクセスや自作スクリプト向け）
```bash
claude mcp add --transport stdio airtable --env AIRTABLE_API_KEY=KEY -- npx -y airtable-mcp-server
# -- の後ろはサーバー起動コマンド。以降は素通しで渡る
```

### WebSocket（双方向・サーバーからpush）
```bash
claude mcp add-json events-server '{"type":"ws","url":"wss://mcp.example.com/socket","headers":{"Authorization":"Bearer TOKEN"}}'
```

### スコープ（`--scope`）
| スコープ | 範囲 | 共有 | 保存先 |
|---|---|---|---|
| `local`（既定） | 現プロジェクトのみ・自分だけ | 否 | `~/.claude.json` |
| `project` | 現プロジェクト | **VCSで共有** | `.mcp.json`（リポジトリルート） |
| `user` | 全プロジェクト・自分 | 否 | `~/.claude.json` |

管理コマンド: `claude mcp list` / `claude mcp get <name>` / `claude mcp remove <name>`。project スコープはワークスペース信頼後に承認される（`⏸ Pending approval`）。

### `.mcp.json`（プロジェクトで共有する形）
```json
{
  "mcpServers": {
    "stripe":   { "type": "http", "url": "https://mcp.stripe.com" },
    "db-tools": { "command": "python", "args": ["server.py"], "env": { "DB_URL": "${DB_URL}" } }
  }
}
```
- タイムアウトは各エントリに `"timeout": 600000`（ms）。
- 名前解決: MCPツールは Claude から `mcp__<server>__<tool>` で見える（例 `mcp__weather__get_temperature`）。プラグイン同梱は `mcp__plugin_<plugin>_<server>__<tool>`。

---

## 3. 自作サーバー: Python（`mcp` SDK / FastMCP）

Academy「MCP入門」で扱う Python 実装。Tools/Resources/Prompts の3つを1ファイルで。

```python
# server.py  (依存: pip install mcp)
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-tools")

# --- Tool（Claudeが呼ぶ。副作用OK。型ヒントからスキーマ生成） ---
@mcp.tool()
def create_ticket(title: str, body: str) -> str:
    """課題管理にチケットを作成し、URLを返す。"""
    # 実処理（API呼び出し等）
    return "https://tracker.example.com/TICKET-123"

# --- Resource（Claudeが読むデータ。URIで識別） ---
@mcp.resource("config://app")
def get_config() -> str:
    """アプリ設定を返す。"""
    return "設定内容..."

# 動的Resource（パラメータ付き）
@mcp.resource("user://{user_id}/profile")
def get_profile(user_id: str) -> str:
    return f"user {user_id} のプロフィール"

# --- Prompt（再利用テンプレート） ---
@mcp.prompt()
def review_code(code: str) -> str:
    return f"次のコードをレビューして問題点を挙げて:\n\n{code}"

if __name__ == "__main__":
    mcp.run()  # 既定 stdio。HTTP等は transport 指定
```

接続:
```bash
claude mcp add --transport stdio my-tools -- python /abs/path/server.py
```

### トランスポートの使い分け（自作時）
- **stdio**: ローカル・単一ユーザー・システムアクセス。最も簡単。認証不要。
- **HTTP (streamable-http)**: リモート・複数ユーザー・OAuth対応。本番配布はこれ。
- **SSE**: サーバーからのストリーム。
- **WebSocket**: サーバーが能動的にpushする双方向（HTTPはOAuth・`--transport`対応、WSは非対応）。

---

## 4. 自作サーバー: TypeScript（`@modelcontextprotocol/sdk`）

```typescript
// server.ts  (依存: npm i @modelcontextprotocol/sdk zod)
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({ name: "my-tools", version: "1.0.0" });

server.tool(
  "create_ticket",
  { title: z.string(), body: z.string() },
  async ({ title, body }) => ({
    content: [{ type: "text", text: "https://tracker.example.com/TICKET-123" }]
  })
);

server.resource("config", "config://app", async (uri) => ({
  contents: [{ uri: uri.href, text: "設定内容..." }]
}));

const transport = new StdioServerTransport();
await server.connect(transport);
```

---

## 5. MCP応用（Academy「MCP: Advanced Topics」の範囲）

本番サーバーで押さえる論点。詳細は各SDK/仕様を参照。

- **Sampling**: サーバーがクライアント（Claude）にLLM生成を依頼する逆方向の呼び出し。サーバー側ロジックにモデル推論を組み込める。
- **Notifications / `list_changed`**: サーバーがツール/リソース/プロンプトの一覧変更を通知すると、Claude Code は再接続なしで能力を更新する。
- **ファイルシステム/システムアクセス**: stdio サーバーでローカル資源に直接アクセス。権限・パス境界に注意。
- **transport 選定**: 上記§3。本番配布は HTTP + OAuth。
- **接続の堅牢性**: HTTP/SSE は切断時に指数バックオフで最大5回自動再接続。stdio は自動再接続されない。
- **チャネル化**: MCPサーバーは[channel](https://code.claude.com/docs/en/channels)として、外部イベント（Telegram/Discord/Webhook）をセッションに push できる。

---

## 6. サブエージェント専用MCP（親の文脈を汚さない）

特定サブエージェントだけにサーバーを与え、そのツール説明をメイン会話に出さない。

```yaml
---
name: browser-tester
description: 実ブラウザで機能をテストする
mcpServers:
  - playwright:
      type: stdio
      command: npx
      args: ["-y", "@playwright/mcp@latest"]
  - github          # 既存サーバーを名前参照で再利用
---
Playwrightツールでページを操作・スクショ・検証する。
```
インライン定義はサブエージェント起動時に接続、終了時に切断。詳細は [`08 §2`](./08-agent-primitives-and-composition.md)。

---

## 7. どの実装形にするかの判断

| 状況 | 実装 |
|---|---|
| 既存の公式/コミュニティサーバーがある | **接続のみ**（自作しない）。`claude mcp add` |
| 社内API/DBを複数エージェント・複数製品で再利用 | **自作MCPサーバー**（stdio→社内、HTTP→配布） |
| 1つのエージェント/アプリ内でしか使わない、Agent SDKで組む | **SDKのin-processカスタムツール**（[`11 §3`](./11-claude-code-tool-use-and-sdk.md)）。別プロセス不要 |
| Claude Code内の手順・知識の再利用（外部接続なし） | **スキル**（[`09`](./09-claude-code-skill-authoring.md)） |
| まとめてチーム配布 | **プラグイン**にMCPを同梱（[`12`](./12-claude-code-hooks-and-plugins.md)） |

---

## チェックリスト
- [ ] 自作前に既存サーバー（Directory/公式/コミュニティ）を探した
- [ ] Tools/Resources/Prompts のどれで要件を満たすか割り付けた
- [ ] トランスポート（stdio/HTTP/SSE/WS）を用途で選んだ
- [ ] スコープ（local/project/user）を共有要否で選んだ
- [ ] 認証・機密情報（env/ヘッダ/OAuth）の扱いを決めた
- [ ] メイン会話に出したくないサーバーはサブエージェントの `mcpServers` に隔離した
