#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
つぎの一歩 (tsugi) — ADHD向け タスク分解 & 計画ストア

使い方の前提:
  分解そのものは Claude Code(チャット)が行う。ユーザーは自然言語で
  「AとBというタスクがある」と話すだけ。Claude Code が極小ステップへ
  分解し、このツールに JSON で流し込み(plan)、WBS / カンバンで見せる。

  → 詳しい運用は CLAUDE.md を参照。

主なコマンド:
  plan            分解済みの計画(JSON)を流し込む(Claude Codeが使う)
  wbs             WBSツリーで表示
  board           カンバンで表示
  now             いまやる一歩を1つ表示
  done / skip     一歩を完了 / 後回し
  add / step      手動で 仕事 / 一歩 を足す
  ls / show / rm / status / where
"""

import sys, os, json, argparse, datetime, re, textwrap, shutil

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "next_step_data.json")
SELF = os.path.basename(__file__)

# ---------- 色(対応端末のみ) ----------
_TTY = sys.stdout.isatty()
def c(code, s): return f"\033[{code}m{s}\033[0m" if _TTY else s
def bold(s):  return c("1", s)
def dim(s):   return c("2", s)
def amber(s): return c("33", s)
def green(s): return c("32", s)
def cyan(s):  return c("36", s)
def red(s):   return c("31", s)
def blue(s):  return c("34", s)

# ---------- データ ----------
def load():
    if not os.path.exists(DATA_FILE):
        return {"next_id": 1, "tasks": []}
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        print(red("データファイルが壊れています: " + DATA_FILE)); sys.exit(1)
    db.setdefault("next_id", 1)
    db.setdefault("tasks", [])
    return db

def save(db):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def find(db, tid):
    return next((t for t in db["tasks"] if t["id"] == tid), None)

def progress(t):
    steps = t.get("steps", [])
    return round(sum(1 for s in steps if s["done"]) / len(steps) * 100) if steps else 0

def status_label(t):
    return {"inbox": "未分解", "active": "進行中", "done": "完了"}.get(t["status"], t["status"])

def bar(pct, width=10):
    fill = round(pct / 100 * width)
    return "▓" * fill + "░" * (width - fill)

def col_of(t):
    """カンバンの列を決める: todo / doing / done"""
    if t["status"] == "done":
        return "done"
    if t["status"] == "inbox":
        return "todo"
    return "doing" if progress(t) > 0 else "todo"

# ---------- ステップ正規化 ----------
def norm_step(s):
    if isinstance(s, str):
        text, mins = s, None
    elif isinstance(s, dict):
        text = (s.get("text") or s.get("step") or "").strip()
        mins = s.get("mins")
        if isinstance(mins, str):
            try: mins = int(re.sub(r"\D", "", mins) or 0) or None
            except Exception: mins = None
        elif not isinstance(mins, (int, float)):
            mins = None
    else:
        return None
    text = (text or "").strip()
    if not text:
        return None
    return {"text": text, "mins": mins, "done": bool(s.get("done")) if isinstance(s, dict) else False}

# ---------- 表示ヘルパ ----------
def disp_w(s):
    """全角=2,半角=1 のおおよその表示幅"""
    w = 0
    for ch in s:
        w += 2 if ord(ch) > 0x1100 and (
            0x1100 <= ord(ch) <= 0x115F or 0x2E80 <= ord(ch) <= 0xA4CF or
            0xAC00 <= ord(ch) <= 0xD7A3 or 0xF900 <= ord(ch) <= 0xFAFF or
            0xFE30 <= ord(ch) <= 0xFE4F or 0xFF00 <= ord(ch) <= 0xFF60 or
            0xFFE0 <= ord(ch) <= 0xFFE6 or 0x1F300 <= ord(ch) <= 0x1FAFF) else 1
    return w

def wrap_disp(text, width):
    """表示幅でラップ(全角考慮)"""
    lines, cur, cw = [], "", 0
    for ch in text:
        w = disp_w(ch)
        if cw + w > width:
            lines.append(cur); cur, cw = ch, w
        else:
            cur += ch; cw += w
    if cur:
        lines.append(cur)
    return lines or [""]

def pad(text, width):
    return text + " " * max(0, width - disp_w(text))

def fmt_mins(m):
    return " " + amber(f"⏱{m}分") if m else ""

# ---------- コマンド ----------
def cmd_add(db, args):
    title = " ".join(args.title).strip()
    if not title:
        print(red("タイトルが空です。")); return
    t = {"id": db["next_id"], "title": title, "project": args.project or "",
         "note": "", "status": "inbox", "steps": [],
         "created": datetime.datetime.now().isoformat(timespec="seconds")}
    db["next_id"] += 1
    db["tasks"].insert(0, t)
    save(db)
    print(green("📥 追加: ") + f"#{t['id']} {title}")

def cmd_plan(db, args):
    """Claude Code が分解結果(JSON)を流し込む。
    形式: {"tasks":[{"title":..,"project":..,"note":..,"steps":[{"text":..,"mins":..}, "..."]}]}
    既存IDを指定すれば、その仕事のステップを置き換える。"""
    raw = open(args.file, encoding="utf-8").read() if (args.file and args.file != "-") else sys.stdin.read()
    try:
        data = json.loads(raw)
    except Exception as e:
        print(red(f"JSONを読めませんでした: {e}")); return
    tasks_in = data.get("tasks") if isinstance(data, dict) else (data if isinstance(data, list) else None)
    if not isinstance(tasks_in, list):
        print(red('形式が違います。{"tasks":[...]} を渡してください。')); return
    created, updated = 0, 0
    for item in tasks_in:
        if not isinstance(item, dict):
            continue
        steps = [s for s in (norm_step(x) for x in item.get("steps", [])) if s]
        tid = item.get("id")
        existing = find(db, tid) if tid else None
        if existing:
            existing["steps"] = steps
            if "title" in item: existing["title"] = item["title"]
            if "project" in item: existing["project"] = item["project"] or ""
            if "note" in item: existing["note"] = item["note"] or ""
            if existing["status"] == "inbox" and steps:
                existing["status"] = "active"
            updated += 1
        else:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            t = {"id": db["next_id"], "title": title,
                 "project": (item.get("project") or "").strip(),
                 "note": (item.get("note") or "").strip(),
                 "status": "active" if steps else "inbox", "steps": steps,
                 "created": datetime.datetime.now().isoformat(timespec="seconds")}
            db["next_id"] += 1
            db["tasks"].append(t)
            created += 1
    save(db)
    print(green(f"✓ 取り込み完了: 新規 {created}件 / 更新 {updated}件"))

def cmd_list(db, args):
    tasks = db["tasks"]
    if not tasks:
        print(dim("  まだ何もありません。")); return
    groups = [("📥 未分解", [t for t in tasks if t["status"] == "inbox"], cyan),
              ("🗂  進行中", [t for t in tasks if t["status"] == "active"], amber),
              ("✓ 完了",   [t for t in tasks if t["status"] == "done"], green)]
    for label, items, col in groups:
        if not items:
            continue
        print(bold(col(f"\n{label} ({len(items)})")))
        for t in items:
            steps = t.get("steps", [])
            cnt = f"{sum(1 for s in steps if s['done'])}/{len(steps)}" if steps else "—"
            proj = dim(f"[{t['project']}] ") if t.get("project") else ""
            print(f"  {bold('#'+str(t['id'])):>5}  {proj}{t['title']}  {dim(bar(progress(t)))} {progress(t)}% ({cnt})")
    print()

def cmd_show(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    proj = f"  [{t['project']}]" if t.get("project") else ""
    print("\n" + bold(f"#{t['id']}  {t['title']}") + dim(proj) + f"   {status_label(t)}  {progress(t)}%")
    if t.get("note"): print(dim("  補足: " + t["note"]))
    steps = t.get("steps", [])
    if not steps:
        print(dim("  まだ分解されていません。"))
    else:
        print()
        for i, s in enumerate(steps, 1):
            mark = green("✓") if s["done"] else dim("○")
            text = dim(s["text"]) if s["done"] else s["text"]
            print(f"  {mark} {bold(str(i)+'.'):>4} {text}{fmt_mins(s.get('mins'))}")
    print()

# ---------- WBS ----------
def cmd_wbs(db, args):
    tasks = [t for t in db["tasks"] if t["status"] != "done"] if not args.all else db["tasks"]
    if not tasks:
        print(dim("  表示する仕事がありません。 (完了も見るには --all)")); return
    projects = {}
    for t in tasks:
        projects.setdefault(t.get("project") or "(プロジェクト未設定)", []).append(t)
    print(bold(blue("\n📐 WBS — 仕事の分解ツリー")))
    for pname, items in projects.items():
        print("\n" + bold("▣ " + pname))
        for ti, t in enumerate(items):
            last_t = ti == len(items) - 1
            tb = "└─" if last_t else "├─"
            head = f" {bold('#'+str(t['id']))} {t['title']}  {dim(bar(progress(t)))} {progress(t)}%"
            print(dim(tb) + head)
            steps = t.get("steps", [])
            indent = "   " if last_t else dim("│  ")
            for si, s in enumerate(steps):
                last_s = si == len(steps) - 1
                sb = "└─" if last_s else "├─"
                mark = green("✓") if s["done"] else "○"
                txt = dim(s["text"]) if s["done"] else s["text"]
                print(indent + dim(sb) + f" {mark} {txt}{fmt_mins(s.get('mins'))}")
            if not steps:
                print(indent + dim("└─ (未分解)"))
    print()

# ---------- カンバン ----------
def cmd_board(db, args):
    cols = [("📥 ToDo", "todo", cyan), ("🔨 Doing", "doing", amber), ("✅ Done", "done", green)]
    buckets = {k: [] for _, k, _ in cols}
    src = db["tasks"] if args.all else [t for t in db["tasks"]
                                        if not (t["status"] == "done")] + [t for t in db["tasks"] if t["status"] == "done"]
    for t in db["tasks"]:
        buckets[col_of(t)].append(t)
    term_w = shutil.get_terminal_size((90, 20)).columns
    cw = max(20, min(34, (term_w - 4) // 3))
    # 各列のカードを行リストへ
    def card_lines(t):
        lines = []
        proj = f"[{t['project']}] " if t.get("project") else ""
        for ln in wrap_disp(f"#{t['id']} {proj}{t['title']}", cw - 2):
            lines.append(" " + ln)
        steps = t.get("steps", [])
        if steps:
            lines.append(" " + dim(bar(progress(t), 8)) + f" {progress(t)}%")
            nxt = next((s for s in steps if not s["done"]), None)
            if nxt and t["status"] != "done":
                for ln in wrap_disp("→ " + nxt["text"], cw - 2):
                    lines.append(" " + dim(ln))
        else:
            lines.append(" " + dim("(未分解)"))
        lines.append("")  # カード間スペース
        return lines
    columns = []
    for label, key, col in cols:
        body = [bold(col(label)) + dim(f" ({len(buckets[key])})"), dim("─" * cw)]
        for t in buckets[key]:
            body += card_lines(t)
        columns.append(body)
    height = max(len(c) for c in columns)
    print(bold(blue("\n🗂  カンバン")))
    for r in range(height):
        row = ""
        for ci, colbody in enumerate(columns):
            cell = colbody[r] if r < len(colbody) else ""
            # ANSIを除いた表示幅でパディング
            plain = re.sub(r"\033\[[0-9;]*m", "", cell)
            row += cell + " " * max(0, cw - disp_w(plain)) + dim("│ ")
        print(row)
    print()

# ---------- now / done / skip ----------
def next_step(db):
    for t in db["tasks"]:
        if t["status"] != "active":
            continue
        for s in t.get("steps", []):
            if not s["done"]:
                return t, s
    return None, None

def cmd_now(db, args):
    t, s = next_step(db)
    print()
    if not t:
        if any(x["status"] == "active" for x in db["tasks"]):
            print(green("  🎉 いまやる一歩は全部おわり！ おつかれさま。"))
        elif any(x["status"] == "inbox" for x in db["tasks"]):
            print(cyan("  📥 未分解の仕事があります。分解しましょう。"))
        else:
            print(dim("  🌱 まだ一歩がありません。"))
        print(); return
    done = sum(1 for x in t["steps"] if x["done"]); total = len(t["steps"])
    print(dim("  いまの仕事: ") + amber(t["title"]) + dim(f"  ({done}/{total})"))
    print("\n   👉 " + bold(s["text"]))
    if s.get("mins"): print("      " + amber(f"だいたい {s['mins']}分"))
    print("\n" + dim(f"  できたら: python {SELF} done {t['id']}    後回し: python {SELF} skip {t['id']}") + "\n")

def cmd_done(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    steps = t.get("steps", [])
    if not steps: print(dim("一歩がありません。")); return
    if args.step:
        if not (1 <= args.step <= len(steps)): print(red("その番号の一歩はありません。")); return
        idx = args.step - 1
    else:
        idx = next((i for i, s in enumerate(steps) if not s["done"]), None)
        if idx is None: print(green("もう全部できています！")); return
    steps[idx]["done"] = True
    if t["status"] == "inbox": t["status"] = "active"
    if all(s["done"] for s in steps):
        t["status"] = "done"; save(db)
        print(green(f"🎉 「{t['title']}」 完了！ おつかれさま。")); return
    save(db)
    print(green("✓ できた: ") + steps[idx]["text"])
    nt, ns = next_step(db)
    if nt and nt["id"] == t["id"]:
        print(dim("  つぎ → ") + bold(ns["text"]) + (dim(f"  ⏱{ns['mins']}分") if ns.get("mins") else ""))

def cmd_skip(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    steps = t.get("steps", [])
    idx = next((i for i, s in enumerate(steps) if not s["done"]), None)
    if idx is None: print(dim("後回しにする一歩がありません。")); return
    s = steps.pop(idx); steps.append(s); save(db)
    print(dim("⤵ 後回し: ") + s["text"])

def cmd_step(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    text = " ".join(args.text).strip()
    if not text: print(red("内容が空です。")); return
    t.setdefault("steps", []).append({"text": text, "mins": args.mins, "done": False})
    if t["status"] == "inbox": t["status"] = "active"
    save(db); print(green("＋ 足しました: ") + text)

def cmd_status(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    if args.state not in ("inbox", "active", "done"):
        print(red("状態は inbox / active / done。")); return
    t["status"] = args.state; save(db)
    print(green(f"#{t['id']} → {status_label(t)}"))

def cmd_rm(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    db["tasks"] = [x for x in db["tasks"] if x["id"] != args.id]; save(db)
    print(dim(f"🗑 削除: #{t['id']} {t['title']}"))

def cmd_where(db, args):
    print("データの保存先:\n  " + DATA_FILE)

# ---------- パーサ ----------
def build_parser():
    p = argparse.ArgumentParser(prog="tsugi", description="つぎの一歩 — ADHD向け タスク分解&計画ストア",
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    sp = sub.add_parser("add", help="仕事を足す"); sp.add_argument("title", nargs="+"); sp.add_argument("--project")
    sp = sub.add_parser("plan", help="分解済み計画(JSON)を流し込む(Claude Code用)"); sp.add_argument("--file", help="JSONファイル('-'で標準入力)")
    sub.add_parser("wbs", help="WBSツリー表示").add_argument("--all", action="store_true", help="完了も表示")
    sub.add_parser("board", help="カンバン表示").add_argument("--all", action="store_true", help="完了列も常に表示")
    sub.add_parser("now", help="いまやる一歩を1つ表示")
    sub.add_parser("ls", aliases=["list"], help="一覧")
    sp = sub.add_parser("show", help="詳細表示"); sp.add_argument("id", type=int)
    sp = sub.add_parser("done", help="一歩を完了"); sp.add_argument("id", type=int); sp.add_argument("step", type=int, nargs="?")
    sp = sub.add_parser("skip", help="一歩を後回し"); sp.add_argument("id", type=int)
    sp = sub.add_parser("step", help="一歩を手で足す"); sp.add_argument("id", type=int); sp.add_argument("text", nargs="+"); sp.add_argument("--mins", type=int)
    sp = sub.add_parser("status", help="状態変更"); sp.add_argument("id", type=int); sp.add_argument("state")
    sp = sub.add_parser("rm", help="削除"); sp.add_argument("id", type=int)
    sub.add_parser("where", help="データ保存先")
    return p

DISPATCH = {"add": cmd_add, "plan": cmd_plan, "wbs": cmd_wbs, "board": cmd_board,
            "now": cmd_now, "ls": cmd_list, "list": cmd_list, "show": cmd_show,
            "done": cmd_done, "skip": cmd_skip, "step": cmd_step,
            "status": cmd_status, "rm": cmd_rm, "where": cmd_where}

def main(argv):
    parser = build_parser()
    if not argv:
        cmd_board(load(), argparse.Namespace(all=False)); return
    args = parser.parse_args(argv)
    fn = DISPATCH.get(args.cmd)
    if not fn:
        parser.print_help(); return
    fn(load(), args)

if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print()
