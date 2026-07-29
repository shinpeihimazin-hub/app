# Claude Code リファレンス⑤ メモリ（CLAUDE.md）と権限（permissions/settings）

エージェントの挙動を規定する2つの基盤。**CLAUDE.md＝毎セッション読み込まれる恒常指示（文脈であって強制ではない）**、**permissions＝クライアントが強制する境界（モデルの判断に関係なく効く）**。この区別が設計の出発点。公式仕様（`code.claude.com/docs/en/memory`, `.../permissions`）ベース。

> 使い分けの鉄則: 「Claudeにこう振る舞ってほしい」→ CLAUDE.md。「Claudeが何を決めようと絶対に通さない/必ず通す」→ permissions（またはフック[`12`](./12-claude-code-hooks-and-plugins.md)）。CLAUDE.mdは強制レイヤーではない。

---

## パート1: CLAUDE.md / メモリ

### 1-1. 2つのメモリ系（両方とも毎セッション先頭でロード）

| | CLAUDE.md | auto memory |
|---|---|---|
| 書くのは | あなた | Claude自身 |
| 中身 | 指示・ルール | 学び・パターン（ビルドコマンド、デバッグ知見、好み） |
| スコープ | project / user / 組織 | リポジトリ単位（worktree間で共有、マシンローカル） |
| ロード | 全文 | `MEMORY.md` の先頭200行 or 25KB |
| 置き場 | 下表 | `~/.claude/projects/<project>/memory/` |

auto memory は既定オン（`autoMemoryEnabled: false` か `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` で無効化）。`/memory` でロード中の全ファイル一覧・編集・auto memoryのオン/オフができる。「pnpmを使え、と覚えて」のような依頼は auto memory に入る。CLAUDE.mdに入れたければ「CLAUDE.mdに追記して」と言うか自分で編集する。

### 1-2. CLAUDE.md の置き場所と優先（広い→狭いの順にロード）

| スコープ | 場所 | 用途 |
|---|---|---|
| Managed（組織） | macOS `/Library/Application Support/ClaudeCode/CLAUDE.md`／Linux `/etc/claude-code/CLAUDE.md`／Win `C:\Program Files\ClaudeCode\CLAUDE.md` | 全社標準。個人設定で除外不可 |
| User | `~/.claude/CLAUDE.md` | 全プロジェクト共通の個人好み |
| Project | `./CLAUDE.md` または `./.claude/CLAUDE.md` | チーム共有（VCS管理）。`/init` で自動生成できる |
| Local | `./CLAUDE.local.md` | 個人×プロジェクト（`.gitignore` に入れる） |

**ロードの仕組み**: 作業ディレクトリから**上へ**辿って各階層の CLAUDE.md / CLAUDE.local.md を全部連結（上書きではない）。ルート側が先、作業ディレクトリに近いものが後（＝最後に読まれる）。**下位ディレクトリ**のCLAUDE.mdは起動時ではなく、そのディレクトリのファイルを読んだ時にオンデマンドでロード。モノレポで他チームのCLAUDE.mdが邪魔なら `claudeMdExcludes`（glob）で除外。HTMLコメント `<!-- -->` は注入前に除去される（人間向けメモに使える）。

### 1-3. 書き方（公式ベストプラクティス）

**いつ書き足すか**: Claudeが同じ間違いを2回した／レビューで「この codebase なら知ってるべき」ことを拾った／前セッションと同じ訂正を打っている——その内容を書く。

- **サイズ: 1ファイル200行以内目標**。長いほど文脈を食い、遵守率が下がる。
- **具体的に**: 「コードを綺麗に」ではなく「インデントは2スペース」「コミット前に `npm test`」「APIハンドラは `src/api/handlers/`」。検証可能な粒度で。
- **構造化**: 見出しと箇条書き。密な段落より節分け。
- **矛盾を残さない**: 2つのルールが矛盾するとどちらかを恣意的に選ぶ。定期的に棚卸す。
- **手順に育った節はスキルへ**（[`09`](./09-claude-code-skill-authoring.md)）、特定パス限定なら rules へ（下記）。**事実と「常にXせよ」だけを残す。**

### 1-4. `@import` と `.claude/rules/`

**import**: CLAUDE.md 内の `@path/to/file` は起動時に展開ロードされる（相対パスはそのファイル基準、再帰4段まで。バッククォート内は無視）。`AGENTS.md` を使う他ツールと共存するなら `@AGENTS.md` をCLAUDE.mdの先頭に書く（またはsymlink）。**importは整理には効くが文脈消費は減らない**（起動時に全部入る）。

**rules（トピック別・パス限定の指示）**: `.claude/rules/*.md`（再帰探索、symlink可）。`paths` フロントマターを付けると**一致するファイルを扱う時だけロード**され、文脈を節約できる:
```markdown
---
paths:
  - "src/api/**/*.ts"
---
# API開発ルール
- 全エンドポイントに入力バリデーション
- 標準エラーフォーマットを使う
```
`paths` 無しの rules は起動時ロード（`.claude/CLAUDE.md` と同格）。`~/.claude/rules/` はユーザー横断（projectより先にロード＝projectが優先）。

### 1-5. トラブルシュート

- **従わない**: `/memory` でロードされているか確認 → 指示をより具体的に → 矛盾を除去。**必ず実行させたい処理はCLAUDE.mdでなくフックに**（[`12`](./12-claude-code-hooks-and-plugins.md)）。
- **`/compact` 後に消えた**: プロジェクトルートのCLAUDE.mdは圧縮後に再注入されるが、**ネストしたCLAUDE.mdは自動再注入されない**（該当ディレクトリのファイルを読むと再ロード）。会話でしか伝えていない指示はCLAUDE.mdに書いて永続化する。
- **大きすぎる**: 200行超なら paths付きrulesへ分割。

---

## パート2: permissions / settings

### 2-1. ルールの3リストと評価順

`/permissions` で管理。settings の `permissions` に書く。

- **deny → ask → allow の順に評価し、最初に一致した方が勝つ**（具体性は順序を変えない）。
- つまり**denyルールは例外を持てない**: `Bash(aws *)` をdenyすると、`Bash(aws s3 ls)` をallowしていてもブロックされる。
- deny の形で挙動が違う: **裸のツール名**（`Bash`）はツールを文脈から**消す**（Claudeに見えない）。**スコープ付き**（`Bash(rm *)`）はツールは見えたまま、一致する呼び出しだけブロック。
- **permissionsはクライアントが強制する**。プロンプトやCLAUDE.mdはClaudeが「何をしようとするか」を変えるだけで、「何が通るか」は変えない。

```json
{
  "permissions": {
    "allow": ["Bash(npm run *)", "Bash(git commit *)", "Read(src/**)"],
    "ask":   ["Bash(git push *)"],
    "deny":  ["Read(.env)", "Read(//**/.ssh/**)", "WebFetch"]
  }
}
```

### 2-2. ルール構文の要点

| 形 | 例 | 意味 |
|---|---|---|
| ツール名のみ | `Bash` / `WebFetch` | そのツールの全使用（`Bash(*)` と等価） |
| Bash glob | `Bash(npm run *)` `Bash(git * main)` | `*` は空白を含む任意列。**` *` の空白が語境界**（`Bash(ls *)` は `ls -la` に一致、`lsof` に不一致。`Bash(ls*)` は両方一致） |
| Read/Edit パス | `Read(.env)` `Edit(/src/**)` `Read(~/.zshrc)` `Read(//etc/**)` | gitignore流。**`/`始まり=プロジェクトルート相対、`//`=絶対パス、`~/`=ホーム**。裸のファイル名は任意の深さに一致 |
| WebFetch | `WebFetch(domain:example.com)` `domain:*.example.com` | ホスト名一致（`*.` は任意深さのサブドメイン、apex自体は含まない） |
| MCP | `mcp__server` / `mcp__server__tool` | サーバー全体／特定ツール |
| サブエージェント | `Agent(Explore)` `Agent(my-agent)` | 特定サブエージェントの許可/禁止（[`08`](./08-agent-primitives-and-composition.md)） |
| パラメータ一致（deny/askのみ） | `Agent(model:opus)` `Bash(run_in_background:true)` | トップレベル入力パラメータで一致 |

**Bashの落とし穴（重要）**:
- **複合コマンドは分解して照合**される（`&&` `||` `;` `\|` 等）。`Bash(safe *)` は `safe && evil` を許可しない。各サブコマンドが独立に一致する必要がある。
- `timeout`/`nice`/`nohup` 等のラッパーは剥がして照合。ただし `npx`/`docker exec`/`devbox run` 等の**環境ランナーは剥がされない**——`Bash(devbox run *)` は `devbox run rm -rf .` も通す。ランナー越しは「ランナー＋内側コマンド」まで書いた具体ルールにする。
- **引数を縛るパターンは脆い**: `Bash(curl http://github.com/ *)` はオプション先行・https・リダイレクト・変数展開で漏れる。URL制御は「curl/wgetをdenyし、`WebFetch(domain:...)` を使わせる」か PreToolUse フックで。
- `ls`/`cat`/`grep`/読み取り系gitなどの**組み込み読み取りコマンドは常に無承認**（設定不可。止めたければ ask/deny を書く）。

**Read/Edit denyの限界**: 組み込みファイルツールと認識可能なBashコマンド（cat等）には効くが、**ファイルを自分で開くサブプロセス**（Pythonスクリプト等）には効かない。OSレベルで塞ぐには[サンドボックス](./17-claude-code-advanced-operations.md)を併用（permissions=ツール層、sandbox=OS層の多層防御）。

### 2-3. settings ファイルの階層と優先

1. **Managed settings**（組織ポリシー。何にも上書きされない）
2. CLIフラグ（セッション一時）
3. `.claude/settings.local.json`（個人×プロジェクト、gitignore）
4. `.claude/settings.json`（チーム共有）
5. `~/.claude/settings.json`（ユーザー）

**どこかの層のdenyは、他のどの層のallowよりも強い**（deny先行評価のため。userのdenyはprojectのallowを塞ぐ）。

`defaultMode` でセッションの権限モード（`default`/`acceptEdits`/`plan`/`auto`/`dontAsk`/`bypassPermissions`）を設定。`bypassPermissions` の注意は [`08 §6.5`](./08-agent-primitives-and-composition.md)。組織で封じるには `permissions.disableBypassPermissionsMode: "disable"`。

**作業ディレクトリの拡張**: `--add-dir` / `/add-dir` / `permissions.additionalDirectories`。追加ディレクトリは**ファイルアクセスを増やすだけ**で設定ルートにはならない（スキル・サブエージェントなど一部例外は `--add-dir` のみロード。[`09`](./09-claude-code-skill-authoring.md)参照）。

### 2-4. フックとの関係

PreToolUse フックは権限プロンプトの**前**に走り、deny/ask/allow を返せる（[`12`](./12-claude-code-hooks-and-plugins.md)）。ただし**ルールのdeny/askはフックの判断より優先**（フックがallowを返してもdenyルールは塞ぐ）。逆に exit 2 のブロックはallowルールより先に効く。「Bashは全部通すが特定コマンドだけ塞ぐ」は「allowに `Bash`＋PreToolUseフックで拒否」の組み合わせで作る。

### 2-5. エージェント設計での使い方（このキットの文脈）

- **成果物のエージェントに権限セットを同梱する**: プロジェクトの `.claude/settings.json` に allow/ask/deny を書いて配布すれば、チーム全員が同じ安全境界で動く。フェーズ4の成果物に含めること。
- **サブエージェントの最小権限**（[`08`](./08-agent-primitives-and-composition.md)）× **プロジェクトのdenyルール** × **フック** × **サンドボックス**の4層で守る。
- 例（フェーズ4に添える標準セット）:
```json
{
  "permissions": {
    "allow": ["Bash(npm test *)", "Bash(npm run lint *)", "Edit(/src/**)", "Edit(/tests/**)"],
    "ask":   ["Bash(git push *)", "Bash(npm publish *)"],
    "deny":  ["Read(.env)", "Read(//**/.ssh/**)", "Read(**/secrets/**)", "Bash(rm -rf *)"]
  }
}
```

---

## チェックリスト
- [ ] 「振る舞いの指示」はCLAUDE.md、「絶対の境界」はpermissions/フックに置き分けた
- [ ] CLAUDE.mdは200行以内・具体的・矛盾なし。手順はスキル、パス限定はrulesへ
- [ ] deny→ask→allowの評価順を踏まえ、denyに例外を期待していない
- [ ] Bashルールの落とし穴（複合コマンド・環境ランナー・引数縛りの脆さ）を回避した
- [ ] 機密パス（.env/.ssh/secrets）のReadをdenyし、必要ならサンドボックスを併用
- [ ] 成果物のエージェントに `.claude/settings.json` の権限セットを同梱した
