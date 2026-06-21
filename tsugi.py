#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
つぎの一歩 (tsugi) — ADHD向け タスク自動分解 & 計画 CLI

仕事を放り込む → AIに「極小の次の一歩」へ分解させる(往復方式) →
「いまやる一歩」を1つだけ表示する。

- 標準ライブラリのみ。追加インストール不要。
- AIとの対話(コピペ)以外はすべてオフラインで完結。
- データは同じフォルダの next_step_data.json に保存。
  フォルダごとコピーすれば別PCでもそのまま使える。

使い方の例:
  python tsugi.py add "請求書を送る"     # 受信トレイに放り込む
  python tsugi.py ls                      # 一覧
  python tsugi.py b 1                     # 1番を分解するプロンプトを出す→AIに貼る
  python tsugi.py import 1                # AIの返事を貼り付け(Ctrl-Dで確定)→取り込む
  python tsugi.py now                     # いまやる一歩を1つ表示(引数なしでもOK)
  python tsugi.py done 1                  # いまの一歩を「できた」に
  python tsugi.py skip 1                  # いまの一歩を後回し
  python tsugi.py split 1 2              # 1番の2歩目をさらに小さく割る
"""

import sys, os, json, argparse, datetime, re, shutil, subprocess

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "next_step_data.json")

# ---------- 色(対応端末のみ) ----------
_TTY = sys.stdout.isatty()
def c(code, s):
    return f"\033[{code}m{s}\033[0m" if _TTY else s
def bold(s):   return c("1", s)
def dim(s):    return c("2", s)
def amber(s):  return c("33", s)
def green(s):  return c("32", s)
def cyan(s):   return c("36", s)
def red(s):    return c("31", s)

# ---------- データ ----------
def load():
    if not os.path.exists(DATA_FILE):
        return {"next_id": 1, "tasks": []}
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        print(red("データファイルが壊れています: " + DATA_FILE))
        sys.exit(1)
    db.setdefault("next_id", 1)
    db.setdefault("tasks", [])
    return db

def save(db):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def find(db, tid):
    for t in db["tasks"]:
        if t["id"] == tid:
            return t
    return None

def progress(t):
    steps = t.get("steps", [])
    if not steps:
        return 0
    return round(sum(1 for s in steps if s["done"]) / len(steps) * 100)

def status_label(t):
    return {"inbox": "未分解", "active": "進行中", "done": "完了"}.get(t["status"], t["status"])

def bar(pct, width=12):
    fill = round(pct / 100 * width)
    return "█" * fill + "·" * (width - fill)

# ---------- AIプロンプト ----------
PROMPT_TEMPLATE = '''あなたはADHDの人の「実行支援コーチ」です。次の仕事を、いますぐ動ける「極小の次の一歩」へ分解してください。

# 仕事
__TITLE__
__NOTE__
# 分解のルール
- 1ステップ = 物理的に1アクション。「〜について考える」など曖昧なものは禁止。
- 最初のステップは「2分以内・座ったまま始められる」具体行動にする(例: ファイルを開く / 宛先を1人だけ書く)。
- 各ステップに目安の所要時間(分)を付ける。基本は1〜10分。重いものは更に割る。
- 「頑張る/集中する」等の精神論は入れない。迷いどころは選択肢を埋めて消す。
- ステップ数は3〜8個。多すぎないこと。

# 出力フォーマット(重要)
説明や前置きは書かず、次のJSONだけをコードブロックで出力してください:
```json
{"steps":[{"text":"最初の極小の一歩","mins":2},{"text":"次の一歩","mins":5}]}
```'''

def build_prompt(title, note=""):
    note_block = ("# 補足\n" + note + "\n") if note else ""
    return PROMPT_TEMPLATE.replace("__TITLE__", title).replace("__NOTE__\n", note_block)

def parse_steps(raw):
    if not raw or not raw.strip():
        return None
    txt = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt, re.I)
    if m:
        txt = m.group(1).strip()
    obj = None
    try:
        obj = json.loads(txt)
    except Exception:
        m2 = re.search(r"\{[\s\S]*\}", txt)
        if m2:
            try:
                obj = json.loads(m2.group(0))
            except Exception:
                obj = None
    if not obj or not isinstance(obj.get("steps"), list):
        return None
    steps = []
    for s in obj["steps"]:
        if isinstance(s, str):
            text, mins = s, None
        elif isinstance(s, dict):
            text = s.get("text") or s.get("step") or ""
            mins = s.get("mins")
            if isinstance(mins, str):
                try: mins = int(re.sub(r"\D", "", mins) or 0) or None
                except Exception: mins = None
            elif not isinstance(mins, (int, float)):
                mins = None
        else:
            continue
        text = (text or "").strip()
        if text:
            steps.append({"text": text, "mins": mins, "done": False})
    return steps or None

def copy_to_clipboard(text):
    candidates = [["pbcopy"], ["clip"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-b"]]
    for cmd in candidates:
        if shutil.which(cmd[0]):
            try:
                p = subprocess.run(cmd, input=text.encode("utf-8"))
                if p.returncode == 0:
                    return cmd[0]
            except Exception:
                pass
    return None

# ---------- 表示 ----------
def fmt_mins(m):
    return f" {amber('⏱'+str(m)+'分')}" if m else ""

def print_task_line(t):
    pct = progress(t)
    sl = status_label(t)
    sl_c = {"未分解": cyan, "進行中": amber, "完了": green}.get(sl, dim)(sl)
    steps = t.get("steps", [])
    cnt = f"{sum(1 for s in steps if s['done'])}/{len(steps)}" if steps else "—"
    print(f"  {bold('#'+str(t['id'])):>5}  [{sl_c}] {t['title']}")
    if steps:
        print(f"         {dim(bar(pct))} {pct}%  ({cnt})")

# ---------- コマンド ----------
def cmd_add(db, args):
    title = " ".join(args.title).strip()
    if not title:
        print(red("タイトルが空です。")); return
    t = {"id": db["next_id"], "title": title, "note": "", "status": "inbox",
         "steps": [], "created": datetime.datetime.now().isoformat(timespec="seconds")}
    db["next_id"] += 1
    db["tasks"].insert(0, t)
    save(db)
    print(green(f"📥 受信トレイに追加: ") + f"#{t['id']} {title}")
    print(dim(f"   分解するには:  python {os.path.basename(__file__)} b {t['id']}"))

def cmd_list(db, args):
    tasks = db["tasks"]
    if args.inbox:
        tasks = [t for t in tasks if t["status"] == "inbox"]
    inbox  = [t for t in tasks if t["status"] == "inbox"]
    active = [t for t in tasks if t["status"] == "active"]
    done   = [t for t in tasks if t["status"] == "done"]
    if not tasks:
        print(dim("  まだ何もありません。 `add \"やること\"` で放り込もう。")); return
    if inbox:
        print(bold(cyan(f"\n📥 受信トレイ・未分解 ({len(inbox)})")))
        for t in inbox: print_task_line(t)
    if active and not args.inbox:
        print(bold(amber(f"\n🗂  進行中 ({len(active)})")))
        for t in active: print_task_line(t)
    if done and not args.inbox:
        print(bold(green(f"\n✓ 完了 ({len(done)})")))
        for t in done: print_task_line(t)
    print()

def cmd_show(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    print()
    print(bold(f"#{t['id']}  {t['title']}") + f"   [{status_label(t)}]  {progress(t)}%")
    if t.get("note"): print(dim("  補足: " + t["note"]))
    steps = t.get("steps", [])
    if not steps:
        print(dim("\n  まだ分解されていません。  ") + f"python {os.path.basename(__file__)} b {t['id']}")
    else:
        print()
        for i, s in enumerate(steps, 1):
            mark = green("✓") if s["done"] else dim("○")
            text = dim(s["text"]) if s["done"] else s["text"]
            print(f"  {mark} {bold(str(i)+'.'):>3} {text}{fmt_mins(s.get('mins'))}")
    print()

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
    if not t:
        has_active = any(x["status"] == "active" for x in db["tasks"])
        has_inbox = any(x["status"] == "inbox" for x in db["tasks"])
        print()
        if has_active:
            print(green("  🎉 いまやる一歩は全部おわり！ おつかれさま。"))
        elif has_inbox:
            print(cyan("  📥 未分解の仕事があります。 `b <番号>` で分解しよう。"))
        else:
            print(dim("  🌱 まだ一歩がありません。 `add \"やること\"` から。"))
        print()
        return
    done = sum(1 for x in t["steps"] if x["done"])
    total = len(t["steps"])
    print()
    print(dim(f"  いまの仕事: ") + amber(t["title"]) + dim(f"  ({done}/{total})"))
    print()
    print("   👉 " + bold(s["text"]))
    if s.get("mins"):
        print("      " + amber(f"だいたい {s['mins']}分"))
    print()
    base = os.path.basename(__file__)
    print(dim(f"  できたら: python {base} done {t['id']}    ")
          + dim(f"重い→小さく: python {base} split {t['id']} {t['steps'].index(s)+1}"))
    print()

def cmd_breakdown(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    if args.note:
        t["note"] = args.note; save(db)
    prompt = build_prompt(t["title"], t.get("note", ""))
    used = copy_to_clipboard(prompt)
    base = os.path.basename(__file__)
    print()
    print(bold(cyan(f"#{t['id']} 「{t['title']}」 の分解プロンプト")))
    print(dim("─" * 50))
    print(prompt)
    print(dim("─" * 50))
    if used:
        print(green(f"📋 クリップボードにコピーしました ({used})。AIに貼って実行してください。"))
    else:
        print(dim("↑ これをコピーしてAI(Claude等)に貼り、実行してください。"))
    print(dim(f"AIの返事が出たら:  python {base} import {t['id']}  (貼り付けてCtrl-Dで確定)"))
    print()

def read_pasted(args):
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            return f.read()
    eof = "Ctrl-Z→Enter" if os.name == "nt" else "Ctrl-D"
    print(cyan(f"AIの返事をまるごと貼り付けて、最後に {eof} を押してください:"))
    print(dim("(JSON部分 {\"steps\":[…]} を含んでいればOK)"))
    return sys.stdin.read()

def cmd_import(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    raw = read_pasted(args)
    steps = parse_steps(raw)
    if not steps:
        print(red('⚠ うまく読み取れませんでした。 {"steps":[…]} を含む返事を貼ってください。')); return
    t["steps"] = steps
    if t["status"] == "inbox":
        t["status"] = "active"
    save(db)
    print(green(f"✓ {len(steps)}個の一歩に分解しました。"))
    cmd_show(db, argparse.Namespace(id=t["id"]))
    print(dim(f"  → まずは: python {os.path.basename(__file__)} now"))

def cmd_split(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    steps = t.get("steps", [])
    if not (1 <= args.step <= len(steps)):
        print(red(f"#{args.id} に {args.step}番目の一歩はありません。")); return
    target = steps[args.step - 1]
    prompt = build_prompt(target["text"],
                          f"これは「{t['title']}」の一歩。これ自体がまだ重いので、さらに極小に割ってください。")
    used = copy_to_clipboard(prompt)
    base = os.path.basename(__file__)
    print()
    print(bold(cyan(f"「{target['text']}」 をさらに小さく")))
    print(dim("─" * 50)); print(prompt); print(dim("─" * 50))
    if used: print(green(f"📋 コピーしました ({used})。"))
    print(dim(f"返事が出たら:  python {base} import {t['id']} --replace {args.step}"))
    print()

def cmd_done(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    steps = t.get("steps", [])
    if not steps:
        print(dim("一歩がありません。先に分解してください。")); return
    if args.step:
        if not (1 <= args.step <= len(steps)):
            print(red(f"{args.step}番目の一歩はありません。")); return
        idx = args.step - 1
    else:
        idx = next((i for i, s in enumerate(steps) if not s["done"]), None)
        if idx is None:
            print(green("もう全部できています！")); return
    steps[idx]["done"] = True
    if t["status"] == "inbox":
        t["status"] = "active"
    if all(s["done"] for s in steps):
        t["status"] = "done"
        save(db)
        print(green(f"🎉 「{t['title']}」 完了！ おつかれさま。"))
        return
    save(db)
    print(green(f"✓ できた: ") + steps[idx]["text"])
    nt, ns = next_step(db)
    if nt and nt["id"] == t["id"]:
        print(dim("  つぎ → ") + bold(ns["text"]) + (dim(f"  ⏱{ns['mins']}分") if ns.get("mins") else ""))

def cmd_skip(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    steps = t.get("steps", [])
    idx = next((i for i, s in enumerate(steps) if not s["done"]), None)
    if idx is None:
        print(dim("後回しにする一歩がありません。")); return
    s = steps.pop(idx)
    steps.append(s)
    save(db)
    print(dim("⤵ 後回しにしました: ") + s["text"])
    nt, ns = next_step(db)
    if nt:
        print(dim("  つぎ → ") + bold(ns["text"]))

def cmd_step(db, args):
    """一歩を手で足す"""
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    text = " ".join(args.text).strip()
    if not text:
        print(red("一歩の内容が空です。")); return
    t.setdefault("steps", []).append({"text": text, "mins": args.mins, "done": False})
    if t["status"] == "inbox":
        t["status"] = "active"
    save(db)
    print(green("＋ 足しました: ") + text)

def cmd_status(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    if args.state not in ("inbox", "active", "done"):
        print(red("状態は inbox / active / done のいずれか。")); return
    t["status"] = args.state
    save(db)
    print(green(f"#{t['id']} を {status_label(t)} にしました。"))

def cmd_rm(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    db["tasks"] = [x for x in db["tasks"] if x["id"] != args.id]
    save(db)
    print(dim(f"🗑 削除: #{t['id']} {t['title']}"))

def cmd_where(db, args):
    print("データの保存先:")
    print("  " + DATA_FILE)
    print(dim("このフォルダごと別PCにコピーすれば、タスクも一緒に移せます。"))

# ---------- パーサ ----------
def build_parser():
    p = argparse.ArgumentParser(
        prog="tsugi",
        description="つぎの一歩 — ADHD向け タスク分解&計画 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("add", help="受信トレイに仕事を放り込む"); sp.add_argument("title", nargs="+")
    sub.add_parser("now", help="いまやる一歩を1つ表示(既定)")
    sp = sub.add_parser("ls", aliases=["list"], help="一覧"); sp.add_argument("--inbox", action="store_true", help="未分解だけ")
    sp = sub.add_parser("show", help="詳細表示"); sp.add_argument("id", type=int)
    sp = sub.add_parser("b", aliases=["breakdown"], help="分解プロンプトを出す")
    sp.add_argument("id", type=int); sp.add_argument("--note", help="補足情報")
    sp = sub.add_parser("import", help="AIの返事を取り込む")
    sp.add_argument("id", type=int); sp.add_argument("--file", help="返事をファイルから読む"); sp.add_argument("--replace", type=int, help="指定番目の一歩を置き換える(splitの取り込み)")
    sp = sub.add_parser("split", help="一歩をさらに小さく割るプロンプト"); sp.add_argument("id", type=int); sp.add_argument("step", type=int)
    sp = sub.add_parser("done", help="一歩をできたにする"); sp.add_argument("id", type=int); sp.add_argument("step", type=int, nargs="?")
    sp = sub.add_parser("skip", help="いまの一歩を後回し"); sp.add_argument("id", type=int)
    sp = sub.add_parser("step", help="一歩を手で足す"); sp.add_argument("id", type=int); sp.add_argument("text", nargs="+"); sp.add_argument("--mins", type=int)
    sp = sub.add_parser("status", help="状態変更"); sp.add_argument("id", type=int); sp.add_argument("state")
    sp = sub.add_parser("rm", help="削除"); sp.add_argument("id", type=int)
    sub.add_parser("where", help="データ保存先を表示")
    return p

def main(argv):
    parser = build_parser()
    if not argv:
        db = load(); cmd_now(db, None); return
    args = parser.parse_args(argv)
    db = load()
    dispatch = {
        "add": cmd_add, "now": cmd_now, "ls": cmd_list, "list": cmd_list,
        "show": cmd_show, "b": cmd_breakdown, "breakdown": cmd_breakdown,
        "import": cmd_import, "split": cmd_split, "done": cmd_done,
        "skip": cmd_skip, "step": cmd_step, "status": cmd_status,
        "rm": cmd_rm, "where": cmd_where,
    }
    fn = dispatch.get(args.cmd)
    if not fn:
        parser.print_help(); return
    # importの--replace対応
    if args.cmd == "import" and getattr(args, "replace", None):
        return cmd_import_replace(db, args)
    fn(db, args)

def cmd_import_replace(db, args):
    t = find(db, args.id)
    if not t: print(red(f"#{args.id} が見つかりません。")); return
    steps = t.get("steps", [])
    if not (1 <= args.replace <= len(steps)):
        print(red(f"{args.replace}番目の一歩はありません。")); return
    raw = read_pasted(args)
    new_steps = parse_steps(raw)
    if not new_steps:
        print(red('⚠ 読み取れませんでした。')); return
    steps[args.replace - 1:args.replace] = new_steps
    save(db)
    print(green(f"✓ {args.replace}番目の一歩を {len(new_steps)}個に置き換えました。"))
    cmd_show(db, argparse.Namespace(id=t["id"]))

if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print()
