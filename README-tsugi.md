# つぎの一歩 (tsugi)

ADHD向け。**仕事が来たら極小の「次の一歩」まで分解して、見やすく(WBS / カンバン)管理する** ためのツール。

分解は **Claude Code(チャット)が直接おこなう**。コピペの往復も外部APIも不要。すべて Claude Code 上で完結する。

## いちばん簡単な使い方

Claude Code のチャットで、こう話すだけ:

> いま「請求書を送る」と「勉強会の資料作り」と「健康診断の予約」がある。分解してカンバンで見せて。

Claude Code が各タスクを極小ステップへ分解し、`tsugi.py` に保存して、カンバン/WBSで表示し返します。
あとは「#1の最初のやつ終わった」と言えば進捗が更新されます。

(この自動運用のルールは `CLAUDE.md` に書いてあります)

## 自分で直接たたく場合

```bash
python tsugi.py board          # カンバン表示(引数なしでもこれ)
python tsugi.py wbs            # WBSツリー表示
python tsugi.py now            # いまやる一歩を1つだけ
python tsugi.py done 1         # #1 の次の一歩を完了
python tsugi.py skip 1         # 後回し
python tsugi.py add "やること" # 受信トレイに足す
python tsugi.py ls             # 一覧
python tsugi.py show 1         # 詳細
```

| コマンド | 説明 |
|---|---|
| `board [--all]` | カンバン(ToDo / Doing / Done) |
| `wbs [--all]` | WBSツリー(プロジェクト > 仕事 > 一歩) |
| `now` | いまやる一歩を1つ表示 |
| `plan --file -` | 分解済み計画(JSON)を流し込む ※主にClaude Codeが使う |
| `add "仕事" [--project 名]` | 仕事を足す |
| `step <id> "一歩" [--mins N]` | 一歩を手で足す |
| `done <id> [番号]` / `skip <id>` | 完了 / 後回し |
| `status <id> inbox\|active\|done` / `rm <id>` | 状態変更 / 削除 |
| `show <id>` / `ls` / `where` | 詳細 / 一覧 / 保存先 |

## 必要なもの

- Python 3（標準ライブラリのみ。追加インストール不要）
- データは `next_step_data.json` に保存。

## 仕組み

- ADHDの実行支援に効くよう、**最初の一歩は「2分・座ったまま始められる」具体行動**にし、各ステップに所要時間を付けて分解する(ルールは `CLAUDE.md`)。
- `tsugi.py` は「保存庫 + 表示器」。分解の知能は Claude Code が担うので、APIキー不要・チャット内完結。
