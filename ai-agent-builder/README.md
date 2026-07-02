# AIエージェント・ビルダー・キット

「最強のAIエージェントを作れるエージェント」を実現するための運用マニュアル一式。

作りたいAIエージェントの要件を渡すと、毎回このプロセスを回す。

1. **要件ヒアリング** — 目的・入出力・実行環境・自律度・非機能要件を確定する
2. **ワークフロー分解** — 要件を「入力→処理ステップ→出力」の流れに分解する
3. **タスク・工数分解** — 各ステップを実装可能な作業単位に割り、工数を見積もる
4. **ツール選定** — タスクごとに、Claudeだけに頼らず最適な言語・フレームワーク・モデル・ノーコードツールを比較して選ぶ
5. **プリミティブ探索・再利用・合成（フェーズ3.5）** — 新規に作る前に、既存のサブエージェント／スキル／スラッシュコマンド／MCP／プラグイン／マーケットプレイスを**探索・読込・選定**し、再利用できるものを選ぶ。足りない分だけを、正しいプリミティブ種別で作る
6. **成果物生成** — 「コピペ/保存すれば動く」レベルまで具体化した成果物を出す
7. **評価・反復** — テストして、フィードバックを該当フェーズに戻して回す

このキットはこのフェーズ群を毎回同じ質で再現するためのプロンプト・テンプレート・意思決定マトリクス・基準値をまとめたものであり、**特定のプロジェクトに紐づかない汎用ツールキット**として作ってある。単独リポジトリとして切り出して使うことを想定した自己完結構成。

> **フェーズ3.5がこのキットの心臓部。** 「エージェントを作る」＝ゼロからコードを書く、ではない。既存の部品を探して選び、足りない分だけ正しい形（スキルか、サブエージェントか、MCPか、プラグインか）で作る。この探索・選定の方法論は [`08-agent-primitives-and-composition.md`](./08-agent-primitives-and-composition.md) に集約してある。

## 使い方（最短ルート）

1. [`00-meta-agent-prompt.md`](./00-meta-agent-prompt.md) の中身をまるごとコピーして、Claude（や他のLLM）のシステムプロンプト／カスタム指示として渡す。これが「エージェントを作るエージェント」本体になる。
2. 作りたいエージェントの要件を投げる。曖昧でもよい。フェーズ0のヒアリングが足りない部分を埋めてくれる（人間が埋める場合は [`01-intake-and-requirements.md`](./01-intake-and-requirements.md) を使う）。
3. 出てくるワークフロー分解・タスク分解・ツール選定・成果物を、各フェーズごとに確認しながら進める。
4. 迷ったら以下の各ファイルを直接参照する。

## ファイル構成

| ファイル | 内容 | いつ使うか |
|---|---|---|
| [`00-meta-agent-prompt.md`](./00-meta-agent-prompt.md) | コピペで使えるメタエージェントのシステムプロンプト本体 | 最初に1回セットする |
| [`01-intake-and-requirements.md`](./01-intake-and-requirements.md) | 要件ヒアリングの質問項目・記入例 | フェーズ0 |
| [`02-workflow-decomposition.md`](./02-workflow-decomposition.md) | ワークフロー分解の型・代表的なエージェント設計パターン | フェーズ1 |
| [`03-task-and-effort-breakdown.md`](./03-task-and-effort-breakdown.md) | タスク分解の型・工数見積りの基準表 | フェーズ2 |
| [`04-tool-selection-matrix.md`](./04-tool-selection-matrix.md) | モデル/フレームワーク/DB/評価/デプロイの選定マトリクス | フェーズ3 |
| [`08-agent-primitives-and-composition.md`](./08-agent-primitives-and-composition.md) | **サブエージェント/スキル/スラッシュコマンド/MCP/プラグインの正確な仕様・使い分け・探索と選定の決定木**（公式仕様ベース） | **フェーズ3.5（心臓部）** |
| [`05-build-and-output-templates.md`](./05-build-and-output-templates.md) | 実働テンプレ集（A システムプロンプト / B 素のSDK / C LangGraph HITL / D CrewAI / E MCP / F n8n / G Claude Code拡張 / H 評価 / I OpenAI Agents SDK / J RAG(pgvector) / K ガードレール / L ストリーミング / M 可観測性 / N Docker＋CI） | フェーズ4 |
| [`09-claude-code-skill-authoring.md`](./09-claude-code-skill-authoring.md) | **Claude Code実装リファレンス① スキルを実装する完全版**（frontmatter全項目/動的注入/引数/progressive disclosure/scripts/context:fork/評価） | 実装 |
| [`10-claude-code-mcp-servers.md`](./10-claude-code-mcp-servers.md) | **同② MCPで外部ツールを実装・接続**（Tools/Resources/Prompts、transports、scope、Python/TS） | 実装 |
| [`11-claude-code-tool-use-and-sdk.md`](./11-claude-code-tool-use-and-sdk.md) | **同③ API tool use（関数呼び出し）＋Agent SDKカスタムツール＋ビルトインツール表** | 実装 |
| [`12-claude-code-hooks-and-plugins.md`](./12-claude-code-hooks-and-plugins.md) | **同④ フック（確定的自動化）＋プラグイン配布＋output styles** | 実装 |
| [`13-advanced-agent-patterns.md`](./13-advanced-agent-patterns.md) | **Building Effective Agents**（ワークフローvsエージェント、5ワークフローパターン＋自律エージェント、中核原則）をClaude Codeプリミティブへ対応 | フェーズ1（高度） |
| [`14-prompt-and-context-engineering.md`](./14-prompt-and-context-engineering.md) | **プロンプト／コンテキストエンジニアリング**（system prompt設計、ツール記述ACI、思考/effort、並列ツール、長期state管理、自律と安全、失敗モード対処） | フェーズ4 |
| [`15-bedrock-vertex-deployment.md`](./15-bedrock-vertex-deployment.md) | **Amazon Bedrock / Google Vertex AI 実運用**（設定・認証・モデルpin・IAM・キャッシュ・1M・ガードレール・Mantle・トラブルシュート） | デプロイ（エンタープライズ） |
| [`16-claude-code-memory-and-permissions.md`](./16-claude-code-memory-and-permissions.md) | **メモリ（CLAUDE.md階層・rules/・imports・auto memory）と権限（ルール構文・deny→ask→allow評価・settings階層）** | 実装（挙動の基盤） |
| [`17-claude-code-advanced-operations.md`](./17-claude-code-advanced-operations.md) | **運用系周辺機能**（sandboxのOS層隔離・checkpoint/`/rewind`・`/loop`とcron/Routines・agent teams vs サブエージェント・Monitor/Channels） | 運用 |
| [`anthropic-academy-coverage.md`](./anthropic-academy-coverage.md) | **Anthropic Academy カバレッジマップ**（各コース×キット対応、網羅の証跡） | 網羅確認 |
| [`06-evaluation-and-iteration.md`](./06-evaluation-and-iteration.md) | 評価方法・改善ループの回し方 | フェーズ5 |
| [`07-worked-example.md`](./07-worked-example.md) | 通し実演2例（例1=線形＋HITL/保守性優先、例2=パターン合成/精度優先。同じフェーズでも優先順位で選択が真逆になる対比） | 迷ったとき・型を掴みたいとき |
| `templates/phase0〜3-*.md` | 各フェーズで使う空テンプレート（コピーして埋める用） | 各フェーズ |
| [`templates/agent-builder.subagent.md`](./templates/agent-builder.subagent.md) | **このビルダー自身**を Claude Code のサブエージェントとして常駐させる完成テンプレ | 常駐化 |
| [`templates/agent-builder.SKILL.md`](./templates/agent-builder.SKILL.md) | **このビルダー自身**を Claude Code のスキル（`/agent-builder`）として常駐させる完成テンプレ | 常駐化 |

## 運用ルール（4行）

- **分解と見積りを飛ばしていきなり実装に入らない。** 「とりあえずClaudeに投げて動くもの作る」は最強のエージェントには辿り着かない。
- **ツール選定は「Claudeで全部やる」を初期仮説にしない。** タスクごとに毎回マトリクスで比較検討し、根拠つきで選ぶ。他のLLM・フレームワーク・ノーコード・自作コードすべてが候補。
- **新規に部品を作る前に、必ず既存プリミティブを探索・読込・選定する（フェーズ3.5）。** 「無かった／不十分だった」の探索結果を根拠として示さない「新しく作りましょう」は不採用。
- **出力は毎回「そのまま動かせる／貼れる」形にする。** 説明・助言だけで終わらせない。

## 単独リポジトリとして切り出す

このディレクトリは自己完結しているので、そのまま新しいリポジトリにできる。`git subtree` で履歴ごと切り出す例:

```bash
# 1. このディレクトリだけを履歴付きで新ブランチに分離
git subtree split --prefix=ai-agent-builder -b ai-agent-builder-only

# 2. 空の新リポジトリを作って push（<URL> は新規作成したリポジトリのもの）
git push <新リポジトリのURL> ai-agent-builder-only:main
```

履歴が不要なら、ディレクトリをコピーして `git init` するだけでもよい:

```bash
cp -r ai-agent-builder /path/to/ai-agent-builder-kit
cd /path/to/ai-agent-builder-kit && git init && git add . && git commit -m "init: AIエージェント・ビルダー・キット"
# その後、新リポジトリを作成して push
```

## このキットの前提

- 特定の言語・クラウド・LLMベンダーに縛られない。案件ごとに最適解が変わる前提で作ってある。
- 「最強」の基準は案件によって変わる（速度優先、精度優先、コスト優先、保守性優先）。フェーズ0で必ずこの優先順位を確定させる。
- ツール・フレームワークのエコシステムは変化が速い。`04-tool-selection-matrix.md` は定期的に見直すことを前提に、選定基準（軸）を先に固定し、個別ツール名は入れ替え可能な形で書いてある。

## 鮮度管理

- **最終検証日: 2026-07-02**（全ファイル。Claude Code / API / MCP は公式ドキュメント、第三者FW（LangGraph / OpenAI Agents SDK 等）は公式ドキュメント・現行API情報と突き合わせて検証）。
- モデルID・フロントマター仕様・SDKのAPIは変わる。**この日付から時間が経っているほど、実装前の公式確認（各ファイルの但し書き参照）を厚めに**。再検証したらこの日付を更新する。
