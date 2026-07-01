# Anthropic Academy カバレッジマップ

「Anthropic Academy で出る内容は全て網羅は最低ライン」の達成状況を、Academy の各コースとキットの対応で示す。Academy は無料・メール登録のみ。開発者向けディープダイブを中心に、Claude Code であらゆるスキル・ツールを実装するのに必要な範囲を対応づけた。

> 出典: [Anthropic Academy / Courses](https://anthropic.skilljar.com/) ・ [anthropic.com/learn](https://www.anthropic.com/learn)。カリキュラムは更新されるため、リンク先で最新のコース構成を確認する。

## コース × キット対応表

| Academy コース | 主な学習内容 | キットでの対応 | 状態 |
|---|---|---|---|
| **Claude Code** | codebaseの読み書き、コマンド実行、エージェント的コーディング | [`08`](./08-agent-primitives-and-composition.md)〜[`12`](./12-claude-code-hooks-and-plugins.md) 全体、ビルトインツール表（[`11 §4`](./11-claude-code-tool-use-and-sdk.md)） | ✅ |
| **Agent Skills** | Skillの構築・設定・共有、自動適用 | [`09`](./09-claude-code-skill-authoring.md)（全機能: frontmatter/動的注入/引数/progressive disclosure/scripts/context:fork/評価） | ✅ |
| **Subagents** | サブエージェントで文脈管理・委譲・専門ワークフロー | [`08 §2`](./08-agent-primitives-and-composition.md)（frontmatter全項目・ツール制限・model routing・チェーン/並列/ネスト） | ✅ |
| **Building with the Claude API** | API基礎・高度プロンプト・**tool use**・RAG・自動化・マルチモーダル | [`11 §1-2`](./11-claude-code-tool-use-and-sdk.md)（tool use/tool_choice/エージェントループ/RAG/マルチモーダル/構造化）、[`04`](./04-tool-selection-matrix.md)（RAG基盤） | ✅ |
| **Introduction to MCP** | Python でサーバー/クライアントを**ゼロから**構築。3プリミティブ（Tools/Resources/Prompts） | [`10 §1,§3,§4`](./10-claude-code-mcp-servers.md)（3プリミティブ、Python/TS実装、接続） | ✅ |
| **MCP: Advanced Topics** | sampling / notifications / filesystem / transports、本番サーバー | [`10 §5`](./10-claude-code-mcp-servers.md)（sampling/list_changed/transports/再接続/channel） | ✅ |
| **Claude with Amazon Bedrock** | Bedrock 上での Claude 運用（設定〜本番） | [`15`](./15-bedrock-vertex-deployment.md)（設定・認証・モデルpin・IAM・キャッシュ・1M・ガードレール・Mantle・トラブルシュート） | ✅ |
| **Claude with Google Vertex AI** | Vertex AI 上での Claude 運用（設定〜本番） | [`15`](./15-bedrock-vertex-deployment.md)（設定・認証・region・モデルpin・IAM・キャッシュ・tool search・トラブルシュート） | ✅ |
| **AI Fluency / Claude 101** | 非技術者向けの Claude 活用（4E: Effective/Efficient/Ethical/Safe） | 本キットは「エージェント構築」に特化。非技術者向け一般活用は対象外（意図的スコープ外） | ⛔ 対象外 |

## 網羅の判定

- **開発者ディープダイブ（Claude Code / Agent Skills / Subagents / Claude API tool use / MCP入門 / MCP応用）＝このキットの主対象は網羅済み（✅）。** 「あらゆるスキル・ツールを Claude Code で実装する」に必要な範囲を、公式仕様ベースで [`08`](./08-agent-primitives-and-composition.md)〜[`12`](./12-claude-code-hooks-and-plugins.md) に落とした。
- **Bedrock / Vertex AI 運用も網羅（✅）。** [`15`](./15-bedrock-vertex-deployment.md) に設定・認証・モデルpin・IAM・キャッシュ・1M context・ガードレール・Mantle・トラブルシュートまで公式仕様ベースで収録。残る「クラウドネイティブなAPIアプリ構築」の細部（各クラウドSDK固有のアプリ実装）は本キットの目的外だが、Claude Code/Agent SDK をこの2クラウドで動かす運用は満たしている。
- **⛔ 対象外**: 非技術者向けの一般 Claude 活用（Claude 101 / AI Fluency）は、本キットの目的（AIエージェントを作るエージェント）とスコープが異なるため意図的に含めない。

## Academy を超えてキットが持つもの（Academyの範囲外の実務補強）

Academy が扱わない、実運用で必須の領域も入れてある。

- **要件ヒアリング → ワークフロー分解 → 工数見積り**（[`01`](./01-intake-and-requirements.md)〜[`03`](./03-task-and-effort-breakdown.md)）
- **プリミティブ選定の決定木と再利用優先の探索手順**（[`08`](./08-agent-primitives-and-composition.md)）
- **フック／プラグイン／output styles／配布**（[`12`](./12-claude-code-hooks-and-plugins.md)）
- **安全設計**（最小権限・プロンプトインジェクション・信頼境界: [`08 §6.5`](./08-agent-primitives-and-composition.md)）
- **評価・回帰・反復ループ**（[`06`](./06-evaluation-and-iteration.md)）
- **非Claude系ツール（他LLM/LangGraph/n8n/ベクトルDB等）との比較選定**（[`04`](./04-tool-selection-matrix.md)）

## 一次情報リンク（実装時に最新確認）

- Claude Code ドキュメント索引: https://code.claude.com/docs/llms.txt
- スキル: https://code.claude.com/docs/en/skills ／ サブエージェント: https://code.claude.com/docs/en/sub-agents
- MCP: https://code.claude.com/docs/en/mcp ／ MCP標準: https://modelcontextprotocol.io
- フック: https://code.claude.com/docs/en/hooks ／ プラグイン: https://code.claude.com/docs/en/plugins-reference
- Agent SDK: https://code.claude.com/docs/en/agent-sdk/overview ／ カスタムツール: https://code.claude.com/docs/en/agent-sdk/custom-tools
- API tool use: https://platform.claude.com/docs/en/build-with-claude/tool-use/overview
- Anthropic Academy: https://anthropic.skilljar.com/ ／ https://www.anthropic.com/learn
