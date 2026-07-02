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

---

## 台帳の育て方

- 新しい部品を見つけたら・使いたくなったら: **`/absorb <ツール名やURL>`**
- 定期巡回（新着MCP・新スキルの発見）: **`/absorb sweep`**
- エントリの鮮度: 検証日から6ヶ月超のエントリは使用前に再検証（`/absorb <名前>` で上書き更新）
