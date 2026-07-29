# vendor/ — 無改変で搬入した外部部品

## superpowers/
- 出所: https://github.com/obra/superpowers （MIT License — LICENSE同梱）
- 取得経路: ユーザーのfork https://github.com/shinpeihimazin-hub/superpowers 経由（完全clone）
- 取得時点: upstream SHA `d884ae04edebef577e82ff7c4e143debd0bbec99` / v6.1.1 / 2026-07-14搬入
- **中身は一切改変していない**（.gitのみ除去）。更新はforkをupstreamに同期→再cloneで上書き
- 配線: .claude/settings.json の SessionStart が hooks/run-hook.cmd session-start を呼び、
  using-superpowers を毎セッション冒頭に注入（本家プラグインと同一機構）。
  14スキルは .claude/skills/ にコピーして登録（同内容・無改変）
