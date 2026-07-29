#!/usr/bin/env bash
# スコープガード（PreToolUse: Write|Edit）
# 目的: エージェントの「頼まれていない変更」を物理的に止める。
# 使い方: タスク開始時にエージェントが .claude/task-scope に
#         「このタスクで書き込むパスのパターン」を1行ずつ宣言する（#でコメント）。
#         宣言外パスへの書き込みは自動でユーザー確認（ask）に回る。
#         スコープの拡大 = task-scope への追記もスコープ外なので、必ずユーザー確認を通る。
#         .claude/task-scope が無ければガードは何もしない（通常利用の邪魔をしない）。
set -euo pipefail

input=$(cat)
proj="${CLAUDE_PROJECT_DIR:-$PWD}"
scope_file="$proj/.claude/task-scope"
[ -f "$scope_file" ] || exit 0

path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
[ -n "$path" ] || exit 0
rel="${path#"$proj"/}"

while IFS= read -r pat; do
  [ -z "$pat" ] && continue
  case "$pat" in \#*) continue ;; esac
  # bashのcaseパターンは * がスラッシュもまたぐ（例: ai-agent-builder/* は配下全て）
  case "$rel" in $pat) exit 0 ;; esac
done < "$scope_file"

cat <<EOF
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"宣言スコープ外への書き込み: $rel — .claude/task-scope に宣言が無い。頼まれていない変更の可能性。承認するか、スコープ宣言の更新を指示してください"}}
EOF
