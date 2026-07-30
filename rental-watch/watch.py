#!/usr/bin/env python3
"""賃貸物件 監視スクリプト

不動産ジャパン / ハトマークサイト / at home を確定条件で叩き、
seen.json に無い物件だけを報告する。
SUUMO / LIFULL HOME'S / カナリー は対象外（本人が自分で見ているため）。

物件はサイトを跨いで同一判定（fingerprint）するので、
「同じ部屋がどのサイトに何時間早く出たか」が seen.json に蓄積される。
--speed でその集計を出せる。

使い方:
    python3 rental-watch/watch.py            # 差分を報告し seen.json / runlog.md を更新
    python3 rental-watch/watch.py --dry-run  # 何も書かない
    python3 rental-watch/watch.py --all      # 既知も含めて全ヒットを表示
    python3 rental-watch/watch.py --speed    # 掲載速度の集計だけ出す（取得しない）

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
import unicodedata
import urllib.request
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN_PATH = os.path.join(HERE, "seen.json")
RUNLOG_PATH = os.path.join(HERE, "runlog.md")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# ---- 確定条件 (conditions.md と対応) -------------------------------------
RENT_CAP = 170000            # 家賃の上限（円）
RENT_CAP_INCLUSIVE = True    # True = 管理費・共益費込みで上限を判定する（本人確定 2026-07-29）
AREA_MIN = 40.0              # 専有面積 下限（㎡）
AGE_MAX = 25                 # 築年数 上限（年）
WALK_MAX = 15                # 駅徒歩 上限（分）

# 中核8駅（本人が最初に指定した「田町ー目黒／品川ー大森」の範囲）
CORE_STATIONS = {"田町", "高輪ゲートウェイ", "品川", "大崎",
                 "五反田", "目黒", "大井町", "大森"}
# 周辺駅。通勤MUST（秋葉原40分以内・二子玉川50分以内・いずれも乗換1回以内）を
# 実測で満たしたものだけを入れている。石川台・洗足・自由が丘などは秋葉原41分以上で不採用。
NEAR_STATIONS = {"大岡山", "北千束", "荏原町", "中延", "戸越公園", "戸越銀座", "旗の台",
                 "長原", "洗足池", "荏原中延", "武蔵小山", "西小山", "不動前",
                 "池上", "蓮沼", "戸越", "白金台", "高輪台", "三田", "泉岳寺"}
TARGET_STATIONS = CORE_STATIONS | NEAR_STATIONS

FDJ_STATION_CODES = [
    # 中核8駅
    "C8MR8BDBN", "C8MR8BD5N", "C8MR8B5BD", "C8MR8BRBI",
    "C8MR8BSB9", "C8MR8BXB4", "C8MX58RBI", "C8MX58SB9",
    # 周辺20駅
    "Y8W8WBSB9", "Y8W8WBRBI", "Y8W8WBDBN", "Y8W8WBPB3", "Y8W8WBWBY",
    "Y8W8DBWBY", "Y8W8WB5BD", "Y8W8DB5BD", "Y8W8DBRBI", "Y8W8DBPB3",
    "Y8W8R8WBY", "Y8W8R8PB3", "Y8W8R88BS", "Y8W8DMWBY", "Y8W8DMPB3",
    "Y8WDMMRBI", "Y8WPXBMBC", "Y8WDMMDBN", "Y8WDMMWBY", "Y8WWMBMBC",
]
HATO_WARDS = ["13109", "13111", "13110", "13103"]
# at home だけは駅ごとに1リクエスト必要で、叩きすぎるとボット判定（「認証中」ページ）に入る。
# 実測で8駅・間隔3秒までは通ることを確認しているので、ここは中核8駅に据え置く。
# 不動産ジャパンは全駅を1クエリ、ハトマークは区単位なので、駅を増やしてもリクエストは増えない。
ATHOME_SLUGS = ["tamachi", "takanawagateway", "shinagawa", "osaki",
                "gotanda", "meguro", "oimachi", "omori"]
FLOOR_PLANS = ["1XXSLDK", "2XXXXSK", "2XXXSDK", "2XXSLDK",
               "3XXXXSK", "3XXXSDK", "3XXSLDK", "4XXXXSK", "4XXXSDK"]

JST = timezone(timedelta(hours=9))

# 致命的ではないが報告すべき事象（部分ブロック等）をソースから積む
WARNINGS = []


def now_jst():
    return datetime.now(JST)


def stamp():
    return now_jst().strftime("%Y-%m-%d %H:%M JST")


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
    n = now_jst()
    y, mo = int(m.group(1)), int(m.group(2)) if m.group(2) else 1
    return (n.year - y) + (n.month - mo) / 12.0


def norm_addr(s):
    """サイト間で表記が揺れる住所を突き合わせ用に正規化する。"""
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"^東京都", "", s)
    s = re.sub(r"[\s　\-－ー–—]", "", s)
    s = re.sub(r"(丁目|番地|番|号).*$", r"\1", s)
    return s


def fingerprint(item):
    """サイトを跨いで同一物件を同定するキー。

    住所（正規化）＋専有面積＋賃料。住所が取れないソースは駅＋徒歩で代替する。
    """
    a = norm_addr(item.get("addr_key", ""))
    if not a and item.get("stations"):
        st, w = item["stations"][0]
        a = f"{st}{w}"
    area = round(item["area"], 1) if item.get("area") else 0
    return f"{item.get('rent') or 0}|{area}|{a}"


def madori_ok(m):
    m = unicodedata.normalize("NFKC", m or "").upper()
    return bool(re.search(r"[1-5]S?LDK|[2-5]S?[DL]?K", m))


def within_budget(item):
    """家賃上限の判定。

    RENT_CAP_INCLUSIVE=True なら管理費・共益費込みで見る。
    各サイトへのクエリは賃料（管理費抜き）で投げているが、管理費は必ず0以上なので
    「賃料 <= 上限」は「込み <= 上限」の上位集合になる。取りこぼしはない。
    """
    value = item.get("total") if RENT_CAP_INCLUSIVE else item.get("rent")
    if not value:
        return True  # 賃料が「要問合せ」のものは落とさず人に判断させる
    return value <= RENT_CAP


# --------------------------------------------------------------------------
# ソース1: 不動産ジャパン（駅指定・築年は詳細ページで判定）
# --------------------------------------------------------------------------
def fudousan_japan():
    q = ["ptm%5B%5D=0303"]
    q += [f"wst%5B%5D={c}" for c in FDJ_STATION_CODES]
    q += [f"floor_plan%5B%5D={f}" for f in FLOOR_PLANS]
    q += [f"eki_walk={WALK_MAX}", "toil%5B%5D=TOIL04", "wsng%5B%5D=WSNG02",
          "wash%5B%5D=WASH13", f"exclusive_area_from={int(AREA_MIN)}",
          f"price_r_to={RENT_CAP}", "limit=100"]
    page = fetch("https://www.fudousan.or.jp/property/rent/13/station/list?" + "&".join(q))
    if "件見つかりました" not in page and "【マンション】" not in page:
        raise RuntimeError("結果ページの目印が消えている（構造変化の疑い）")

    out = []
    for raw in re.split(r"(?=【(?:マンション|アパート)】)", page)[1:]:
        pno = re.search(r"p_no=(\d+)", raw)
        if not pno:
            continue
        url = f"https://www.fudousan.or.jp/property/detail?p_no={pno.group(1)}"
        try:
            det = flatten(fetch(url, timeout=60))
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
        if "バス・トイレ別" not in setsubi or "洗面所" not in setsubi:
            continue
        stations = [(s.strip(), int(w)) for _l, s, w in
                    re.findall(r"([^|]{2,24}?線)\s*「([^」]+)」駅?\s*徒歩(\d+)分", det)]
        hit = [(s, w) for s, w in stations if s in TARGET_STATIONS and w <= WALK_MAX]
        if not hit:
            continue
        area_m = re.search(r"専有面積[|\s：:]*([\d.]+)㎡", det)
        rent = to_yen(field(det, "賃料", 24))
        kanri = to_yen(field(det, "管理費", 24)) or 0
        out.append({
            "source": "不動産ジャパン", "rent": rent, "kanri": kanri,
            "total": (rent or 0) + kanri,
            "area": float(area_m.group(1)) if area_m else None,
            "madori": field(det, "間取り", 10), "built": field(det, "築年月", 20),
            "age": round(age, 1), "kouzou": kouzou, "stations": hit,
            "addr": field(det, "所在地", 40), "addr_key": field(det, "所在地", 40),
            "taiyou": field(det, "取引態様", 14),
            "url": url,
        })
    return out


# --------------------------------------------------------------------------
# ソース2: ハトマークサイト（区指定 → 対象駅で絞る）
# --------------------------------------------------------------------------
def hatomark():
    q = [f"m_adr%5B%5D={w}" for w in HATO_WARDS] + ["home_category%5B%5D=mansion"]
    q += [f"floor_plan%5B%5D={f}" for f in FLOOR_PLANS + ["4XXSLDK"]]
    q += [f"eki_walk={WALK_MAX}", "bath%5B%5D=BATH01", "wash%5B%5D=WASH04",
          f"built_to={AGE_MAX}", f"building_area_all_from={int(AREA_MIN)}",
          f"price_r_to={RENT_CAP}", "limit=100"]
    base = "https://www.hatomarksite.com/search/zentaku/rent/home/area/13/list?" + "&".join(q)

    out, keys, sane = [], set(), False
    for page_no in range(1, 5):
        page = fetch(base + (f"&page={page_no}" if page_no > 1 else ""), timeout=120)
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
            addr = re.search(r"\|(東京都[^|]{4,40}?)\|", blk)
            rent_m = re.search(r"賃料[|\s]*([\d.]+)万円", blk)
            area_m = re.search(r"専有面積[|\s]*([\d.]+)㎡", blk)
            if not (rent_m and area_m):
                continue
            built_m = (re.search(r"築年月[|\s]*(\d{4})\[[^\]]*\]年(\d{1,2})月", blk)
                       or re.search(r"築年月[|\s]*(\d{4})年(\d{1,2})月", blk))
            names = [c.strip() for c in re.findall(r"\|([^|]{2,40}?)\|", blk[:600])
                     if c.strip() not in ("マンション", "アパート")
                     and "画像" not in c and "閲覧" not in c and "東京都" not in c]
            rent = int(float(rent_m.group(1)) * 10000)
            key = (addr.group(1) if addr else "", names[0] if names else "", rent, area_m.group(1))
            if key in keys:
                continue
            keys.add(key)
            built = f"{built_m.group(1)}年{int(built_m.group(2))}月" if built_m else ""
            out.append({
                "source": "ハトマークサイト", "rent": rent,
                "kanri": to_yen(field(blk, "管理費等", 14)) or 0,
                "total": rent + (to_yen(field(blk, "管理費等", 14)) or 0),
                "area": float(area_m.group(1)), "madori": "", "built": built,
                "age": round(age_years(built), 1) if built else None,
                "kouzou": "マンション(RC近似)", "stations": hit,
                "addr": ((addr.group(1) if addr else "") + " "
                         + (names[0] if names else "")).strip(),
                "addr_key": addr.group(1) if addr else "",
                "taiyou": "", "url": base,
            })
        time.sleep(2)
    if not sane:
        raise RuntimeError("結果ページの目印が消えている（構造変化の疑い）")
    return out


# --------------------------------------------------------------------------
# ソース3: at home（駅ページ。絞り込みはJS依存なので条件はこちらで当てる）
# --------------------------------------------------------------------------
def athome():
    out, sane, blocked = [], False, []
    for slug in ATHOME_SLUGS:
        url = f"https://www.athome.co.jp/chintai/tokyo/{slug}-st/list/"
        try:
            page = fetch(url, timeout=90)
        except RuntimeError:
            continue
        # at home はボット判定に入ると HTTP 200 のまま「認証中」ページを返す。
        # ここを素通りさせると「ブロックされた」が「0件」に化けて静かに壊れる。
        if "認証中" in page[:4000] or "お探しのページが見つかりません" in page[:4000]:
            blocked.append(slug)
            time.sleep(5)
            continue
        if "駅の賃貸物件" in page:
            sane = True
        blocks = re.split(r'(?=<[^>]*class="p-property p-property--building js-block")', page)[1:]
        for raw in blocks:
            blk = flatten(raw)
            head = blk[:900]
            name_m = re.search(r"\|([^|]{2,40}?)\s*\d+階建\|", head)
            addr_m = re.search(r"\|([^|]*?[区市][^|]{1,20}?[０-９0-9一二三四五六七八九十]+丁目)\|", head)
            st_m = re.findall(r"「([^」]+)」駅\s*徒歩(\d+)分", head)
            built_m = re.search(r"\|(\d{4})年\s*(\d{1,2})月\s*\(築", head)
            hit = [(s, int(w)) for s, w in st_m if s in TARGET_STATIONS and int(w) <= WALK_MAX]
            if not hit or not built_m:
                continue
            built = f"{built_m.group(1)}年{int(built_m.group(2))}月"
            age = age_years(built)
            if age is None or age > AGE_MAX:
                continue
            bt_sep = "バス・トイレ別" in blk
            for rent_s, kanri_s, mad, area_s in re.findall(
                    r"\|([\d.]+)\|万円[^|]*\|([\d,]*)円\|(?:[^|]*\|){0,10}?"
                    r"\s*([0-9A-Za-zＬＤＫSＫ]{1,8})\s*\|[\s|]*([\d.]+)m", blk):
                area = float(area_s)
                rent = int(float(rent_s) * 10000)
                kanri = int(kanri_s.replace(",", "")) if kanri_s else 0
                if area < AREA_MIN or rent > RENT_CAP or not madori_ok(mad):
                    continue
                if not bt_sep:
                    continue
                out.append({
                    "source": "at home", "rent": rent, "kanri": kanri,
                    "total": rent + kanri, "area": area, "madori": mad,
                    "built": built, "age": round(age, 1),
                    "kouzou": "未確認(一覧に構造なし)", "stations": hit,
                    "addr": ((addr_m.group(1) if addr_m else "") + " "
                             + (name_m.group(1) if name_m else "")).strip(),
                    "addr_key": addr_m.group(1) if addr_m else "",
                    "taiyou": "", "url": url,
                })
        time.sleep(3)
    if blocked and len(blocked) == len(ATHOME_SLUGS):
        raise RuntimeError("全駅がボット判定でブロックされた（認証中ページ）")
    if blocked:
        WARNINGS.append(
            f"at home: {len(blocked)}駅がボット判定でブロック（{'/'.join(blocked)}）。"
            f"残り{len(ATHOME_SLUGS)-len(blocked)}駅の結果のみ反映")
    if not sane:
        raise RuntimeError("結果ページの目印が消えている（構造変化の疑い）")
    return out


# --------------------------------------------------------------------------
def render(item):
    st = " / ".join(f"{s}歩{w}分" for s, w in item["stations"])
    rent = f"{item['rent']:,}円" if item["rent"] else "要問合せ"
    over = "" if RENT_CAP_INCLUSIVE else (
        "  ⚠[管理費込みで上限超]" if item["total"] and item["total"] > RENT_CAP else "")
    lines = [
        f"### {item['addr'].strip() or '(名称なし)'}",
        f"- **賃料 {rent}**（管理費 {item['kanri']:,}円 / 込み {item['total']:,}円）{over}",
        f"- {item['madori'] or '1LDK以上'} / {item['area']}㎡ / 築{item['built']}"
        f"（{item['age']}年）/ {item['kouzou']}",
        f"- 駅: {st}",
    ]
    if item.get("taiyou"):
        lines.append(f"- 取引態様: {item['taiyou']}")
    srcs = item.get("also_on") or [item["source"]]
    lines += [f"- {item['url']}",
              f"- 掲載: {' / '.join(dict.fromkeys(srcs))}"]
    return "\n".join(lines)


def speed_report(seen):
    """複数ソースで観測できた物件から、掲載の先行時間を集計する。"""
    rows = []
    for fp, rec in seen.items():
        src = rec.get("sources", {})
        if len(src) < 2:
            continue
        parsed = []
        for name, ts in src.items():
            try:
                parsed.append((name, datetime.strptime(ts, "%Y-%m-%d %H:%M JST")))
            except ValueError:
                pass
        if len(parsed) < 2:
            continue
        parsed.sort(key=lambda x: x[1])
        lead = (parsed[-1][1] - parsed[0][1]).total_seconds() / 3600.0
        rows.append((parsed[0][0], parsed[-1][0], lead, rec.get("addr", "")))
    print(f"## 掲載速度の実測 — 複数ソースで観測できた物件 {len(rows)}件\n")
    if not rows:
        print("まだ比較できる物件がない。同じ部屋が2サイト以上に出るまで蓄積が要る。")
        return
    wins = {}
    for first, _last, lead, addr in rows:
        wins[first] = wins.get(first, 0) + 1
        print(f"- **{first}** が先行 {lead:.1f}時間 — {addr[:40]}")
    print("\n### 先行回数")
    for name, n in sorted(wins.items(), key=lambda x: -x[1]):
        print(f"- {name}: {n}回")


def persist(msg):
    """runlog / seen をリポジトリに残す。

    コンテナは揮発するので、コミットしないと記録が消える。定期実行の
    プロンプト文言に依存させず、スクリプト側で完結させる。
    失敗しても監視自体は成功扱いにする（記録の欠落は致命的ではない）。
    """
    import subprocess
    def run(*a):
        return subprocess.run(a, cwd=os.path.dirname(HERE) or ".",
                              capture_output=True, text=True, timeout=120)
    try:
        run("git", "add", SEEN_PATH, RUNLOG_PATH)
        st = run("git", "diff", "--cached", "--name-only")
        if not st.stdout.strip():
            return "commit不要（差分なし）"
        c = run("git", "-c", "user.name=rental-watch",
                "-c", "user.email=noreply@anthropic.com", "commit", "-m", msg)
        if c.returncode != 0:
            return f"commit失敗: {c.stderr.strip()[:120]}"
        for attempt in range(3):
            p = run("git", "push", "origin", "HEAD")
            if p.returncode == 0:
                return "commit+push 済み"
            time.sleep(2 * (attempt + 1))
        return f"push失敗: {p.stderr.strip()[:120]}"
    except Exception as exc:  # noqa: BLE001 - 記録の失敗で監視を落とさない
        return f"git処理で例外: {exc}"


def append_runlog(line):
    new = not os.path.exists(RUNLOG_PATH)
    with open(RUNLOG_PATH, "a", encoding="utf-8") as fh:
        if new:
            fh.write("# 実行ログ\n\n"
                     "監視が「静かに成功」しているのか「静かに失敗」しているのかを\n"
                     "外から見分けるための記録。3時間おきに1行ずつ増えるのが正常。\n\n")
        fh.write(line + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--speed", action="store_true")
    ap.add_argument("--no-commit", action="store_true",
                    help="記録をリポジトリにコミットしない（ローカル検証用）")
    args = ap.parse_args()

    seen = {}
    if os.path.exists(SEEN_PATH):
        with open(SEEN_PATH, encoding="utf-8") as fh:
            seen = json.load(fh)

    if args.speed:
        speed_report(seen)
        return 0

    hits, errors, counts = [], [], {}
    for name, fn in (("不動産ジャパン", fudousan_japan),
                     ("ハトマークサイト", hatomark),
                     ("at home", athome)):
        try:
            got = fn()
            hits.extend(got)
            counts[name] = len(got)
            print(f"[ok] {name}: {len(got)}件", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - どの失敗も健全性エラーとして扱う
            errors.append(f"{name}: {exc}")
            counts[name] = "NG"
            print(f"[NG] {name}: {exc}", file=sys.stderr)

    ts = stamp()
    summary = " / ".join(f"{k}{v}" for k, v in counts.items())

    # 家賃上限（管理費込み判定）でここで落とす。
    # 各サイトへのクエリは賃料ベースなので、込み超過はこの段で除く。
    dropped = [h for h in hits if not within_budget(h)]
    hits = [h for h in hits if within_budget(h)]
    if dropped:
        print(f"[info] 管理費込みで上限超過のため除外: {len(dropped)}件", file=sys.stderr)

    # 同じ部屋が複数サイトから来たら1件にまとめる。
    # まとめないと同一回の通知で件数が水増しされる（住所が取れている方を残す）。
    merged = {}
    for h in hits:
        fp = fingerprint(h)
        prev = merged.get(fp)
        if prev is None:
            h["also_on"] = [h["source"]]
            merged[fp] = h
        else:
            prev["also_on"].append(h["source"])
            # 構造や住所がはっきりしている方を代表にする
            if prev["kouzou"].startswith(("マンション", "未確認")) and \
                    not h["kouzou"].startswith(("マンション", "未確認")):
                h["also_on"] = prev["also_on"]
                merged[fp] = h
    if len(merged) != len(hits):
        print(f"[info] 複数サイトで重複していた物件を統合: {len(hits)}→{len(merged)}件",
              file=sys.stderr)
    hits = list(merged.values())

    if errors and not hits:
        if not args.dry_run:
            append_runlog(f"- {ts}  **ERROR**  {summary}  — {'; '.join(errors)[:120]}")
            if not args.no_commit:
                print(f"[git] {persist(f'chore(rental-watch): 監視エラー {ts}')}", file=sys.stderr)
        print("## ⚠ 監視エラー（取得できなかった）\n")
        for e in errors:
            print(f"- {e}")
        print("\nサイト構造が変わったか、ネットワークが遮断されている可能性がある。"
              "「新着ゼロ」と混同しないこと。")
        return 2

    new = [h for h in hits if fingerprint(h) not in seen]
    show = hits if args.all else new

    if show:
        print(f"## {'全ヒット' if args.all else '🔔 新着'} {len(show)}件 ({ts})\n")
        for item in sorted(show, key=lambda x: x["total"] or 0):
            print(render(item))
            print()
    else:
        print(f"## 新着なし ({ts}) — 監視中の全ヒット {len(hits)}件")

    if errors or WARNINGS:
        print("\n### ⚠ 取得に問題があった箇所")
        for e in errors:
            print(f"- {e}")
        for e in WARNINGS:
            print(f"- {e}")

    if not args.dry_run:
        for h in hits:
            fp = fingerprint(h)
            rec = seen.setdefault(fp, {"first_seen": ts, "sources": {}})
            rec.setdefault("sources", {}).setdefault(h["source"], ts)
            rec.update({"addr": h["addr"].strip(), "rent": h["rent"], "area": h["area"]})
        with open(SEEN_PATH, "w", encoding="utf-8") as fh:
            json.dump(seen, fh, ensure_ascii=False, indent=1, sort_keys=True)
        mark = "**新着%d**" % len(new) if new else "新着0"
        note = "; ".join(errors + WARNINGS)
        append_runlog(f"- {ts}  ok  {summary}  {mark}"
                      + (f"  ※{note[:110]}" if note else ""))
        if not args.no_commit:
            print(f"[git] {persist(f'chore(rental-watch): 定期監視 {ts} {mark}')}",
                  file=sys.stderr)

    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
