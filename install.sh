#!/usr/bin/env bash
# AIエージェント・ビルダーを対象プロジェクトの .claude/ に導入する。
# 使い方: ./install.sh /path/to/your-project
# （キットを単独リポジトリに切り出した後でも、templates/ から自己完結で導入できる）
set -euo pipefail

TARGET="${1:?対象プロジェクトのパスを指定してください}"
KIT_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$TARGET/.claude/skills/agent-builder" "$TARGET/.claude/agents"

# 本体スキル（メイン会話で対話的にフェーズを回す）
cp "$KIT_DIR/templates/agent-builder.SKILL.md" \
   "$TARGET/.claude/skills/agent-builder/SKILL.md"

# 調査専門サブエージェント（フェーズ3.5の大量探索を隔離して要約だけ返す）
cp "$KIT_DIR/templates/agent-builder-researcher.md" \
   "$TARGET/.claude/agents/agent-builder-researcher.md"

# リファレンスキット本体（スキルが必要時に読み込む）
# TARGET がキット自身（切り出し後のリポジトリ直下）の場合はコピー不要
TARGET_ABS="$(cd "$TARGET" && pwd)"
if [ "$KIT_DIR" != "$TARGET_ABS" ] && [ ! -d "$TARGET_ABS/ai-agent-builder" ]; then
  cp -r "$KIT_DIR" "$TARGET_ABS/ai-agent-builder"
  rm -f "$TARGET_ABS/ai-agent-builder/install.sh"
fi

cat <<'MSG'
導入完了:
  .claude/skills/agent-builder/SKILL.md        … /agent-builder で起動（スキルは即時反映）
  .claude/agents/agent-builder-researcher.md   … 調査用サブエージェント（新セッションから有効）
  ai-agent-builder/                            … 詳細リファレンス（スキルが必要時に参照）
推奨: 公式ドキュメント調査を無承認化する permissions.allow（ai-agent-builder/16 §2-5 参照）
MSG
