# Claude Code リファレンス⑥ 運用系の周辺機能（sandbox / checkpoint / スケジュール / agent teams）

エージェントを「安全に・止まらず・並列に」動かすための運用機能群。公式仕様（`code.claude.com/docs/en/sandboxing`, `.../checkpointing`, `.../scheduled-tasks`, `.../agent-teams`）ベース。

> どれも更新が速い領域（agent teams は実験的機能）。実装時に公式で現行仕様を確認する。

---

## パート1: サンドボックス（BashのOSレベル隔離）

permissionsが「ツール層」の制御なら、サンドボックスは**OS層の強制**。Bashコマンドとその子プロセス全部に、ファイルシステムとネットワークの境界をOSが課す（macOS=Seatbelt、Linux/WSL2=bubblewrap+socat。ネイティブWindows非対応）。**許可済みコマンドが名前以上のことをしても境界は保たれる**——これがpermissionルールとの本質的な違い（[`16 §2`](./16-claude-code-memory-and-permissions.md) と多層防御）。

### 使い方
- `/sandbox` でパネルを開き、モードを選ぶ（設定は `.claude/settings.local.json` に書かれる。全プロジェクトなら user settings に `sandbox.enabled: true`）。
- **auto-allowモード**: サンドボックス内で走るBashは**無承認で自動実行**（境界そのものが承認の代わり）。deny ルール・`Bash(git push *)` 型のaskルール・`rm -rf /`系は引き続き効く。
- 既定の境界: **書き込み=作業ディレクトリ＋セッションtempのみ**、読み取り=ほぼ全域（**認証情報ファイルは既定で読める**——下記で塞ぐ）、ネットワーク=**事前許可ドメインなし**（初回にドメイン単位でプロンプト、`allowedDomains` で事前許可）。

### 設定例
```json
{
  "sandbox": {
    "enabled": true,
    "filesystem": {
      "allowWrite": ["~/.kube", "/tmp/build"],
      "denyRead": ["~/"], "allowRead": ["."]
    },
    "credentials": {
      "files": [{ "path": "~/.aws/credentials", "mode": "deny" },
                { "path": "~/.ssh", "mode": "deny" }],
      "envVars": [{ "name": "GITHUB_TOKEN", "mode": "deny" }]
    },
    "network": { "allowedDomains": ["registry.npmjs.org"] }
  }
}
```
- パス記法はpermissionルールと**違う**（`/`=絶対、`~/`=ホーム、相対=設定ファイルの場所基準）。
- **`sandbox.credentials` は必ず検討する**: 既定では `~/.ssh` や `~/.aws/credentials` が読めてしまう。組み込みのdeny listは無い。
- サンドボックスで動かないコマンド（docker、watchman系、macOSのGo製CLIのTLS等）は `excludedCommands` で外に出すか、失敗時にClaudeが `dangerouslyDisableSandbox` で外側再試行（通常の承認フローに乗る）。封じるには `allowUnsandboxedCommands: false`。
- 組織強制: managed settings で `enabled` + `failIfUnavailable: true` + `allowUnsandboxedCommands: false`。

### 限界（過信しない）
- プロキシは**TLSを覗かない**（ホスト名で許可判定）→ `github.com` のような広いドメイン許可はdomain fronting等での持ち出し経路になりうる。厳格な要件はTLS終端する custom proxy を。
- 隔離対象は**Bashのみ**。Read/Edit等はpermission層、computer useは実デスクトップで動く。
- サブエージェントも親セッションのサンドボックス設定を継承する。

**エージェント設計での位置づけ**: 自律度の高いエージェント（[`13 §4`](./13-advanced-agent-patterns.md)）を長時間走らせるなら、permissions＋フック＋サンドボックスの3層を成果物に含める。無人実行の隔離境界の比較（devcontainer/コンテナ/VM）は公式 [Sandbox environments](https://code.claude.com/docs/en/sandbox-environments)。

---

## パート2: チェックポイント・セッション（やり直しと再開）

- **チェックポイント**: プロンプト毎にファイル編集前の状態を自動記録。`/rewind`（または空入力で `Esc` 2回）で「コードだけ／会話だけ／両方」を選んで巻き戻せる。**Summarize from/up to here** で会話の片側だけ要約圧縮もできる（`/compact` の狙い撃ち版）。
- **追跡されないもの（重要）**: **Bashコマンドによるファイル変更（`rm`/`mv`/`cp`等）は巻き戻せない**。セッション外の手動変更も対象外。**gitの代替ではない**——チェックポイント=ローカルundo、git=恒久履歴。
- **セッション**: `--continue`（直近）/ `--resume <id>`（指定）で再開。`claude --continue --fork-session` で元セッションを保ったまま分岐。30日で自動クリーンアップ（`cleanupPeriodDays`）。
- **worktree**: `/worktree`・サブエージェントの `isolation: worktree`（[`08`](./08-agent-primitives-and-composition.md)）で、並列作業をgit worktreeに隔離。

**エージェント設計での位置づけ**: 長期タスクのstate管理（[`14 §5`](./14-prompt-and-context-engineering.md)）と併せて、「実験的な変更はチェックポイントで守られるが、**Bash経由の破壊は守られない**」を前提に、破壊的Bashにはフック/サンドボックスを当てる。

---

## パート3: スケジュール実行（`/loop`・cron・Routines）

セッション内でプロンプトを繰り返し/指定時刻に実行する。**イベントに反応したいならポーリングでなく [Channels](https://code.claude.com/docs/en/channels)**（外部イベントをセッションにpush）、**条件達成まで回すなら `/goal`**、が使い分けの前提。

### 3つの選択肢
| | Cloud (Routines) | Desktop scheduled tasks | `/loop`（セッション内） |
|---|---|---|---|
| 実行場所 | Anthropicクラウド | 自分のマシン | 自分のマシン |
| マシン/セッション必要 | 不要/不要 | 必要/不要 | 必要/**必要** |
| 永続 | ○ | ○ | `--resume` で未失効分のみ復元 |
| ローカルファイル | ✕（fresh clone） | ○ | ○（セッション継承） |
| 最小間隔 | 1時間 | 1分 | 1分 |

### `/loop` の3形態
```text
/loop 5m デプロイが終わったか確認して結果を教えて   # 固定間隔（cron化される）
/loop CIが通ったか確認しレビューコメントに対応して    # Claudeが間隔を自己調整（1分〜1時間）
/loop                                              # 内蔵メンテナンスプロンプト（or .claude/loop.md）
```
- スキルも回せる: `/loop 20m /review-pr 1234`（ただし `disable-model-invocation: true` のスキルは実行されず素通し）。
- 一回きりは自然文で「15時にリリースブランチをpushするようリマインドして」→ 単発cronが作られ自動削除。
- 裏側のツールは `CronCreate`/`CronList`/`CronDelete`（5フィールドcron、ローカルタイムゾーン、セッション50個まで）。
- **要注意の仕様**: 発火は**ターンの合間**（実行中は待つ）／**ジッター**あり（毎時ジョブは最大30分遅れ得る。正確な時刻が要るなら `:00`/`:30` を避ける）／**再帰タスクは7日で自動失効**／取りこぼしの追い付き実行は無い。
- 動的 `/loop` では、ポーリングより **Monitorツール**（バックグラウンドコマンドの出力行を逐次フィードバック）の方がトークン効率が良い場合がある。

**エージェント設計での位置づけ**: 「PRを見張る」「ビルドを待つ」系の要件はエージェントを自作する前に `/loop`＋既存スキルで足りないか（フェーズ3.5の再利用優先）。無人・永続が要件なら Routines / GitHub Actions（[`05`](./05-build-and-output-templates.md) テンプレO）へ。

---

## パート4: Agent Teams（実験的・相互通信するセッション群）

サブエージェント（[`08`](./08-agent-primitives-and-composition.md)）が「親に結果を返すだけ」なのに対し、**agent teams は互いにメッセージし合い、共有タスクリストを自分たちでclaimする独立セッション群**。`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` で有効化する実験的機能。

### サブエージェントとの使い分け（ここが判断の核心）
| | サブエージェント | agent teams |
|---|---|---|
| 通信 | 親に報告のみ | **チームメイト同士が直接対話** |
| 調整 | 親が全部管理 | 共有タスクリスト＋自律claim |
| 向く仕事 | 結果だけ欲しい集中作業 | 議論・相互批判・協調が要る複雑作業 |
| トークン | 低（要約が戻る） | **高**（各自が独立セッション） |

**まずサブエージェントで足りないか問う**（[`13 §0`](./13-advanced-agent-patterns.md) のシンプルさ原則）。効くのは: 競合仮説のデバッグ（互いに反証させる）、多観点の並列レビュー、層をまたぐ機能開発（frontend/backend/testを各自が所有）。逐次作業・同一ファイル編集には不向き。

### 要点
- 自然文で起動: 「3人のチームメイトをspawnして、UX/アーキテクチャ/悪魔の代弁者の観点で検討させて」。リードが調整・統合。
- **サブエージェント定義を役割として再利用できる**（`security-reviewer` 等の定義の `tools`/`model` が効く。`skills`/`mcpServers` フィールドは無視）。
- 計画承認を課せる（teammateはリード承認までplan mode）。品質ゲートは `TeammateIdle`/`TaskCreated`/`TaskCompleted` フック（exit 2で差し戻し）。
- 権限はspawn時にリードから継承。teammateの承認要求はリードにバブルアップ（**teammate同士で承認を代行できない**設計）。
- ベストプラクティス: 3〜5人から／1人あたりタスク5〜6個／**同一ファイルを複数人に触らせない**／research・reviewから始める。
- 制限: `/resume` でin-processチームメイトは復元されない、ネスト不可、リード固定、1セッション1チーム。

**エージェント設計での位置づけ**: [`13 §3-4`](./13-advanced-agent-patterns.md) のオーケストレーター・ワーカーや並列化（投票・相互反証）を、**Claude Code上で最も忠実に実装する手段**の一つ。ただし実験的・高コストなので、フェーズ0の優先順位が「精度・網羅」で、かつ相互通信が本当に要る時だけ。

---

## 使い分けの総括（要件 → 機能）

| 要件 | 使う機能 |
|---|---|
| Bashを承認なしで安全に走らせたい | サンドボックス（auto-allow）＋credentials保護 |
| 失敗したら元に戻したい | チェックポイント（`/rewind`）。Bash破壊は対象外→フック/サンドボックスで予防 |
| 一定間隔で見張らせたい | `/loop`（セッション内）→ 無人なら Routines / GitHub Actions |
| 外部イベントに反応させたい | Channels（ポーリングしない） |
| ログを監視して反応させたい | Monitor ツール |
| 並列に調べて結果だけ欲しい | サブエージェント（[`08`](./08-agent-primitives-and-composition.md)） |
| 並列に作業させ、相互に議論・反証させたい | agent teams（実験的・高コスト） |

## チェックリスト
- [ ] 自律実行の成果物に sandbox 設定（credentials保護込み）を含めるか検討した
- [ ] チェックポイントが守らない範囲（Bash破壊・外部変更）を予防策と対にした
- [ ] 見張り系の要件を、自作エージェントの前に `/loop`・Monitor・Channels で検討した
- [ ] teams はサブエージェントで足りないと確認してから（相互通信が本当に必要か）
