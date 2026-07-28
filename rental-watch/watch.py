#!/usr/bin/env python3
"""賃貸物件 監視スクリプト

不動産ジャパン と ハトマークサイト を確定条件で叩き、seen.json に無い物件だけを報告する。
SUUMO / LIFULL HOME'S / カナリー は対象外（本人が自分で見ているため）。

使い方:
    python3 rental-watch/watch.py            # 差分を報告し seen.json を更新
    python3 rental-watch/watch.py --dry-run  # seen.json を更新せず表示だけ
    python3 rental-watch/watch.py --all      # 既知も含めて全ヒットを表示

終了コード:
    0 = 新着なし（正常）
    1 = 新着あり
    2 = 取得エラー（サイト構造変化 / ネットワーク断の疑い）
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN_PATH = os.path.join(HERE, "seen.json")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# ---- 確定条件 (conditions.md と対応) -------------------------------------
RENT_CAP = 170000            # 賃料上限（円）
RENT_CAP_INCLUSIVE = False   # True にすると「管理費込み」で上限判定する
AREA_MIN = 40.0              # 専有面積 下限（㎡）
AGE_MAX = 25                 # 築年数 上限（年）
WALK_MAX = 15                # 駅徒歩 上限（分）

TARGET_STATIONS = {"田町", "高輪ゲートウェイ", "品川", "大崎",
                   "五反田", "目黒", "大井町", "大森"}

FDJ_STATION_CODES = ["C8MR8BDBN", "C8MR8BD5N", "C8MR8B5BD", "C8MR8BRBI",
                     "C8MR8BSB9", "C8MR8BXB4", "C8MX58RBI", "C8MX58SB9"]
HATO_WARDS = ["13109", "13111", "13110", "13103"]
FLOOR_PLANS = ["1XXSLDK", "2XXXXSK", "2XXXSDK", "2XXSLDK",
               "3XXXXSK", "3XXXSDK", "3XXSLDK", "4XXXXSK", "4XXXSDK"]

JST = timezone(timedelta(hours=9))


def fetch(url, timeout=90, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Language": "ja"})
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - ネットワーク起因は握って再試行
            last = exc
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed: {url} :: {last}")


def flatten(html_text):
    """タグを | に潰して1行化する。フィールド抽出用。"""
    body = re.sub(r"<script.*?</script>", "", html_text, flags=re.S)
    body = re.sub(r"<[^>]+>", "|", body)
    body = re.sub(r"\s+", " ", body)
    import html as _html
    return re.sub(r"\|+", "|", _html.unescape(body))


def field(text, label, width=60):
    m = re.search(re.escape(label) + r"[|\s：:]*([^|]{1,%d})" % width, text)
    return m.group(1).strip() if m else ""


def to_yen(s):
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*万", s)
    if m:
        return int(float(m.group(1).replace(",", "")) * 10000)
    m = re.search(r"([\d,]+)\s*円", s)
    return int(m.group(1).replace(",", "")) if m else None


def age_years(built_text):
    m = re.search(r"(\d{4})\D{0,4}年\D{0,4}(\d{1,2})?\s*月?", built_text)
    if not m:
        return None
    now = datetime.now(JST)
    y = int(m.group(1))
    mo = int(m.group(2)) if m.group(2) else 1
    return (now.year - y) + (now.month - mo) / 12.0


# --------------------------------------------------------------------------
# 不動産ジャパン
# --------------------------------------------------------------------------
def fudousan_japan():
    q = ["ptm%5B%5D=0303"]
    q += [f"wst%5B%5D={c}" for c in FDJ_STATION_CODES]
    q += [f"floor_plan%5B%5D={f}" for f in FLOOR_PLANS]
    q += [f"eki_walk={WALK_MAX}", "toil%5B%5D=TOIL04", "wsng%5B%5D=WSNG02",
          "wash%5B%5D=WASH13", f"exclusive_area_from={int(AREA_MIN)}",
          f"price_r_to={RENT_CAP}", "limit=100"]
    url = "https://www.fudousan.or.jp/property/rent/13/station/list?" + "&".join(q)
    page = fetch(url)

    if "件見つかりました" not in page and "【マンション】" not in page:
        raise RuntimeError("不動産ジャパン: 結果ページの形が変わった可能性")

    out = []
    for raw in re.split(r"(?=【(?:マンション|アパート)】)", page)[1:]:
        blk = flatten(raw)
        pno = re.search(r"p_no=(\d+)", raw)
        if not pno:
            continue
        detail_url = f"https://www.fudousan.or.jp/property/detail?p_no={pno.group(1)}"
        try:
            det = flatten(fetch(detail_url, timeout=60))
        except RuntimeError:
            continue
        time.sleep(0.6)

        kouzou = field(det, "建物構造", 12)
        if kouzou not in ("ＲＣ", "ＳＲＣ", "RC", "SRC"):
            continue
        age = age_years(field(det, "築年月", 20))
        if age is None or age > AGE_MAX:
            continue
        setsubi = field(det, "設備", 400)
        if "バス・トイレ別" not in setsubi:
            continue
        if "洗面所独立" not in setsubi and "洗面所" not in setsubi:
            continue

        rent = to_yen(field(det, "賃料", 24))
        kanri = to_yen(field(det, "管理費", 24)) or 0
        area_m = re.search(r"専有面積[|\s：:]*([\d.]+)㎡", det)
        stations = [(s.strip(), int(w)) for _l, s, w in
                    re.findall(r"([^|]{2,24}?線)\s*「([^」]+)」駅?\s*徒歩(\d+)分", det)]
        hit = [(s, w) for s, w in stations if s in TARGET_STATIONS and w <= WALK_MAX]
        if not hit:
            continue

        out.append({
            "id": f"fdj:{pno.group(1)}",
            "source": "不動産ジャパン",
            "rent": rent,
            "kanri": kanri,
            "total": (rent or 0) + kanri,
            "area": float(area_m.group(1)) if area_m else None,
            "madori": field(det, "間取り", 10),
            "built": field(det, "築年月", 20),
            "age": round(age, 1),
            "kouzou": kouzou,
            "stations": hit,
            "addr": field(det, "所在地", 40),
            "taiyou": field(det, "取引態様", 14),
            "koushin": field(det, "更新日", 16),
            "setsubi": setsubi[:200],
            "url": detail_url,
        })
    return out


# --------------------------------------------------------------------------
# ハトマークサイト
# --------------------------------------------------------------------------
def hatomark():
    q = [f"m_adr%5B%5D={w}" for w in HATO_WARDS]
    q += ["home_category%5B%5D=mansion"]
    q += [f"floor_plan%5B%5D={f}" for f in FLOOR_PLANS + ["4XXSLDK"]]
    q += [f"eki_walk={WALK_MAX}", "bath%5B%5D=BATH01", "wash%5B%5D=WASH04",
          f"built_to={AGE_MAX}", f"building_area_all_from={int(AREA_MIN)}",
          f"price_r_to={RENT_CAP}", "limit=100"]
    base = ("https://www.hatomarksite.com/search/zentaku/rent/home/area/13/list?"
            + "&".join(q))

    out, seen_keys, sane = [], set(), False
    for page_no in range(1, 5):
        url = base + (f"&page={page_no}" if page_no > 1 else "")
        page = fetch(url, timeout=120)
        if "検索結果" in page:
            sane = True
        cards = re.split(r'(?=<div class="search-result-box detail-link")', page)[1:]
        if not cards:
            break
        for raw in cards:
            blk = flatten(raw)
            stations = [(s.strip(), int(w)) for _l, s, w in
                        re.findall(r"\|([^|]{0,18}?線)([^|]{1,14}?)駅 徒歩(\d+)分", blk)]
            hit = [(s, w) for s, w in stations if s in TARGET_STATIONS and w <= WALK_MAX]
            if not hit:
                continue
            addr = re.search(r"(東京都[^|]{4,32})\|MAP", blk)
            rent_m = re.search(r"賃料[|\s]*([\d.]+)万円", blk)
            area_m = re.search(r"専有面積[|\s]*([\d.]+)㎡", blk)
            built_m = re.search(r"築年月[|\s]*(\d{4})\[[^\]]*\]年(\d{1,2})月", blk) \
                or re.search(r"築年月[|\s]*(\d{4})年(\d{1,2})月", blk)
            if not (rent_m and area_m):
                continue
            names = [c.strip() for c in re.findall(r"\|([^|]{2,40}?)\|", blk[:600])
                     if c.strip() not in ("マンション", "アパート")
                     and "画像" not in c and "閲覧" not in c and "東京都" not in c]
            rent = int(float(rent_m.group(1)) * 10000)
            kanri = to_yen(field(blk, "管理費等", 14)) or 0
            name = names[0] if names else ""
            key = (addr.group(1) if addr else "", name, rent, area_m.group(1))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            built = f"{built_m.group(1)}年{int(built_m.group(2))}月" if built_m else ""
            out.append({
                "id": "hato:" + re.sub(r"\W+", "", "".join(str(x) for x in key))[:60],
                "source": "ハトマークサイト",
                "rent": rent,
                "kanri": kanri,
                "total": rent + kanri,
                "area": float(area_m.group(1)),
                "madori": "",
                "built": built,
                "age": round(age_years(built), 1) if built else None,
                "kouzou": "マンション(RC近似)",
                "stations": hit,
                "addr": (addr.group(1) if addr else "") + " " + name,
                "taiyou": "",
                "koushin": "",
                "setsubi": "バス・トイレ別/洗面所独立(検索条件)",
                "url": base,
            })
        time.sleep(2)
    if not sane:
        raise RuntimeError("ハトマーク: 結果ページの形が変わった可能性")
    return out


# --------------------------------------------------------------------------
def render(item):
    st = " / ".join(f"{s}歩{w}分" for s, w in item["stations"])
    rent = f"{item['rent']:,}円" if item["rent"] else "要問合せ"
    total = f"{item['total']:,}円" if item["total"] else "-"
    over = "  ⚠[管理費込みで17万超]" if item["total"] and item["total"] > RENT_CAP else ""
    lines = [
        f"### {item['addr'] or '(名称なし)'}",
        f"- **賃料 {rent}**（管理費 {item['kanri']:,}円 / 込み {total}）{over}",
        f"- {item['madori'] or '1LDK以上'} / {item['area']}㎡ / 築{item['built']}"
        f"（{item['age']}年）/ {item['kouzou']}",
        f"- 駅: {st}",
    ]
    if item["taiyou"]:
        lines.append(f"- 取引態様: {item['taiyou']} / 更新: {item['koushin']}")
    lines.append(f"- {item['url']}")
    lines.append(f"- 出典: {item['source']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    seen = {}
    if os.path.exists(SEEN_PATH):
        with open(SEEN_PATH, encoding="utf-8") as fh:
            seen = json.load(fh)

    hits, errors = [], []
    for name, fn in (("不動産ジャパン", fudousan_japan), ("ハトマークサイト", hatomark)):
        try:
            got = fn()
            hits.extend(got)
            print(f"[ok] {name}: {len(got)}件", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - どの失敗も健全性エラーとして扱う
            errors.append(f"{name}: {exc}")
            print(f"[NG] {name}: {exc}", file=sys.stderr)

    if errors and not hits:
        print("## ⚠ 監視エラー（取得できなかった）\n")
        for e in errors:
            print(f"- {e}")
        print("\nサイト構造が変わったか、ネットワークが遮断されている可能性がある。"
              "「新着ゼロ」と混同しないこと。")
        return 2

    new = [h for h in hits if h["id"] not in seen]
    show = hits if args.all else new
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")

    if show:
        head = "全ヒット" if args.all else "🔔 新着"
        print(f"## {head} {len(show)}件 ({stamp})\n")
        for item in sorted(show, key=lambda x: x["total"] or 0):
            print(render(item))
            print()
    else:
        print(f"## 新着なし ({stamp}) — 監視中の全ヒット {len(hits)}件")

    if errors:
        print("\n### ⚠ 一部ソースで取得失敗")
        for e in errors:
            print(f"- {e}")

    if not args.dry_run:
        for h in hits:
            seen[h["id"]] = {"first_seen": seen.get(h["id"], {}).get("first_seen", stamp),
                             "addr": h["addr"], "rent": h["rent"], "area": h["area"]}
        with open(SEEN_PATH, "w", encoding="utf-8") as fh:
            json.dump(seen, fh, ensure_ascii=False, indent=1, sort_keys=True)

    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
