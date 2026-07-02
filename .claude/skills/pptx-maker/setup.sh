#!/usr/bin/env bash
# pptx-maker の依存導入（各利用者の環境で1回実行）
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

python3 -m pip install -q -r "$HERE/requirements.txt"
python3 - <<'EOF'
import pptx, markitdown
print("python-pptx", pptx.__version__, "/ markitdown OK")
EOF

# レンダリングQA（任意機能）: LibreOffice Impress があると S6 の視覚検証が全自動になる
if command -v soffice >/dev/null 2>&1; then
  echo "soffice: あり（レンダリングQA有効）"
else
  cat <<'MSG'
soffice: なし → S6は幾何チェックのみで動作（視覚確認は生成物を各自PowerPointで開いて実施）
  有効化したい場合:
    - Ubuntu/Debian: sudo apt-get install -y --no-install-recommends libreoffice-impress
    - macOS:         brew install --cask libreoffice
    - Windows:       https://www.libreoffice.org/ からインストール（soffice.comにPATHを通す）
MSG
fi
echo "セットアップ完了。/pptx-maker で開始（テンプレ.pptxのパスを用意してください）"
