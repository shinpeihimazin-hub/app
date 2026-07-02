---
name: pptx-maker
description: 会社テンプレ準拠のパワポ（.pptx）を対話で作る。目的・聴衆のヒアリング→ストーリー設計→スライド原稿→テンプレ流し込み→自動品質QA→承認、の6ステップ。「パワポ」「スライド」「提案書」「deck」「プレゼン資料を作りたい」と言われたら使う。
when_to_use: ユーザーがプレゼン資料・提案書・報告書スライドを作りたいとき。内容が曖昧でもよい（S1のヒアリングで確定する）。
argument-hint: [作りたい資料の概要（任意）]
---

# pptx-maker — テンプレ準拠パワポ生成

依頼: $ARGUMENTS

このスキルの基準ディレクトリ（以下 `$SKILL`）: このSKILL.mdがあるディレクトリ。`references/` と `scripts/` を持つ。

## 絶対原則
1. **ステップを飛ばさない。承認ゲート（①②③）を省略しない。** ユーザーが「一気に」と明示した場合のみゲートをまとめる。
2. **テンプレ必須。** 会社テンプレ（.pptx）のパスが未指定なら、まず場所を聞く。**ダミーテンプレを勝手に作って進めない。**
3. 事実と推測を混ぜない。裏付けの無い数値・実績は使わず「要確認」としてスライドに明示する。
4. 生成物の品質判定は必ずレンダリング結果（PDF）を自分の目で見て行う。テキスト出力だけで「できました」と言わない。
5. 機密データはこのセッションの外（Web検索クエリ等）に出さない。

## 初回セットアップ（配布先PCで実施。機密はこのPCから出ない）
1. 依存の導入: `bash $SKILL/setup.sh` （python-pptx / markitdown。数十秒）
2. 会社テンプレ（.pptx）の場所をユーザーに確認する。**テンプレ本体はこのリポジトリに絶対にコミットしない**（`$SKILL/local/` と `pptx-work/` はgitignore済み）。
3. テンプレ地図の生成（ローカル完結）:
   ```bash
   mkdir -p $SKILL/local
   python3 $SKILL/scripts/inspect_template.py <テンプレ.pptx> --json $SKILL/local/template-map.json
   ```
   テンプレのパスを `$SKILL/local/template.path` に保存しておく（次回以降聞き直さない）。
4. 以後の作業ファイル（brief.md / deck.json / 生成pptx / qa/）はすべて `pptx-work/`（gitignore領域）に置く。

**機密設計**: 配布物に含まれるのはスキル・スクリプト・ガイドのみ。テンプレ・テンプレ地図・ブリーフ・生成物は各PCのgitignore領域で完結し、`git push` しても外に出ない。

## ステップ

### S1: インタビュー（`references/interview.md` を読んでから）
AskUserQuestionで 目的/聴衆/決裁者/結論/主張/材料/枚数/トーン を確定し、`pptx-work/brief.md` に構造化して保存。**結論が一文で言えるまで次へ進まない。**

### S2: 材料の取り込み
渡されたファイル（pptx/docx/pdf/xlsx）は `python3 -m markitdown <file>` でテキスト化して読む。材料が足りない場合は不足リストを提示していったん停止（勝手に補完しない）。

### S3: ストーリー設計（`references/story.md` を読んでから）
アウトライン（スライドごとの見出し＝キーメッセージ1行）を提示 → **承認ゲート①**。修正はこの段階で吸収する（最も手戻りが安い）。

### S4: スライド原稿（`references/draft-format.md` を読んでから）
承認済みアウトラインを `pptx-work/deck.json` に落とす。図表が必要なスライドは、**先に dataviz スキルを読み込み**、matplotlib等でPNGとして描き出してから `images` に指定する。全スライド分を提示 → **承認ゲート②**（大幅変更はS3へ戻る）。

### S5: 生成
```bash
python3 $SKILL/scripts/build_deck.py "$(cat $SKILL/local/template.path)" pptx-work/deck.json pptx-work/out.pptx
```
レイアウト割付は `$SKILL/local/template-map.json` の実在レイアウト名から選ぶ（存在しない名前を発明しない）。

### S6: 自動品質QA（最大3周）
```bash
python3 $SKILL/scripts/qa_render.py pptx-work/out.pptx pptx-work/qa/
```
1. `pptx-work/qa/qa_report.json` の警告（文字あふれ・空プレースホルダ）を修正
2. `pptx-work/qa/out.pdf` を **Readツールで開いて視覚確認**（崩れ・詰まり・トンマナ。`references/design-guide.md` の観点で）
3. 問題があれば `deck.json` を直してS5からやり直し（最大3周。直らない点は正直に報告）

### S7: 最終承認 → **承認ゲート③**
`out.pptx` と残課題（あれば）を提示。微修正はS4へ、OKなら完了。

## ブランド基準の参照（設定されている場合のみ）
組織のClaude Designプロジェクト（デザインシステム）が案内されている場合、S4の前にDesignSyncのread系で配色・トーン基準を確認する。未設定ならこの手順はスキップ（エラーにしない）。

## 制約
- 1回の生成は最大30スライド。超える場合は分割を提案。
- S6で解決できない品質問題は「既知の課題」として最終報告に必ず残す。
