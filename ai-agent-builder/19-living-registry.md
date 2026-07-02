# 生きた台帳（Living Registry）— このエージェントが「食った」部品の全記録

[`18`](./18-third-party-ecosystem.md) が「世の中の地図（カテゴリと選び方）」なのに対し、このファイルは**このエージェントが実際に調査・検証・導入した部品の台帳**。`/absorb` スキルで1件ずつ増えていく。

> **設計思想**: 「この世の全ツールを暗記しているエージェント」は作れない（エコシステムの変化速度が暗記を必ず陳腐化させる）。代わりにこのエージェントは3層で「全てを把握」する:
> 1. **固定の選定軸**（[`04`](./04-tool-selection-matrix.md)/[`08`](./08-agent-primitives-and-composition.md)）— ツールが入れ替わっても変わらない判断基準
> 2. **生きた台帳**（このファイル）— 検証済み・即使用可の装備。`/absorb` で成長する
> 3. **オンデマンド探索**（`agent-builder-researcher`＋WebSearch）— 台帳に無いものはその場で5分で調べて食う
>
> 「全部知ってる」ではなく「**何でも即座に調べて、検証して、装備に変えられる**」が正しい形。

## エントリの状態定義

| 状態 | 意味 |
|---|---|
| ✅導入済 | この環境で動作検証済み・即使用可 |
| 🔑待機 | 導入手順は確立済み。APIキー等の人間側アクションを差せば有効化（`templates/mcp-optional.json`） |
| 📖調査済 | 仕様・導入方法を調査済みだが未導入（必要になったら導入タスク化） |
| ⚠️制約あり | 動くが環境制約に注意（備考参照） |

---

## 1. MCPサーバー

| 名前 | 状態 | 何ができるか | 導入方法 | キー | 検証日 | 出典 |
|---|---|---|---|---|---|---|
| Playwright MCP | ✅導入済 | 実ブラウザ操作23ツール（navigate/click/snapshot/screenshot/evaluate等）。アンチボット回避力が最も高い取得手段 | `.mcp.json`（プリインストールChromium使用） | 不要 | 2026-07-02 | github.com/microsoft/playwright-mcp |
| Context7 | 🔑待機 | ライブラリ最新公式ドキュメントの文脈注入 | `templates/mcp-optional.json` → `.mcp.json` | 不要(制限緩和に任意キー) | 2026-07-02 | github.com/upstash/context7 |
| Tavily | 🔑待機 | エージェント向け検索API（出典つき・セッション上限なし） | 同上 | TAVILY_API_KEY | 2026-07-02 | tavily.com |
| Exa | 🔑待機 | セマンティック検索・類似ページ探索 | 同上 | EXA_API_KEY | 2026-07-02 | exa.ai |
| Brave Search | 🔑待機 | 独立インデックスのWeb検索 | 同上 | BRAVE_API_KEY | 2026-07-02 | brave.com/search/api |
| GitHub MCP | ⚠️制約あり | PR/issue/CI/リポジトリ操作 約60ツール | リモート実行環境が自動接続（ローカルは要設定） | 環境付与 | 2026-07-02 | github.com/github/github-mcp-server |
| Serena | ✅導入済 | LSPベースの意味論的コード操作（find_symbol/replace_symbol_body等、40+言語）。エージェントに「IDEの腕」。ローカル完結 | `.mcp.json`（uvx＋PyPI `serena-agent`。v1.5.3で起動確認。**次セッションで21ツールの実ツール化を確認済み**） | 不要 | 2026-07-02 | github.com/oraios/serena |
| Sequential Thinking | ✅導入済 | 構造化推論ツール（複雑な設計の計画を明示的ステップに分解）。公式リファレンス実装・ローカル完結 | `.mcp.json`（npx。stdio起動確認済み。**次セッションで実ツール化を確認済み**） | 不要 | 2026-07-02 | github.com/modelcontextprotocol/servers |
| Memory（公式） | ✅導入済 | ナレッジグラフ型の永続メモリ。セッションをまたいで学習を蓄積。保存先を `.claude/agent-memory.json` に固定＝**gitで永続化され母艦が育つ** | `.mcp.json`（npx。stdio起動確認済み。保存先が生成されない場合は `MEMORY_FILE_PATH` を絶対パスに） | 不要 | 2026-07-02 | github.com/modelcontextprotocol/servers |
| MarkItDown（Microsoft公式） | ✅導入済 | PDF/Office/画像→Markdown変換（RAG前処理・ドキュメント処理の腕。18 §4-4の実装装備） | `.mcp.json`（uvx。--help検証済み。音声変換のみffmpeg未PATHで不可） | 不要 | 2026-07-02 | github.com/microsoft/markitdown |
| DuckDuckGo Search | ⚠️制約あり | キー不要のWeb検索。ローカルCLIならWebSearchのセッション上限の代替 | `templates/mcp-optional.json`（uvx。起動確認済み。**この環境は外部遮断のため検索は不可＝ローカル用**） | 不要 | 2026-07-02 | github.com/nickclyde/duckduckgo-mcp-server |

## 2. REST API（MCP不要・Bash/requestsから直接叩く）

| 名前 | 状態 | 何ができるか | キー | 検証日 |
|---|---|---|---|---|
| 楽天市場 商品検索API | 🔑待機 | 価格・ポイント倍率が構造化JSONで返る（無料）。ECスクレイピングの正解 | RAKUTEN_APP_ID | 2026-07-02（仕様調査） |
| Yahoo!ショッピング 商品検索API | 🔑待機 | 同上（無料） | YAHOO_APP_ID | 2026-07-02（仕様調査） |

## 3. ランタイム装備（この実行環境にプリインストール）

| 名前 | 状態 | 備考 | 検証日 |
|---|---|---|---|
| Chromium 実ブラウザ | ✅導入済 | `/opt/pw-browsers/chromium`（Playwright 1.56対応ビルド） | 2026-07-02（起動確認済み） |
| playwright 1.56.1（npmグローバル） | ✅導入済 | Bashから直接スクリプト実行可（CJS＋`executablePath`指定） | 2026-07-02 |
| Node 22 / Python 3 / uv・uvx / requests | ✅導入済 | uvxでPython系MCPも起動可 | 2026-07-02 |
| MCP Inspector（公式） | 📖調査済 | 自作MCPサーバーのデバッグ標準ツール（Web UI）。`npx @modelcontextprotocol/inspector` で随時起動（常駐不要） | 2026-07-02（仕様調査のみ） |
| ネットワーク | ⚠️制約あり | **プロキシポリシーが許可リスト外ドメインをCONNECT 403で遮断**。アンチボット403と誤診しないこと。curl 1回で切り分ける | 2026-07-02（実測） |

## 4. スキル

| 名前 | 状態 | 何ができるか | 所在 |
|---|---|---|---|
| /agent-builder | ✅導入済 | 本体。6フェーズでエージェントを設計・実装（起動時に環境自動棚卸し） | `.claude/skills/agent-builder/` |
| /absorb | ✅導入済 | 新部品の調査→台帳追記→可能なら即導入（このエージェントの「食う」機能） | `.claude/skills/absorb/` |
| /price-hunter | ✅導入済 | 実演で作った最安値比較（環境スパイク・逐次検証の見本） | `.claude/skills/price-hunter/` |
| bundledスキル群 | ✅導入済 | `/code-review` `/verify` `/simplify` `/run` `/dataviz` `/claude-api` `/loop` `/security-review` `/review` `/init` `/update-config` `/fewer-permission-prompts` 等。ハーネス同梱・導入不要 | ハーネス |

## 5. サブエージェント

| 名前 | 状態 | 何ができるか | 所在 |
|---|---|---|---|
| agent-builder-researcher | ✅導入済 | 大量調査の隔離（Read/Grep/Glob/WebSearch/WebFetch、maxTurns 25）。**価格取得等の実行代行は不可**（調査専門） | `.claude/agents/` |
| Explore / Plan / general-purpose / claude-code-guide | ✅導入済 | ビルトイン（高速探索／設計／万能／Claude公式仕様の質問） | ハーネス |

## 6. フレームワーク・SDK（調査済みカタログは [`04`](./04-tool-selection-matrix.md)/[`18`](./18-third-party-ecosystem.md)）

未導入。必要案件が来たら `/absorb <名前>` で調査→この台帳に昇格させる。

## 7. 発見チャネル（部品を探しに行く「棚」）

| 名前 | 状態 | 何があるか | 使い方 | 検証日 |
|---|---|---|---|---|
| 公式プラグインマーケットプレイス（anthropics/claude-plugins-official） | ✅精査済 | Anthropic監査済みプラグイン**255件**（development 109 / productivity 45 / database 34 / monitoring 17 / security 13 ほか。※「119件」という記事情報は旧数—一次ソースのmarketplace.jsonで確認） | `/plugin` のDiscoverタブで閲覧、`claude plugin install <名前>@claude-plugins-official -s project` で導入。カタログ: claude.com/plugins | 2026-07-02（全255件精査） |
| awesome-claude-code（hesreallyhim, 36.8k★） | ✅登録済 | コミュニティ製スラッシュコマンド/スキル/フック/ワークフローの最大手カタログ | フェーズ3.5の探索先。この環境からは直接読めないため、候補名を特定→WebSearchで個別裏取り→`/absorb <名前>` | 2026-07-02 |
| VoltAgent/awesome-claude-code-subagents | ✅登録済 | 既製サブエージェント150+のカタログ（カテゴリ別） | 同上。サブエージェントを新規に書く前にここを確認 | 2026-07-02 |

## 8. プラグイン選定（公式マーケットプレイス255件から精査済み）

**この環境での導入は人間側アクション待ち**: セッションのGitHubアクセスが shinpeihimazin-hub/app に限定されており、マーケットプレイスのclone（anthropics/claude-plugins-official）が403になる（エラーは「Use add_repo to request access」。tarball/API/HTML/jsDelivrも検証済みで全て遮断、raw単体ファイルのみ可＝ファイル列挙不能で搬入不可）。**セッションのリポジトリアクセスに `anthropics/claude-plugins-official` を追加するか、ローカルCLIで下記2コマンドを実行すれば即導入できる**:

```bash
claude plugin marketplace add anthropics/claude-plugins-official   # ローカルCLIでは不要（自動登録済み）
claude plugin install <名前>@claude-plugins-official -s project    # -s project でリポジトリに記録され全セッションに効く
```

### 中核5選（🔑導入待ち・全てAnthropic公式作）— エージェント作成の使命に直結

| 名前 | 何ができるか | キット対応 |
|---|---|---|
| **skill-creator** | スキルの新規作成・改善・eval計測 | 09の実装版 |
| **mcp-server-dev** | MCPサーバーの設計・構築ガイド一式 | 10の実装版 |
| **plugin-dev** | プラグイン開発（hooks/agents/commands/MCP統合、7スキル） | 12の実装版 |
| **agent-sdk-dev** | Claude Agent SDK開発キット | 11の実装版 |
| **security-guidance** | 生成コードのセキュリティレビュー（編集時パターン警告＋LLM差分レビュー） | 08 §6.5の自動化 |

### 次点（用途が発生したら個別に。全て精査済み）

| 名前 | 何ができるか | 入れ時 |
|---|---|---|
| hookify（Anthropic） | 会話パターン分析からカスタムフック生成 | フック需要が出たら |
| claude-code-setup（Anthropic） | コードベース分析→hooks/skills/MCPの提案 | 新規プロジェクト導入時 |
| claude-md-management（Anthropic） | CLAUDE.mdの品質監査・セッション学習の取り込み | メモリ運用を始めたら |
| feature-dev / pr-review-toolkit（Anthropic） | 機能開発ワークフロー／PR多角レビュー | 実装案件が回り始めたら |
| superpowers（obra・コミュニティ有名作） | ブレスト＋サブエージェント駆動開発＋内蔵レビュー | メタ開発を強化したいとき |
| chrome-devtools-mcp（Google公式） | 実Chromeの制御・パフォーマンストレース | Playwright MCPで不足したら |
| ○○-lsp 系（typescript/pyright/gopls/rust等 十数種） | 言語別LSP | **Serenaと重複のため原則不要**。Serena不調の言語のみ |
| tavily / exa / context7 / firecrawl / brightdata | 検索・スクレイパのプラグイン版 | §1のMCP待機行と同じキーで、MCP単体よりスキル込みのこちらを優先してもよい |

---

## 台帳の育て方

- 新しい部品を見つけたら・使いたくなったら: **`/absorb <ツール名やURL>`**
- 定期巡回（新着MCP・新スキルの発見）: **`/absorb sweep`**
- エントリの鮮度: 検証日から6ヶ月超のエントリは使用前に再検証（`/absorb <名前>` で上書き更新）
