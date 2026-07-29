# study-memory — 分からなかったことの置き場

`study-buddy` スキルが読み書きする。**1項目 = 1ファイル**、`YYYYMMDD-ascii-slug.md`。

- 詰まったものを投げる → ここにファイルが増える
- 「問題出して」 → ここからランダムに1件 引いて、前回と違う形式で出る

`quiz.json` はここから作る**派生物**（`study-buddy.html` が同一オリジンで fetch する出題データ）。
md を直したら再生成する。スキーマは `.claude/skills/study-buddy/references/quiz-json-schema.md`。

索引ファイルは作らない（本体とズレて腐るから）。一覧は grep で取る:

```bash
grep -H -E "^(id|topic|tripped_on|last_asked|recent|formats_used):" study-memory/*.md
```

## 手で足していい

エディタで直接 書いてよい。frontmatterの必須キーは
`id / topic / tripped_on / added / last_asked / recent / formats_used / source`。
新規なら `last_asked: ""` `recent: ""` `formats_used: []` で置いておけば、次の出題で拾われる（未出題が最優先）。
ひな形は `.claude/skills/study-buddy/templates/item.md`。

## `recent` と `last_asked` は成績ではない

出題の順番を決めるためだけの内部状態。**正答率も連続日数もここからは作らないし、表示もしない。**
記録の提示はこの本人には効かない（`progress-engine-log.md`「已に潰した案」で確定）。
