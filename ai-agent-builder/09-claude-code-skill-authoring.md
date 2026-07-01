# Claude Code リファレンス① スキルを実装する（完全版）

「あらゆるスキルを実装できる」ための実装リファレンス。公式仕様（`code.claude.com/docs/en/skills`）ベース。概念・使い分けは [`08`](./08-agent-primitives-and-composition.md) を先に読む。ここは**作り方の全手順**。

> 仕様の細部はバージョンで変わる。実装時に公式ドキュメント／`/doctor`／`--debug` で確認する。

---

## 1. 最小のスキル（3ステップ）

```bash
mkdir -p ~/.claude/skills/summarize-changes        # 個人用（全プロジェクトで有効）
# or: mkdir -p .claude/skills/summarize-changes     # プロジェクト用（リポジトリで共有）
```

`~/.claude/skills/summarize-changes/SKILL.md`:
```markdown
---
description: 未コミットの変更を要約し、リスクを指摘する。ユーザーが「何を変えた?」「コミットメッセージ」「差分レビュー」を求めたときに使う。
---

## 現在の変更
!`git diff HEAD`

## 手順
上の差分を2〜3個の箇条書きで要約し、リスク（エラーハンドリング欠落・ハードコード・要更新テスト等）を列挙する。差分が空なら「未コミットの変更なし」と言う。
```

- **ディレクトリ名が `/コマンド名`** になる（`summarize-changes/` → `/summarize-changes`）。
- 自動起動（Claudeが description で判断）と手動起動（`/summarize-changes`）の両方が可能。

---

## 2. 置き場所（スコープ）と優先順位

| 場所 | パス | 適用範囲 |
|---|---|---|
| Enterprise | managed settings | 組織全員 |
| Personal | `~/.claude/skills/<name>/SKILL.md` | 自分の全プロジェクト |
| Project | `.claude/skills/<name>/SKILL.md` | そのプロジェクトのみ（VCSで共有） |
| Plugin | `<plugin>/skills/<name>/SKILL.md` | プラグイン有効な所（`plugin:skill` で名前空間化） |

- 同名衝突は enterprise > personal > project。スキルは同名の**ビルトインを上書き**する（例: プロジェクトの `code-review` が bundled `/code-review` を置換）。
- 親ディレクトリ・ネストした `.claude/skills/` も探索される（モノレポ対応）。ネスト同名は `apps/web:deploy` のようにディレクトリ修飾名になる。
- `.claude/commands/<name>.md` も等価（`/name` を作る）。新規はスキル推奨（対応ファイル等の機能があるため）。

---

## 3. フロントマター全フィールド（`description` のみ推奨）

| フィールド | 役割 |
|---|---|
| `name` | 表示名（省略時ディレクトリ名）。呼び出し名は基本ディレクトリ名で決まる（plugin-root除く） |
| `description` | **何を/いつ**。Claudeの自動起動判断に使う。要点を先頭に（一覧は combined で1,536文字上限） |
| `when_to_use` | 発動トリガーの補足（description に追記、上限に算入） |
| `argument-hint` | オートコンプリート時の引数ヒント（例 `[issue-number]`） |
| `arguments` | 名前付き位置引数（`$name` 置換用。空白区切り or YAMLリスト） |
| `disable-model-invocation: true` | Claudeの自動起動を止め、`/name` 手動限定に。副作用のある操作（deploy/commit/送信）に必須級 |
| `user-invocable: false` | `/`メニューから隠す。Claude専用の背景知識に |
| `allowed-tools` | 稼働中に無承認で使えるツール（例 `Bash(git add *)`）。可用性は制限せず**承認を省く**だけ |
| `disallowed-tools` | 稼働中に外すツール（自律ループで `AskUserQuestion` を封じる等）。次の発話で解除 |
| `model` | 稼働中のモデル上書き（`/model` と同値 or `inherit`）。ターン内のみ有効 |
| `effort` | 稼働中の推論強度（`low`〜`max`） |
| `context: fork` | **サブエージェントで隔離実行**（本体がタスクプロンプトになる） |
| `agent` | `context: fork` 時のサブエージェント種別（`Explore`/`Plan`/`general-purpose`/カスタム） |
| `paths` | globに一致するファイル作業時だけ自動発動（例 `src/**/*.ts`） |
| `hooks` | このスキルのライフサイクルに紐づくフック |
| `shell` | インライン `` !`` `` 実行のシェル（`bash`/`powershell`） |

### 誰が起動できるか（3状態）
| フロントマター | ユーザー起動 | Claude起動 | 文脈ロード |
|---|---|---|---|
| （既定） | 可 | 可 | descriptionは常時、本体は起動時 |
| `disable-model-invocation: true` | 可 | **不可** | descriptionも非ロード、本体は手動起動時 |
| `user-invocable: false` | **不可** | 可 | descriptionは常時、本体は起動時 |

---

## 4. 動的コンテキスト注入（生データを根拠にする）

`` !`command` `` はスキルが渡る**前に**シェル実行され、出力がその場に差し込まれる（Claudeが実行するのではなく前処理）。

```markdown
## PRコンテキスト
- diff: !`gh pr diff`
- 変更ファイル: !`gh pr diff --name-only`
```
- `!` は**行頭 or 空白直後**でのみ認識（`KEY=!`cmd`` は無効）。
- 複数行は ` ```! ` フェンスを使う。
- 一度だけ置換され再スキャンされない。10,000字上限等の制約あり。
- 無効化ポリシー: `disableSkillShellExecution`。

---

## 5. 引数を受ける

| 変数 | 意味 |
|---|---|
| `$ARGUMENTS` | 全引数。プレースホルダが無ければ末尾に `ARGUMENTS: <値>` 追記 |
| `$ARGUMENTS[N]` / `$N` | N番目（0始まり）。`/skill "hello world" second` → `$0=hello world`, `$1=second` |
| `$name` | `arguments: [issue, branch]` 宣言時の名前付き引数 |
| `${CLAUDE_SESSION_ID}` / `${CLAUDE_SKILL_DIR}` / `${CLAUDE_PROJECT_DIR}` | セッションID / スキルのディレクトリ / プロジェクトルート |

```markdown
---
name: fix-issue
description: GitHub issueを修正する
disable-model-invocation: true
---
GitHub issue $ARGUMENTS を規約に沿って修正する。
1. issue説明を読む 2. 要件把握 3. 実装 4. テスト 5. コミット
```

---

## 6. プログレッシブ・ディスクロージャ（コストを普段ゼロに）

`SKILL.md` は目次に徹し、詳細は別ファイルに置き、必要時だけ読ませる。

```text
my-skill/
├── SKILL.md        # 必須。概要とナビゲーション（500行以内目安）
├── reference.md    # 詳細API（必要時ロード）
├── examples.md     # 出力例
└── scripts/
    └── helper.py   # 実行される（文脈にはロードされない）
```

`SKILL.md` から必ず参照づける（Claudeに「何が・いつ要るか」を知らせる）:
```markdown
## 追加リソース
- 完全なAPI仕様は [reference.md](reference.md)
- 使用例は [examples.md](examples.md)
```

**本体は一度注入されると以後ずっと文脈に残る**（毎ターンのコスト）。恒常指示として簡潔に書く。大きい参照資料ほど別ファイルへ。

---

## 7. スクリプト同梱（プロンプト単体を超える）

任意言語のスクリプトを同梱・実行できる（可視化HTML生成、データ処理等）。パスは `${CLAUDE_SKILL_DIR}` で解決（個人/プロジェクト/プラグインのどこに置かれても動く）。

````markdown
---
name: codebase-visualizer
description: コードベースの折りたたみツリーHTMLを生成する。新規リポジトリ把握や大きいファイル特定に使う。
allowed-tools: Bash(python3 *)
---
プロジェクトルートから可視化スクリプトを実行:
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/visualize.py .
```
`codebase-map.html` を生成しブラウザで開く。
````

---

## 8. ツール権限（無承認化と制限）

- `allowed-tools`: 稼働中、列挙ツールを無承認化（可用性は制限しない）。プロジェクトの `.claude/skills/` では**ワークスペース信頼ダイアログ承認後**に有効。他人のスキルは中身を読んでから信頼する。
```yaml
---
name: commit
description: 現在の変更をステージしコミットする
disable-model-invocation: true
allowed-tools: Bash(git add *) Bash(git commit *) Bash(git status *)
---
```
- `disallowed-tools`: 稼働中にツールを外す（次の発話で解除）。全体で恒久的に塞ぐなら permission の deny。

---

## 9. スキルをサブエージェントで隔離実行（`context: fork`）

明確なタスクを持つスキルを、独立コンテキストで実行して要約だけ返す。

```yaml
---
name: deep-research
description: トピックを徹底的に調査する
context: fork
agent: Explore
---
$ARGUMENTS を徹底調査:
1. Glob/Grepで関連ファイル発見 2. 読んで分析 3. ファイル参照つきで要約
```
- `agent` 未指定なら `general-purpose`。`Explore`/`Plan` は CLAUDE.md・git status を省いて軽量。
- 注意: ガイドライン系（タスクの無い知識注入）を `context: fork` にすると、実行可能な指示が無く空振りする。**タスクを持つスキルにのみ使う**。
- 逆方向（サブエージェントに `skills` で知識を前ロード）は [`08 §3`](./08-agent-primitives-and-composition.md)。

---

## 10. 評価と反復（トリガー精度＋出力品質）

「起動した」＝「意図通り動いた」ではない。2つを別々に測る。

- **ベースライン比較**: 現実的なプロンプト数件を、スキル有効時と[無効時](#)で新規セッション（文脈汚染を避ける）で走らせ、結果を比較する。
- **skill-creator プラグイン**で自動化: `evals/evals.json` にテストケース、サブエージェントで隔離実行、`grading.json` に合否、`benchmark.json` に有/無のpass率・時間・トークン、A/Bで改善確認、description調整（誤発動の検出）。
  ```text
  /plugin install skill-creator@claude-plugins-official
  ```

---

## 11. トラブルシュート

- **起動しない**: description にユーザーが自然に言う語を入れる／`What skills are available?` で確認／`/name` で直接起動／`--debug` でパースエラー確認（フロントマターYAML不正だと description 無しでロードされる）。
- **起動しすぎる**: description をより具体化／`disable-model-invocation: true`。
- **descriptionが切られる**: スキル多数だと予算内に短縮される。`/doctor` で確認。`skillListingBudgetFraction` を上げる／低優先を `skillOverrides` で `name-only` に／要点を先頭に（1,536字上限）。
- **効かなくなった気がする**: 本体は文脈に残っている。description・指示を強化するか、確定的挙動は[フック](./12-claude-code-hooks-and-plugins.md)で。圧縮後は再invoke。

---

## チェックリスト
- [ ] `description` に発動語が入っていて、要点が先頭にある
- [ ] 副作用のある操作は `disable-model-invocation: true` か Human-in-the-Loop
- [ ] 本体は簡潔（500行以内）、詳細は別ファイルに逃がした
- [ ] スクリプトパスは `${CLAUDE_SKILL_DIR}` で書いた
- [ ] `allowed-tools` は最小限
- [ ] ゴールデンテストで有/無を比較した
