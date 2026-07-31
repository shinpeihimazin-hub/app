#!/usr/bin/env python3
"""賃貸物件 監視スクリプト

SUUMO / 不動産ジャパン / ハトマークサイト / at home / LIFULL HOME'S /
エイブル を確定条件で叩き、seen.json に無い物件だけを報告する。カナリーは未対応。

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

# 初期費用（本人確定 2026-07-30）。仲介手数料は0.55ヶ月で固定して見積もる。
INIT_CAP = 400000            # 初期費用の上限（円）
CHUKAI_MONTHS = 0.55         # 仲介手数料（宅建業法の原則。1.1ヶ月は借主の承諾が要る）
HOSHO_RATIO = 0.5            # 保証会社の初回保証料（賃料比）
MISC_COST = 40000            # 火災保険2万＋鍵交換2万

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

# LIFULL HOME'S の駅スラッグ（駅名 → {slug}_{駅コード}）。
# 路線ページ（例 /chintai/tokyo/yamanote-line/）の
# name="cond[roseneki][...]" と隣接する駅リンクから採取した実測値。
HOMES_STATIONS = {
    "田町": "tamachi_00573", "高輪ゲートウェイ": "takanawagateway_10177",
    "品川": "shinagawa_00224", "大崎": "osaki_00574", "五反田": "gotanda_00575",
    "目黒": "meguro_00576", "大井町": "oimachi_00603", "大森": "omori_00604",
    "大岡山": "ookayama_05072", "北千束": "kitasenzoku_05084",
    "荏原町": "ebaramachi_05082", "中延": "nakanobu_05081",
    "戸越公園": "togoshikoen_05080", "戸越銀座": "togoshiginza_05115",
    "旗の台": "hatanodai_05083", "長原": "nagahara_05117",
    "洗足池": "senzokuike_05118", "荏原中延": "ebaranakanobu_05116",
    "武蔵小山": "musashikoyama_05069", "西小山": "nishikoyama_05070",
    "不動前": "fudomae_05068", "池上": "ikegami_05124", "蓮沼": "hasunuma_05125",
    "戸越": "togoshi_06400", "白金台": "shirokanedai_09216",
    "高輪台": "takanawadai_06401", "三田": "mita_06402", "泉岳寺": "sengakuji_05181",
}
# HOME'S の間取りコード（1LDK以上）と設備コード。
HOMES_MADORI = ["15", "22", "23", "25", "32", "33", "35", "42", "43", "45-"]
HOMES_MCF = ["220301", "223101"]   # バス・トイレ別 / 洗面所独立

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


def html_unescape(x):
    import html as _h
    return _h.unescape(x)


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
    """金額表記を円に直す。

    不動産ジャパンは「14万5,000円」のように万と千を分けて書く。
    万だけを読むと5,000円を取りこぼし、賃料が5千円ずれる。
    賃料は fingerprint のキーにも使うので、ずれると同一物件を別物と誤判定する。
    """
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*万\s*([\d,]+)?\s*円?", s)
    if m:
        v = float(m.group(1).replace(",", "")) * 10000
        if m.group(2):
            v += int(m.group(2).replace(",", ""))
        return int(v)
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
    """サイト間で表記が揺れる住所を突き合わせ用に正規化する。

    丁目の書き方がサイトごとに違う。SUUMOは「目黒本町４」、HOME'Sは
    「目黒本町4丁目」、エイブルは「目黒本町４丁目」と書く。丁目を残すと
    同じ部屋が別物と判定されて毎回二重に通知される（実測で発生した）。
    そこで**最初の数字までで切る**。丁目・番地・号は全部落ちて同じ形になる。

    番地まで違う建物が同じキーになるが、fingerprint は賃料と専有面積も
    含むので実害は出ない。取りこぼす（＝重複通知する）方が損が大きい。
    """
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"^東京都", "", s)
    s = re.sub(r"[\s　\-－ー–—]", "", s)
    m = re.match(r"(.*?\d+)", s)
    return m.group(1) if m else s


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


VALUE_PATTERNS = [r"^[|\s：:]*([\d.,]+\s*万\s*[\d,]*\s*円)",
                  r"^[|\s：:]*([\d,]+\s*円)",
                  r"^[|\s：:]*([\d.]+\s*[ヵヶか]月)",
                  r"^[|\s：:]*(無|なし|礼金なし|敷金なし|不要)"]


def grab_value(text, label):
    """ラベルの各出現を順に見て、最初に値が続いた箇所を返す。

    詳細ページは「敷金| | | | |敷金| |2ヵ月」のように見出しだけの出現が先に来る。
    素直に最初の出現を取ると空文字を掴む。
    """
    for m in re.finditer(re.escape(label), text):
        seg = text[m.end():m.end() + 40]
        for pat in VALUE_PATTERNS:
            hit = re.search(pat, seg)
            if hit:
                return hit.group(1).strip()
    return ""


def deposit_yen(txt, rent):
    """「2ヵ月」「14万円」「無」を円に直す。"""
    if not txt or txt.strip() in ("無", "なし", "礼金なし", "敷金なし", "不要", "-", "―"):
        return 0
    m = re.search(r"([\d.]+)\s*[ヵヶか]月", txt)
    if m:
        return int(float(m.group(1)) * rent)
    return to_yen(txt) or 0


def initial_cost(item):
    """初期費用の見積り。

    敷金 + 礼金 + 仲介(0.55ヶ月) + 前家賃(管理費込) + 保証会社(賃料50%) + 火災保険・鍵交換。

    仲介0.55を固定すると、上限40万に収めるには敷礼がほぼゼロでないと数学的に届かない
    （敷礼合計1ヶ月だと賃料11.8万が上限になり、想定レンジの外に出る）。
    """
    rent = item.get("rent") or 0
    return (item.get("shiki", 0) + item.get("rei", 0)
            + int(rent * CHUKAI_MONTHS) + (item.get("total") or 0)
            + int(rent * HOSHO_RATIO) + MISC_COST)


def within_init_cap(item):
    if item.get("shiki") is None or item.get("rei") is None:
        return True  # 敷礼が読めなかったものは落とさず人に判断させる
    return initial_cost(item) <= INIT_CAP


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
            "shiki": deposit_yen(grab_value(det, "敷金"), rent or 0),
            "rei": deposit_yen(grab_value(det, "礼金"), rent or 0),
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
                "shiki": deposit_yen(grab_value(blk, "敷金"), rent),
                "rei": deposit_yen(grab_value(blk, "礼金"), rent),
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
            # 並びは 賃料|万円|管理費|敷金|礼金|…|間取り|面積
            for rent_s, kanri_s, shiki_s, rei_s, mad, area_s in re.findall(
                    r"\|([\d.]+)\|万円[^|]*\|([\d,]*)円\|"
                    r"[\s|]*([^|]{0,12}?)\|[\s|]*([^|]{0,12}?)\|"
                    r"(?:[^|]*\|){0,4}?\s*([0-9A-Za-zＬＤＫSＫ]{1,8})\s*\|[\s|]*([\d.]+)m", blk):
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
                    "shiki": deposit_yen(shiki_s, rent),
                    "rei": deposit_yen(rei_s, rent),
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
# ソース4: SUUMO（区指定 → 対象駅で絞る）
# --------------------------------------------------------------------------
# 当初は「本人が自分で見ているから」除外していたが、敷礼ゼロ物件の実測が
# SUUMO 26件 / 不動産ジャパン 1件 / ハトマーク 0件 と桁違いだったため追加した。
# 初期費用40万を仲介0.55で満たすには礼金ゼロが事実上の必須条件になるので、
# co=3（礼金なし）をサーバ側で効かせて母数を992件から95件に落としている。
def suumo():
    # co=3（礼金なし）は使わない。敷金ゼロ＋礼金0.5ヶ月のような組み合わせでも
    # 賃料14.1万までなら初期費用40万に収まるため、サーバ側で切ると取りこぼす。
    # 間取りは 1LDK 以上を全部（3LDK/4LDKも条件上は対象）。
    base = ("https://suumo.jp/jj/chintai/ichiran/FR301FC001/?ar=030&bs=040&ta=13"
            "&sc=13109&sc=13111&sc=13110&sc=13103"
            f"&cb=0.0&ct={RENT_CAP/10000:.1f}&co=1"
            "&md=04&md=05&md=06&md=07&md=08&md=09&md=10&md=11&md=12&md=13"
            f"&mb={int(AREA_MIN)}&mt=9999999&cn={AGE_MAX}&et={WALK_MAX}"
            "&ts=1&tc=0400301&tc=0400501&pc=50&page={p}")
    out, sane = [], False
    for page_no in range(1, 25):
        page = fetch(base.format(p=page_no), timeout=90)
        if "cassetteitem" in page or "pagecaption" in page:
            sane = True
        cass = re.findall(
            r'<div class="cassetteitem">(.*?)(?=<div class="cassetteitem">|<div id="js-bukkenList-end")',
            page, re.S)
        if not cass:
            break
        for c in cass:
            nm = re.search(r'cassetteitem_content-title">(.*?)<', c, re.S)
            name = flatten(nm.group(1)).strip(" |") if nm else ""
            ad = re.search(r'cassetteitem_detail-col1">(.*?)</div>', c, re.S)
            addr = flatten(ad.group(1)).strip(" |") if ad else ""
            # col1 には住所に続けて「東急目黒線/武蔵小山駅 歩9分」等が入る。丁目までで切る。
            am = re.match(r"(東京都[^|]*?[０-９0-9一二三四五六七八九十]+丁目)", addr) \
                or re.match(r"(東京都[^|]*?[市区町村][^|]{0,12}?)(?:\||$)", addr)
            addr = am.group(1).strip() if am else addr.split("|")[0].strip()
            mm = re.search(r"築(\d+)年", c)
            age = int(mm.group(1)) if mm else (0 if "新築" in c else None)
            if age is None or age > AGE_MAX:
                continue
            hit = []
            for a in (flatten(x) for x in
                      re.findall(r'cassetteitem_detail-text">(.*?)</div>', c, re.S)):
                m = re.search(r"([^/歩\s|]+?)駅?\s*歩(\d+)分", a)
                if not m:
                    continue
                st = m.group(1).replace("駅", "").strip(" |")
                for t in TARGET_STATIONS:
                    if (st == t or st.endswith(t)) and int(m.group(2)) <= WALK_MAX:
                        hit.append((t, int(m.group(2))))
            if not hit:
                continue
            for tr in re.findall(r'<tr class="js-cassette_link">(.*?)</tr>', c, re.S):
                r = re.search(r'cassetteitem_other-emphasis ui-text--bold">(.*?)<', tr, re.S)
                a2 = re.search(r'cassetteitem_menseki">(.*?)m', tr, re.S)
                if not (r and a2):
                    continue
                k = re.search(r'cassetteitem_price--administration">(.*?)<', tr, re.S)
                d = re.search(r'cassetteitem_price--deposit">(.*?)<', tr, re.S)
                g = re.search(r'cassetteitem_price--gratuity">(.*?)<', tr, re.S)
                md = re.search(r'cassetteitem_madori">(.*?)<', tr, re.S)
                u = re.search(r'href="(/chintai/jnc_\d+/\?bc=\d+)"', tr)
                rent = to_yen(flatten(r.group(1))) or 0
                kanri = (to_yen(flatten(k.group(1))) if k else 0) or 0
                area = float(flatten(a2.group(1)))
                if area < AREA_MIN or rent < 50000:
                    continue
                out.append({
                    "source": "SUUMO", "rent": rent, "kanri": kanri,
                    "total": rent + kanri,
                    "shiki": (to_yen(flatten(d.group(1))) if d else 0) or 0,
                    "rei": (to_yen(flatten(g.group(1))) if g else 0) or 0,
                    "area": area,
                    "madori": flatten(md.group(1)).strip(" |") if md else "",
                    "built": f"{age}年", "age": float(age),
                    "kouzou": "マンション(RC近似)",
                    "stations": sorted(set(hit), key=lambda x: x[1]),
                    "addr": (addr + " " + name).strip(), "addr_key": addr,
                    "taiyou": "",
                    "url": ("https://suumo.jp" + html_unescape(u.group(1))) if u else "",
                })
        time.sleep(1.5)
    if not sane:
        raise RuntimeError("結果ページの目印が消えている（構造変化の疑い）")
    return out

# --------------------------------------------------------------------------
# ソース5: LIFULL HOME'S（駅指定・28駅）
# --------------------------------------------------------------------------
# 当初「ページは200で返るが物件データが描画されない」として未対応にしていたが、
# これは駅スラッグを取り違えて404ページを掴んでいたための誤判定だった。
# 正しいスラッグならHTMLに物件が全部入っている。母数は監視5サイト中で最大。
HOMES_ZERO = "条件に一致する情報は見つかりませんでした"
HOMES_TOTAL = re.compile(r"総物件数：([\d,]+)件")
HOMES_BLOCK = re.compile(
    r'class="[^"]*mod-mergeBuilding[^"]*"(.*?)(?=class="[^"]*mod-mergeBuilding|</body>)', re.S)
HOMES_ROOM = re.compile(
    r'data-href="(?P<url>[^"]+)"[^>]*class="prg-room .*?'
    r'<td class="floar"[^>]*>(?P<floor>.*?)</td>.*?'
    r'<td class="price">(?P<price>.*?)</td>.*?'
    r'<td class="layout"[^>]*>(?P<layout>.*?)</td>', re.S)


def homes_cell(s):
    """HOME'S の td を1行に。改行(<br>)だけを | にし、他のタグは消す。

    共用の flatten() は全タグを | にするので、
    「賃料/管理費<br>敷金/礼金/…」の段組みが区別できなくなる。
    """
    s = re.sub(r"<br\s*/?>", "|", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html_unescape(s)).replace(" ", " ").strip()


def homes_query():
    # URLエンコード済みの %5B/%5D を含むので、%書式ではなくf文字列で組む
    return (f"cond%5Bmonthmoneyroomh%5D={RENT_CAP // 10000}"
            + f"&cond%5Bhousearea%5D={int(AREA_MIN)}"
            + f"&cond%5Bhouseageh%5D={AGE_MAX}"
            + f"&cond%5Bwalkminutesh%5D={WALK_MAX}"
            + "&cond%5Bhousekouzougroup%5D%5Brebar%5D=rebar"   # 鉄筋系＝RC/SRC
            + "".join(f"&cond%5Bmcf%5D%5B{c}%5D={c}" for c in HOMES_MCF)
            + "".join(f"&cond%5Bmadori%5D%5B{m}%5D={m}" for m in HOMES_MADORI)
            + "&cond%5Bsortby%5D=newdate")


def homes_parse(page):
    out = []
    for blk in HOMES_BLOCK.findall(page):
        m = re.search(r"<th>所在地</th>\s*<td>(.*?)</td>", blk, re.S)
        addr = flatten(m.group(1)).strip(" |") if m else ""
        m = re.search(r'class="bukkenName[^"]*">(.*?)</span>', blk, re.S)
        name = flatten(m.group(1)).strip(" |") if m else ""
        m = re.search(r"<th>築年数/階数</th>\s*<td>(.*?)</td>", blk, re.S)
        age = None
        if m:
            t = flatten(m.group(1))
            mm = re.search(r"(\d+)\s*年", t)
            age = 0 if "新築" in t else (int(mm.group(1)) if mm else None)
        hit = []
        for sm in re.finditer(r'class="prg-stationText[^"]*">(.*?)</span>', blk, re.S):
            mm = re.search(r"(\S+?)駅\s*徒歩(\d+)分", flatten(sm.group(1)))
            if mm and mm.group(1) in TARGET_STATIONS and int(mm.group(2)) <= WALK_MAX:
                hit.append((mm.group(1), int(mm.group(2))))
        if not hit:
            continue
        if age is None or age > AGE_MAX:
            continue

        for r in HOMES_ROOM.finditer(blk):
            # price 例: "16.5万円/14,000円|1ヶ月/2ヶ月/-/-"（後半が 敷/礼/保証/敷引）
            parts = homes_cell(r.group("price")).split("|")
            money = parts[0].split("/")
            rent = to_yen(money[0]) or 0
            kanri = (to_yen(money[1]) if len(money) > 1 else 0) or 0
            shiki = rei = None
            if len(parts) > 1:
                dep = parts[1].split("/")
                if len(dep) >= 2:
                    shiki, rei = deposit_yen(dep[0], rent), deposit_yen(dep[1], rent)
            layout = homes_cell(r.group("layout"))
            am = re.search(r"([\d.]+)\s*m", layout)
            area = float(am.group(1)) if am else None
            if not area or area < AREA_MIN or rent < 50000:
                continue
            out.append({
                "source": "HOME'S", "rent": rent, "kanri": kanri, "total": rent + kanri,
                "shiki": shiki if shiki is not None else 0,
                "rei": rei if rei is not None else 0,
                "area": area, "madori": layout.split("|")[0].strip(),
                "built": f"{age}年", "age": float(age),
                "kouzou": "鉄筋系(RC/SRC)",
                "stations": sorted(set(hit), key=lambda x: x[1]),
                "addr": (addr + " " + name).strip(), "addr_key": addr,
                "taiyou": "",
                "url": html_unescape(r.group("url")),
            })
    return out


def homes():
    """28駅を1駅ずつ。「本当に0件」と「取れなかった」を必ず区別する。

    HOME'S は連続アクセスすると、0件マーカーの無い“物件ブロックだけ落ちた”
    通常ページを返してくる。これを0件として扱うと、監視しているつもりで
    静かに何も見ていない状態になるので、待って引き直し、駄目なら失敗にする。
    """
    q, out, blocked = homes_query(), [], []
    for st, slug in HOMES_STATIONS.items():
        page_no, total, tries = 1, None, 0
        while True:
            url = (f"https://www.homes.co.jp/chintai/tokyo/{slug}-st/list/?{q}"
                   + (f"&page={page_no}" if page_no > 1 else ""))
            page = fetch(url, timeout=90)
            if HOMES_ZERO in page and "mod-mergeBuilding--rent" not in page:
                break                                   # この駅は本当に0件
            got = homes_parse(page)
            if not got and "mod-mergeBuilding--rent" not in page:
                tries += 1
                if tries > 3:
                    blocked.append(st)
                    break
                time.sleep(10 * tries)
                continue
            tries = 0
            m = HOMES_TOTAL.search(page)
            if m and total is None:
                total = int(m.group(1).replace(",", ""))
            out.extend(got)
            # 1ページ10件。総物件数に届くまでページを送る。
            if total is None or page_no * 10 >= total or page_no >= 12:
                break
            page_no += 1
            time.sleep(2.5)
        time.sleep(2.5)
    if len(blocked) == len(HOMES_STATIONS):
        raise RuntimeError("全駅で物件ブロックが取れない（規制か構造変化）")
    if blocked:
        WARNINGS.append(f"HOME'S: {len(blocked)}駅で取得できず（{'/'.join(blocked)}）")
    return out


# --------------------------------------------------------------------------
# ソース6: エイブル（区指定 → 対象駅で絞る）
# --------------------------------------------------------------------------
# 一覧に「構造」が出るので RC/SRC を人手確認なしで判定できる（at home にはこれが無い）。
# 家賃上限（ct）だけはサーバ側で効かない（詳細リンクに ct=0 で伝播する）ので、
# 面積・築年・徒歩・間取りだけサーバ側で当てて、家賃と初期費用はこちらで落とす。
ABLE_QUERY = ("sf=%d&h=7&j=5&p=10&" % int(AREA_MIN)   # sf=面積下限 h=7:築25年 j=5:徒歩15分 p=10:100件/頁
              + "&".join(f"m={m}" for m in
                         ["3", "4", "5", "6", "7", "8", "9", "A", "B"]))  # 1LDK以上
ABLE_BLOCK = re.compile(r"js-detailLinkUrl(.*?)(?=js-detailLinkUrl|</body>)", re.S)
ABLE_ROOM = re.compile(
    r'<td class="floar[^"]*">(?P<floor>.*?)</td>\s*'
    r'<td class="price[^"]*">(?P<price>.*?)</td>\s*'
    r'<td class="price[^"]*">(?P<dep>.*?)</td>\s*'
    r'<td class="layout[^"]*">(?P<layout>.*?)</td>', re.S)


def able_cell(s):
    """エイブルの td を1行に。HOME'S と同じく <br> だけを | にする。"""
    s = re.sub(r"<br\s*/?>", "|", s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html_unescape(s)).replace(" ", " ").strip()


def able_parse(page):
    out = []
    for blk in ABLE_BLOCK.findall(page):
        m = re.search(r'data-bkKey="(\d+)"', blk)
        bk = m.group(1) if m else ""
        # ブロックの分割目印が "js-detailLinkUrl" なので、建物名のアンカーは
        # ブロック先頭（class属性の途中）から始まる。先頭の > の後ろを名前として拾う。
        m = re.match(r'[^>]*>\s*(.*?)\s*</a>', blk, re.S)
        name = able_cell(m.group(1)) if m else ""
        m = re.search(r'<th>住所</th>\s*<td>(.*?)<p class="map"', blk, re.S)
        addr = able_cell(m.group(1)) if m else ""
        m = re.search(r"<th>構造</th>\s*<td>(.*?)</td>", blk, re.S)
        kouzou = able_cell(m.group(1)) if m else ""
        m = re.search(r"<th>築年</th>\s*<td>(.*?)</td>", blk, re.S)
        built = able_cell(m.group(1)) if m else ""
        age = age_years(built)
        if age is None or age > AGE_MAX:
            continue
        if "鉄筋" not in kouzou:          # RC/SRC 以外は落とす（構造が一覧に出る強み）
            continue
        hit = []
        for li in re.findall(r"<li>([^<]*?徒歩\d+分)</li>", blk):
            mm = re.search(r"/?([^/]+?)駅\s*徒歩(\d+)分", able_cell(li))
            if mm and mm.group(1) in TARGET_STATIONS and int(mm.group(2)) <= WALK_MAX:
                hit.append((mm.group(1), int(mm.group(2))))
        if not hit:
            continue
        for r in ABLE_ROOM.finditer(blk):
            price = able_cell(r.group("price")).split("|")
            dep = able_cell(r.group("dep")).split("|")
            layout = able_cell(r.group("layout")).split("|")
            rent = to_yen(price[0]) or 0
            am = re.search(r"([\d.]+)\s*㎡", " ".join(layout))
            area = float(am.group(1)) if am else None
            if not area or area < AREA_MIN or rent < 50000:
                continue
            kanri = (to_yen(price[1]) if len(price) > 1 else 0) or 0
            out.append({
                "source": "エイブル", "rent": rent, "kanri": kanri, "total": rent + kanri,
                "shiki": deposit_yen(dep[0] if dep else "", rent),
                "rei": deposit_yen(dep[1] if len(dep) > 1 else "", rent),
                "area": area, "madori": layout[0] if layout else "",
                "built": built, "age": round(age, 1), "kouzou": kouzou,
                "stations": sorted(set(hit), key=lambda x: x[1]),
                "addr": (addr + " " + name).strip(), "addr_key": addr,
                "taiyou": "",
                "url": f"https://www.able.co.jp/detail/Detail.do?bk={bk}",
            })
    return out


def able():
    out, sane = [], False
    for ward in HATO_WARDS:
        i = 1
        while True:
            url = f"https://www.able.co.jp/tokyo/area/{ward}/list/?{ABLE_QUERY}"
            if i > 1:
                url += f"&i={i}"
            page = fetch(url, timeout=90)
            if "js-detailLinkUrl" in page or "条件を保存" in page:
                sane = True
            items = able_parse(page)
            blocks = len(ABLE_BLOCK.findall(page))
            out.extend(items)
            if blocks < 100 or i >= 12:
                break
            i += 1
            time.sleep(2)
        time.sleep(2)
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
        f"- 敷{item.get('shiki', 0):,}円 / 礼{item.get('rei', 0):,}円 → "
        f"**初期費用 約{initial_cost(item):,}円**（仲介{CHUKAI_MONTHS}ヶ月・保証会社50%・諸費用4万で試算）",
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
                     ("at home", athome),
                     ("SUUMO", suumo),
                     ("HOME'S", homes),
                     ("エイブル", able)):
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

    over = [h for h in hits if not within_init_cap(h)]
    hits = [h for h in hits if within_init_cap(h)]
    if over:
        print(f"[info] 初期費用{INIT_CAP:,}円超のため除外: {len(over)}件"
              f"（仲介{CHUKAI_MONTHS}ヶ月で計算）", file=sys.stderr)

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
