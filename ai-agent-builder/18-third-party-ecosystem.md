# サードパーティ・エコシステム（エージェントの幅を広げる）

Claude単体・テキスト完結のエージェントに閉じず、**モダリティ（ブラウザ操作・音声・コンピュータ操作・データ処理）**と**サードパーティ製の部品**まで広げるためのカタログ。[`04`](./04-tool-selection-matrix.md) が「選定の軸」、このファイルは「候補の地図」。フェーズ3（ツール選定）とフェーズ3.5（再利用探索）で使う。

> **このファイルは最も陳腐化が速い。** 個別ツールの状況（スター数・GA/実験・買収）は数ヶ月で変わる。ここでは「カテゴリと代表と選び方」を固定し、採用前に必ず各公式で現状確認する（最終検証日はREADME参照）。

---

## 1. エージェントのモダリティ（何を操作するエージェントか）

「テキストin/テキストout」の外に広げるときの選択肢。**要件のモダリティが決まると、使う部品群が決まる。**

| モダリティ | 何をする | 主な部品（下記§で詳述） |
|---|---|---|
| コーディング | リポジトリの読み書き・実行 | Claude Code / Agent SDK（[`08`](./08-agent-primitives-and-composition.md)〜[`12`](./12-claude-code-hooks-and-plugins.md)） |
| **ブラウザ操作** | Webサイトの閲覧・操作・抽出 | Playwright MCP / Stagehand / browser-use / Browserbase（§4-1） |
| **コンピュータ操作** | 画面を見てマウス・キーボード操作 | Claude computer use（vision駆動。[`11`](./11-claude-code-tool-use-and-sdk.md) サーバーツール） |
| **音声** | リアルタイム会話（電話・音声UI） | LiveKit Agents / Pipecat / 各社音声プラットフォーム（§4-2） |
| データ処理 | 大量文書・データの一括処理 | Batch API（[`11 §2`](./11-claude-code-tool-use-and-sdk.md)）＋ドキュメント解析（§4-4） |
| 組み込み（製品内） | 自社アプリの機能として同梱 | Agent SDK / 各社SDK＋ガードレール（[`05`](./05-build-and-output-templates.md)） |

**ブラウザ系の重要な設計判断（2026時点の定説）**: アプローチは**DOM駆動**（Playwright/Stagehand/browser-use＝要素を構造で掴む。一般に信頼性が高い）と**vision駆動**（computer use＝画面像で操作。canvasだけのUIやアンチボット画面など、DOMで届かない領域に効く）に二分される。実務は**ハイブリッド**が定番——予測可能な8割はPlaywrightの決定的スクリプト、AIの理解が要る2割だけエージェント操作。

---

## 2. 既製MCPサーバー・カタログ（自作の前にここを見る）

フェーズ3.5の再利用探索（[`08 §0`](./08-agent-primitives-and-composition.md)）で最初に当たる棚。接続方法は [`10`](./10-claude-code-mcp-servers.md)。[Anthropic Directory](https://claude.ai/directory) と各公式リポジトリで最新を確認。

| 領域 | 代表的な既製サーバー | 典型用途 |
|---|---|---|
| 開発 | GitHub / GitLab / Sentry | issue・PR操作、エラー監視の文脈取り込み |
| ブラウザ | **Playwright MCP** / Chrome DevTools系 | E2Eテスト、Web操作・スクショ（§4-1） |
| ドキュメント/PM | Notion / Linear / Jira / Asana | タスク・ドキュメントの読み書き |
| コミュニケーション | Slack / Gmail系 | 通知・下書き・要約 |
| DB | PostgreSQL / SQLite / 各社DBaaS | 自然言語→クエリ、スキーマ把握 |
| 決済/SaaS | Stripe ほか各社公式 | 業務APIの安全な呼び出し |
| デザイン | Figma | デザイン→実装の文脈取り込み |
| 検索 | Tavily / Exa / Brave Search のMCP | エージェント向けWeb検索（§4-3） |
| ライブラリ文書 | Context7 等 | 最新のAPIドキュメントを文脈へ |

**採用時の注意**: サードパーティMCPは**ツール定義がそのまま文脈に入り、外部にデータが出る**。①信頼できる提供元か（公式優先）②要るツールだけに絞る（`mcp__server__tool` 単位の許可: [`16`](./16-claude-code-memory-and-permissions.md)）③機微データを扱うサーバーはサブエージェントに隔離（[`08 §2`](./08-agent-primitives-and-composition.md)）——を必ず通す。

---

## 3. フレームワーク・ランドスケープ拡張（[`04`](./04-tool-selection-matrix.md) カテゴリ2の続き）

`04`の主要候補（素のSDK / Claude Agent SDK / LangGraph / CrewAI / OpenAI Agents SDK）に加えて検討する価値があるもの。**どれもLiteLLM等経由でClaudeを使える**（プロバイダ非依存が標準化してきた）。

| フレームワーク | 特徴 | 向いているケース |
|---|---|---|
| **Pydantic AI**（Python） | 型安全・Pydanticバリデーション・DI。エージェントのロジックエラーを開発時に捕捉 | 型を重視するPythonチーム、構造化出力中心 |
| **Google ADK**（Python） | Gemini最適化だがモデル非依存。Workflow agentsでマルチエージェント、Vertex AI/Cloud Run/Cloud Traceと密結合 | GCP中心のチーム（[`15`](./15-bedrock-vertex-deployment.md)と相性） |
| **Microsoft Agent Framework**（.NET/Python） | **AutoGenとSemantic Kernelを統合**して1.0 GA。エンタープライズ.NET資産と接続 | Microsoftスタック中心の組織 |
| **smolagents**（Python/HF） | 極小・コード中心（エージェントがコードを書いて実行する方式） | 軽量・研究・素早い実験 |
| **Mastra**（TypeScript） | RAG・可観測性・MCP対応が最初から入ったopinionatedなTS製FW | TypeScriptでフルスタックに組みたい |
| **Vercel AI SDK**（TypeScript） | フロントエンド統合が強い。ストリーミングUI・MCP対応 | Next.js等のWebプロダクト組み込み |
| **LlamaIndex / Haystack**（Python） | RAG起点の統合FW（`04`にも記載） | 検索中心の構成 |

**選定の追加軸**（`04`の共通軸に加えて）: ①**メモリの内蔵度**（真に内蔵しているのは一部。多くはcheckpoint=状態永続であってセマンティックメモリではない→足りなければ§4-5のメモリレイヤーを重ねる）②**MCP対応**（対応FWなら既製MCPサーバー群をそのまま流用できる＝ツール資産の移植性）③**言語**（TSはMastra/Vercel、Pythonは選択肢が広い）。

---

## 4. 専門ツールカテゴリ（エージェントに「腕」を足す）

### 4-1. ブラウザ自動化
| ツール | 型 | 特徴 |
|---|---|---|
| **Playwright MCP** | MCPサーバー | 既存エージェントに「ブラウザの腕」をプラグイン。Claude Codeとの定番（テンプレPで実装） |
| **Stagehand**（TS） | SDK | Playwright上の抽象化。`act`/`extract`/`observe` の3プリミティブで自然言語→操作。構造化抽出が得意 |
| **browser-use**（Python） | エージェントループ | LLMにブラウザ全権を渡す方式（クリック・入力・スクロール・完了判断まで自律） |
| **Browserbase** | マネージドランタイム | クラウドでブラウザを大量に走らせる基盤（上記の実行先） |
| **computer use** | vision駆動 | 画面像で操作。DOMが取れないUI・デスクトップアプリに（[`11`](./11-claude-code-tool-use-and-sdk.md)） |

### 4-2. 音声エージェント
| ツール | 特徴 |
|---|---|
| **LiveKit Agents** | リアルタイム音声/映像/データのOSSフレームワーク。WebRTC基盤 |
| **Pipecat**（Python/OSS） | voice-first・低レイテンシ（sub-250ms級）・マルチモーダルのパイプライン構成 |
| マネージド各社（Vapi / Retell / ElevenLabs系 等） | 電話・音声ボットを最速で。ロックインとコストを確認 |

設計上の要点: 音声は **STT→LLM→TTS のレイテンシ予算**が支配的。ツール呼び出しを挟むなら「つなぎ発話」や並列化（[`14 §3`](./14-prompt-and-context-engineering.md)）が必須になる。

### 4-3. 検索・情報取得API（エージェントの「目」）
| ツール | 特徴 |
|---|---|
| **Tavily** | LLMエージェント向けに設計された検索API（出典つき） |
| **Exa** | セマンティック検索・類似ページ探索に強い |
| **Brave Search API** | インデックス独立系。プライバシー志向 |
| Anthropic `web_search` サーバーツール | API側で完結（[`11 §1`](./11-claude-code-tool-use-and-sdk.md)）。まずこれで足りるか |

### 4-4. ドキュメント解析（RAGの前処理）
**Unstructured / LlamaParse / Docling** 等——PDF・表・スライドを構造化してから[`05`テンプレJ](./05-build-and-output-templates.md)のRAGに流す。表や図の多い文書はここの品質が検索精度を律速する。Embedding/rerank は **Voyage AI**（Anthropic推奨のembedding）/ **Cohere Rerank** 等。

### 4-5. メモリレイヤー（会話をまたぐ記憶）
| ツール | 特徴 |
|---|---|
| **Mem0** | メモリ抽出・階層化のOSS+SaaS。ベンチマーク公開が活発 |
| **Zep** | 時間推論（temporal reasoning）に強みを主張。LongMemEval系で高スコア |
| **Letta**（旧MemGPT） | エージェント自身がメモリを管理する設計思想 |
Claude Code内なら**まずビルトイン**（auto memory / サブエージェント`memory`: [`16`](./16-claude-code-memory-and-permissions.md)・[`08`](./08-agent-primitives-and-composition.md)）で足りないか確認してから。

### 4-6. コード実行サンドボックス（生成コードを安全に走らせる）
| ツール | 特徴 |
|---|---|
| **E2B** | エージェント向けサンドボックスSaaS（Firecracker microVM基盤） |
| **Modal / Daytona 等** | サーバーレス実行・開発環境系 |
| Anthropic `code_execution` サーバーツール | API側のサンドボックスで完結（[`11 §1`](./11-claude-code-tool-use-and-sdk.md)） |
| Claude Code内蔵サンドボックス | Bash隔離（[`17 §1`](./17-claude-code-advanced-operations.md)） |
判断: Claude Code内なら内蔵sandbox、API直で「モデルが書いたコードを実行」なら code_execution → 制御・永続性が要るならE2B等へ。

### 4-7. ローカルLLM・自前サービング
**Ollama**（ローカル開発の定番）/ **vLLM**（本番サービングの定番）/ LM Studio。機密要件・大量処理コストでオープンウェイトを選ぶ場合（[`04`](./04-tool-selection-matrix.md) カテゴリ1）の実行基盤。ほとんどのFW（§3）からOpenAI互換APIとして繋がる。

---

## 5. プロトコル: MCP × A2A（エージェント間連携）

- **MCP** = エージェント⇔**ツール/データ**の標準（[`10`](./10-claude-code-mcp-servers.md)）。
- **A2A（Agent2Agent）** = エージェント⇔**エージェント**の標準。Googleが2025年に公開→Linux Foundationに寄贈され、150+組織・主要クラウド（Google/Microsoft/AWS）が採用、Python/JS/Java/Go/.NETのSDKがある。**組織や技術スタックをまたいで**エージェント同士が発見・通信するためのもの。
- 使い分け: 社内・単一システム内の協調なら サブエージェント/agent teams（[`08`](./08-agent-primitives-and-composition.md)/[`17 §4`](./17-claude-code-advanced-operations.md)）で足りる。**別組織・別ベンダーのエージェントと相互運用**する要件が出たときにA2Aを検討する。MCPとA2Aは補完関係（ツール接続はMCP、エージェント間はA2A）。

---

## 6. 採用の順序（このカタログの使い方）

1. **ビルトイン→公式→サードパーティ**の順で探索する（[`08 §0`](./08-agent-primitives-and-composition.md)）。Anthropicのサーバーツール（web_search/code_execution等）や既製MCPで足りるならそこで止まる。
2. サードパーティを入れるときは `04`の共通軸＋**信頼性の追加確認**: 提供元・メンテ頻度・データの行き先・ライセンス。
3. **1つずつ入れて評価する**（[`06`](./06-evaluation-and-iteration.md)）。腕を一気に増やすとツール選択の精度が落ちる（ツール数と誤選択はトレードオフ: [`14 §2`](./14-prompt-and-context-engineering.md)）。
4. モダリティを広げたら、評価もそのモダリティで作る（ブラウザ操作ならE2Eの成功率、音声ならレイテンシ＋会話完遂率）。

## チェックリスト
- [ ] 要件のモダリティ（テキスト/ブラウザ/音声/画面/データ）を特定した
- [ ] ビルトイン→公式→サードパーティの順で探索した
- [ ] ブラウザ系はDOM駆動/vision駆動/ハイブリッドを意識して選んだ
- [ ] サードパーティの信頼性（提供元・データの行き先・最小権限）を確認した
- [ ] 採用は1つずつ、モダリティに合わせた評価とセットで
