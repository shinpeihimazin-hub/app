#!/usr/bin/env bash
# AIエージェント・ビルダーを対象プロジェクトの .claude/ に導入する。
# 使い方: ./install.sh /path/to/your-project
set -euo pipefail

TARGET="${1:?対象プロジェクトのパスを指定してください}"
KIT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$KIT_DIR/.." && pwd)"

mkdir -p "$TARGET/.claude/skills/agent-builder" "$TARGET/.claude/agents"

# 本体スキル（メイン会話で対話的にフェーズを回す）
cp "$REPO_ROOT/.claude/skills/agent-builder/SKILL.md" \
   "$TARGET/.claude/skills/agent-builder/SKILL.md" 2>/dev/null \
  || cp "$KIT_DIR/templates/agent-builder.SKILL.md" \
        "$TARGET/.claude/skills/agent-builder/SKILL.md"

# 調査専門サブエージェント（大量探索を隔離して要約だけ返す）
cp "$REPO_ROOT/.claude/agents/agent-builder-researcher.md" \
   "$TARGET/.claude/agents/agent-builder-researcher.md" 2>/dev/null || true

# リファレンスキット本体（スキルが必要時に読み込む）
if [ ! -d "$TARGET/ai-agent-builder" ]; then
  cp -r "$KIT_DIR" "$TARGET/ai-agent-builder"
  rm -f "$TARGET/ai-agent-builder/install.sh"
fi

cat <<'MSG'
導入完了:
  .claude/skills/agent-builder/SKILL.md   … /agent-builder で起動（スキルは即時反映）
  .claude/agents/agent-builder-researcher.md … 調査用サブエージェント（新セッションから有効）
  ai-agent-builder/                        … 詳細リファレンス（スキルが必要時に参照）
権限の推奨allow（公式ドキュメント調査の無承認化）は ai-agent-builder/16 §2-5 を参照。
MSG
