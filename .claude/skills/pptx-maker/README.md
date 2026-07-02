# pptx-maker — 会社テンプレ準拠のパワポ生成スキル

Claude Code 上で動く。対話ヒアリング→ストーリー承認→原稿承認→テンプレ流し込み→自動QA→最終承認、の6ステップで「そのまま使える」.pptx を作る。

## 構成（全て自前実装＋MITライセンス依存。再配布制約なし）

```
pptx-maker/
├── SKILL.md                 # 本体（/pptx-maker で起動）
├── references/              # 各ステップの手順書（S1/S3/S4/S6）
├── scripts/
│   ├── inspect_template.py  # テンプレ地図の生成（レイアウト/プレースホルダ列挙）
│   ├── build_deck.py        # deck.json → .pptx（テンプレのマスター準拠）
│   └── qa_render.py         # 幾何チェック＋PDF/PNGレンダリング（soffice検出時）
├── setup.sh                 # 依存導入（python-pptx / markitdown / pypdfium2）
└── requirements.txt
```

## 配布（完全同一・git経由）

利用者側の手順は3つだけ:

```bash
git clone <この配布リポジトリ>                 # 1. 取得
bash <repo>/.claude/skills/pptx-maker/setup.sh  # 2. 依存導入（Python3必須）
# 3. 対象プロジェクトの .claude/skills/ にこのフォルダをコピー（またはこのrepo内でそのまま使用）
```

- 前提: Python 3.10+ / Claude Code。
- LibreOffice は**任意**（あるとS6の視覚QAが全自動化。無くても幾何チェックで動く——setup.shが検出して案内を出す）。

## 機密設計（テンプレの読み込みは配布先PCで行う）

**配布物に機密は一切含まれない。** 会社テンプレ（.pptx）の読み込み・解析（テンプレ地図の生成）は、配布先の各PCで初回セットアップとして実施する:

| データ | 置き場所 | リポジトリへ |
|---|---|---|
| 会社テンプレ .pptx | 各PCの任意パス（`local/template.path` に記録） | ❌ 入らない |
| テンプレ地図 template-map.json | `pptx-maker/local/`（gitignore） | ❌ 入らない |
| ブリーフ・原稿・生成pptx・QA結果 | `pptx-work/`（gitignore） | ❌ 入らない |
| スキル・スクリプト・ガイド | 配布リポジトリ | ✅ これだけ |

`git push` しても機密がリポジトリに戻れない構造（.gitignoreで強制）。

## 品質の考え方

- ビジュアルの土台＝**会社テンプレのスライドマスター**（マスターは書き換えない）
- 流れの品質＝S3の「見出し＝主張の一文」リレー＋承認ゲート①
- 文章の品質＝S4の原稿ルール（references/draft-format.md）＋承認ゲート②
- 仕上がり保証＝S6の機械チェック＋レンダリング目視＋承認ゲート③
- 図表＝dataviz スキル（Claude Code同梱）の指針で描画

## 既知の制約（v1）
- pptxネイティブの表・グラフオブジェクトは未対応（画像として挿入する）
- 既存pptxの「編集」は未対応（新規生成のみ。編集はv2候補）
- 1回の生成は最大30スライド
