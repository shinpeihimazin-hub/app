#!/usr/bin/env bash
# 公式マーケットプレイスから中核5プラグインをプロジェクトスコープで導入する（選定根拠: 19-living-registry.md §8）
# 実行場所: ネットワーク非遮断のローカルCLI環境で、このリポジトリをcloneした中から実行する
set -euo pipefail
cd "$(dirname "$0")/.."   # リポジトリルートへ

PLUGINS=(skill-creator mcp-server-dev plugin-dev agent-sdk-dev security-guidance)

# 公式マーケットプレイスはローカルCLIでは自動登録済みのはず。無い場合のみ追加
claude plugin marketplace list 2>/dev/null | grep -q "claude-plugins-official" || \
  claude plugin marketplace add anthropics/claude-plugins-official

for p in "${PLUGINS[@]}"; do
  echo "=== install: $p ==="
  claude plugin install "$p@claude-plugins-official" -s project
done

echo
echo "導入完了。プロジェクトスコープ(-s project)なので .claude/settings.json に記録されています。"
echo "リポジトリに固定するには:"
echo "  git add .claude/settings.json && git commit -m 'feat: 中核5プラグインを導入（台帳19 §8）' && git push"
echo
echo "注意: リモート実行環境（Claude Code on the web）でもこのプラグインを動かすには、"
echo "      セッションのGitHubリポジトリアクセスに anthropics/claude-plugins-official の追加が必要"
echo "      （プラグイン実体は起動時にマーケットプレイスから取得されるため）。"
