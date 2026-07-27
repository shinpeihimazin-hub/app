#!/usr/bin/env python3
"""conditions.yaml の凍結前検算エンジン（S2b）。

条件のスキーマ（項目IDと重要度◎○△）は references/condition-taxonomy.md から
読み込む。タクソノミが単一の情報源であり、このスクリプトに項目表を二重管理しない。

使い方:
    python3 validate_conditions.py --init > conditions.yaml   # 空の雛形を出力
    python3 validate_conditions.py conditions.yaml            # 検算
    python3 validate_conditions.py conditions.yaml --json     # 機械可読出力

終了コード:
    0  凍結可（BLOCK なし。WARN は残っていてもよい）
    1  凍結不可（BLOCK あり）
    2  入力エラー
"""

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import yaml

TAXONOMY = Path(__file__).resolve().parent.parent / "references" / "condition-taxonomy.md"

# 初期費用の内訳（家賃に対する月数、または固定円）。実額は物件ごとに異なるため概算。
FIRE_INSURANCE_YEN = 20000      # 火災保険 2年分の目安
KEY_EXCHANGE_YEN = 20000        # 鍵交換の目安
GUARANTEE_RATE = 0.5            # 保証会社 初回（家賃比）
AGENT_FEE_DEFAULT = 1.1         # 仲介手数料 1ヶ月＋税（宅建業法の上限）
ADVANCE_RENT_MONTHS = 1.0       # 前家賃
MUST_LIMIT = 8                  # MUST の上限（超えたら警告）
EXCHANGE_RATE_MIN = 5           # 交換レートを必須とする WANT の上位件数
DEFAULT_STAY_MONTHS = 48        # 想定居住月数の既定値
LPG_MONTHLY_PREMIUM = 3500      # プロパンガスの月額上振れ目安

ROW_RE = re.compile(r"^\|\s*`([A-Z]{3}_[a-z0-9_]+)`\s*\|\s*([^|]+?)\s*\|\s*([◎○△])\s*\|")

# タクソノミ上は項目として並ぶが、YAMLではトップレベルのキーではなく
# 各項目の rank / weight フィールドとして表現されるもの。
# 存在チェックの対象から外し、check_ranks() 側で検証する。
FIELD_LEVEL_IDS = {"PRI_rank", "PRI_weight"}


def load_taxonomy(path=TAXONOMY):
    """タクソノミMarkdownから {id: {"label":…, "importance": "◎"|"○"|"△"}} を作る。"""
    if not path.exists():
        sys.exit(f"[FATAL] タクソノミが見つかりません: {path}")
    schema = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line)
        if m:
            schema[m.group(1)] = {"label": m.group(2).strip(), "importance": m.group(3)}
    if not schema:
        sys.exit(f"[FATAL] タクソノミから項目を抽出できませんでした: {path}")
    return schema


def emit_skeleton(schema):
    """全項目を unknown: true で埋めた雛形YAMLを出力する。"""
    out = [
        "# 賃貸条件シート（S1で埋める）",
        "# unknown: true が1つでも◎項目に残る限り、S3の凍結ゲートは通らない。",
        "# 「こだわらない」は unknown: false + rank: 不問 で表現する（未記入とは別物）。",
        "",
        f"_meta:",
        f"  stay_months: {DEFAULT_STAY_MONTHS}   # 想定居住月数（未確定なら既定値のまま）",
        "  stay_months_assumed: true",
        "",
    ]
    for cid, meta in schema.items():
        if cid.startswith("PRI_"):
            continue
        out += [
            f"{cid}:                 # {meta['importance']} {meta['label']}",
            "  value: null",
            "  unknown: true",
            "  rank: null            # MUST / WANT / NICE / 不問",
            "  weight: null          # WANT のときのみ 1-10",
            "  note: \"\"",
            "",
        ]
    out += [
        "PRI_exchange_rate:      # ◎ 交換レート {項目ID: 円/月}",
        "  value: {}",
        "  unknown: true",
        "",
        "PRI_top3:               # ◎ 絶対に譲れない上位3つ（項目IDを3つ）",
        "  value: []",
        "  unknown: true",
        "",
        "PRI_dealbreaker:        # ◎ 一発除外の条件（自由記述）",
        "  value: []",
        "  unknown: true",
        "",
    ]
    return "\n".join(out)


def get(data, cid):
    node = data.get(cid)
    return node if isinstance(node, dict) else {}


def val(data, cid, default=None):
    node = get(data, cid)
    if node.get("unknown") is True:
        return default
    v = node.get("value")
    return default if v is None else v


def num(data, cid, default=None):
    v = val(data, cid, None)
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        digits = re.sub(r"[^\d.]", "", v)
        if digits:
            try:
                return float(digits)
            except ValueError:
                pass
    return default


def is_unknown(data, cid):
    node = get(data, cid)
    return not node or node.get("unknown") is True


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, code, message, detail=None):
        self.items.append(
            {"level": level, "code": code, "message": message, "detail": detail or {}}
        )

    block = lambda self, *a, **k: self.add("BLOCK", *a, **k)   # noqa: E731
    warn = lambda self, *a, **k: self.add("WARN", *a, **k)     # noqa: E731
    info = lambda self, *a, **k: self.add("INFO", *a, **k)     # noqa: E731

    def has(self, level):
        return any(i["level"] == level for i in self.items)


# --------------------------------------------------------------------------
# 完全性チェック（BLOCK）
# --------------------------------------------------------------------------

def check_completeness(data, schema, rep):
    missing = [
        cid for cid, m in schema.items()
        if m["importance"] == "◎" and cid not in FIELD_LEVEL_IDS and is_unknown(data, cid)
    ]
    if missing:
        rep.block(
            "B1_REQUIRED_UNKNOWN",
            f"必須(◎)項目に未記入が {len(missing)} 件あります。凍結できません。",
            {"items": [{"id": c, "label": schema[c]["label"]} for c in missing]},
        )

    assumed = [
        cid for cid, m in schema.items()
        if m["importance"] == "○" and cid not in FIELD_LEVEL_IDS and is_unknown(data, cid)
    ]
    if assumed:
        rep.warn(
            "W0_RECOMMENDED_UNKNOWN",
            f"推奨(○)項目に未記入が {len(assumed)} 件あります。仮定を置く場合はユーザーに明示してください。",
            {"items": [{"id": c, "label": schema[c]["label"]} for c in assumed]},
        )


def check_ranks(data, schema, rep):
    valid = {"MUST", "WANT", "NICE", "不問"}
    no_rank, bad_weight = [], []
    for cid, m in schema.items():
        if cid.startswith("PRI_") or is_unknown(data, cid):
            continue
        rank = get(data, cid).get("rank")
        if rank not in valid:
            no_rank.append(cid)
            continue
        if rank == "WANT":
            w = get(data, cid).get("weight")
            if not isinstance(w, (int, float)) or not (1 <= w <= 10):
                bad_weight.append(cid)
    if no_rank:
        rep.block(
            "B2_NO_RANK",
            f"rank(MUST/WANT/NICE/不問) が未設定の項目が {len(no_rank)} 件あります。",
            {"items": no_rank},
        )
    if bad_weight:
        rep.block(
            "B3_WANT_NO_WEIGHT",
            f"WANT なのに weight(1-10) が無い項目が {len(bad_weight)} 件あります。",
            {"items": bad_weight},
        )


def wants_by_weight(data, schema):
    rows = []
    for cid in schema:
        if cid.startswith("PRI_") or is_unknown(data, cid):
            continue
        if get(data, cid).get("rank") == "WANT":
            w = get(data, cid).get("weight")
            rows.append((cid, w if isinstance(w, (int, float)) else 0))
    return [c for c, _ in sorted(rows, key=lambda r: -r[1])]


def check_exchange_rates(data, schema, rep):
    wants = wants_by_weight(data, schema)
    if not wants:
        return
    rates = val(data, "PRI_exchange_rate", {}) or {}
    if not isinstance(rates, dict):
        rep.block("B4_RATE_TYPE", "PRI_exchange_rate は {項目ID: 円} の辞書である必要があります。")
        return
    need = wants[:EXCHANGE_RATE_MIN]
    lacking = [c for c in need if not isinstance(rates.get(c), (int, float))]
    if lacking:
        rep.block(
            "B4_NO_EXCHANGE_RATE",
            f"上位WANT {len(need)} 件のうち {len(lacking)} 件に交換レートがありません。"
            "ラダー法（scoring.md）で金額を確定してください。",
            {"items": [{"id": c, "label": schema[c]["label"]} for c in lacking]},
        )
    unknown_ids = [c for c in rates if c not in schema]
    if unknown_ids:
        rep.warn("W9_RATE_UNKNOWN_ID", "交換レートに未知の項目IDがあります。", {"items": unknown_ids})


# --------------------------------------------------------------------------
# 現実性の検算（WARN）
# --------------------------------------------------------------------------

def estimate_initial_cost(data):
    """初期費用の概算と内訳を返す。家賃が不明なら None。"""
    rent = num(data, "BUD_rent_max")
    if not rent:
        return None
    dep = num(data, "BUD_deposit_ok", 1.0)
    key = num(data, "BUD_keymoney_ok", 1.0)
    agent = num(data, "BUD_agent_fee_ok", AGENT_FEE_DEFAULT)
    guarantee = GUARANTEE_RATE if val(data, "CTR_guarantee_co", "可") != "不可" else 0.0
    breakdown = {
        "敷金": rent * dep,
        "礼金": rent * key,
        "仲介手数料": rent * agent,
        "前家賃": rent * ADVANCE_RENT_MONTHS,
        "保証会社(初回)": rent * guarantee,
        "火災保険(2年)": FIRE_INSURANCE_YEN,
        "鍵交換": KEY_EXCHANGE_YEN,
    }
    return {"rent": rent, "breakdown": breakdown, "total": sum(breakdown.values())}


def check_budget(data, rep):
    est = estimate_initial_cost(data)
    if not est:
        return
    cap = num(data, "BUD_initial_max")
    detail = {
        "内訳": {k: round(v) for k, v in est["breakdown"].items()},
        "概算合計": round(est["total"]),
        "家賃比": round(est["total"] / est["rent"], 2),
        "上限": cap,
    }
    if cap is not None and est["total"] > cap:
        rep.warn(
            "W2_INITIAL_COST_OVER",
            f"初期費用の概算 ¥{round(est['total']):,} が上限 ¥{round(cap):,} を "
            f"¥{round(est['total'] - cap):,} 超えます。敷礼ゼロ物件への絞り込み、"
            "またはフリーレントの活用を検討してください。",
            detail,
        )
    else:
        rep.info("I2_INITIAL_COST", f"初期費用の概算 ¥{round(est['total']):,}（家賃比 {detail['家賃比']}ヶ月）", detail)

    ideal = num(data, "BUD_rent_ideal")
    if ideal is not None and ideal > est["rent"]:
        rep.warn(
            "W5_IDEAL_OVER_MAX",
            f"理想家賃 ¥{round(ideal):,} が上限 ¥{round(est['rent']):,} を超えています。どちらかが誤りです。",
        )


def check_income(data, rep):
    rent = num(data, "BUD_rent_max")
    income = num(data, "BUD_income_annual")
    if not rent or not income:
        return
    annual_rent = rent * 12
    threshold = income / 3
    detail = {
        "年間家賃": round(annual_rent),
        "年収の1/3": round(threshold),
        "年収に対する家賃比率": round(annual_rent / income * 100, 1),
    }
    if annual_rent > threshold:
        rep.warn(
            "W3_INCOME_RATIO",
            f"年間家賃 ¥{round(annual_rent):,} が年収の1/3（¥{round(threshold):,}）を超えます。"
            "入居審査で不利になる可能性があります。連帯保証人の有無や貯蓄残高の提示が必要になる場合があります。",
            detail,
        )
    else:
        rep.info("I3_INCOME_RATIO", f"年収に対する家賃比率 {detail['年収に対する家賃比率']}%（審査目安は33%以下）", detail)


def parse_date(v):
    if isinstance(v, dt.date):
        return v
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
            try:
                return dt.datetime.strptime(v.strip(), fmt).date()
            except ValueError:
                continue
    return None


def check_timing(data, rep, today=None):
    today = today or dt.date.today()
    movein = parse_date(val(data, "TIM_movein_ideal"))
    notice = num(data, "TIM_current_notice")
    if movein is None or notice is None:
        return
    days_until = (movein - today).days
    months_until = days_until / 30.4
    current_rent = num(data, "TIM_current_rent")
    detail = {
        "入居希望日": movein.isoformat(),
        "本日": today.isoformat(),
        "残り月数": round(months_until, 1),
        "解約予告": notice,
    }
    if months_until < notice:
        overlap = notice - months_until
        detail["二重家賃の月数"] = round(overlap, 1)
        msg = (
            f"解約予告 {notice:g}ヶ月に対し、入居希望日まで {months_until:.1f}ヶ月しかありません。"
            f"約 {overlap:.1f}ヶ月分の二重家賃が発生します。"
        )
        if current_rent:
            cost = current_rent * overlap
            detail["二重家賃の概算"] = round(cost)
            msg += f" 現居家賃 ¥{round(current_rent):,} から概算 ¥{round(cost):,}。"
        msg += " 今すぐ解約予告を出すか、入居日を後ろ倒しするかの判断が必要です。"
        rep.warn("W4_DOUBLE_RENT", msg, detail)
    else:
        rep.info("I4_TIMING_OK", f"解約予告 {notice:g}ヶ月に対し余裕 {months_until:.1f}ヶ月。二重家賃は回避できます。", detail)


def check_must_count(data, schema, rep):
    musts = [
        cid for cid in schema
        if not cid.startswith("PRI_")
        and not is_unknown(data, cid)
        and get(data, cid).get("rank") == "MUST"
    ]
    top3 = val(data, "PRI_top3", []) or []
    if len(musts) > MUST_LIMIT:
        demotable = [c for c in musts if c not in top3]
        rep.warn(
            "W1_TOO_MANY_MUST",
            f"MUST が {len(musts)} 件あり上限 {MUST_LIMIT} 件を超えています。"
            "条件は乗算的に母数を削るため、該当ゼロになる可能性が高い状態です。"
            "PRI_top3 以外について、WANT へ降格した場合の交換レートを聞き取ってください"
            "（ユーザーが「それでも全部MUST」と明示した場合はこの警告のまま凍結して構いません）。",
            {"MUST件数": len(musts), "MUST一覧": musts, "top3": top3, "降格候補": demotable},
        )
    else:
        rep.info("I1_MUST_COUNT", f"MUST は {len(musts)} 件（上限 {MUST_LIMIT} 件）。", {"MUST一覧": musts})
    return musts


def check_consistency(data, rep):
    """条件どうしの噛み合わせを見る。"""
    # エレベーター無しで高層階
    floor = val(data, "ROM_floor")
    if isinstance(floor, str) and re.search(r"(\d+)\s*階以上", floor):
        n = int(re.search(r"(\d+)\s*階以上", floor).group(1))
        if n >= 3 and val(data, "BLD_elevator") in (None, "不問"):
            rep.warn(
                "W8_NO_ELEVATOR",
                f"{n}階以上を希望していますが、エレベーターが「不問」です。"
                "3階以上でエレベーター無しの物件は日常の負担が大きく、家具の搬入費も上がります。",
            )

    # ガス種別を不問にしている場合の実質コスト
    if val(data, "EQP_gas_type") in (None, "不問"):
        rep.warn(
            "W7_GAS_UNSPECIFIED",
            f"ガス種別が「不問」です。プロパンガスは都市ガス比で月額 約¥{LPG_MONTHLY_PREMIUM:,} "
            "上振れするのが一般的で、家賃の安さが相殺されます。"
            "実額を示したうえで、それでも不問でよいか再確認してください。",
            {"月額差の目安": LPG_MONTHLY_PREMIUM, "48ヶ月換算": LPG_MONTHLY_PREMIUM * 48},
        )

    # 定期借家
    ctype = val(data, "CTR_contract_type")
    if isinstance(ctype, str) and "定期借家" in ctype:
        rep.warn(
            "W10_FIXED_TERM",
            "定期借家を許容しています。期間満了で必ず退去となり、再契約は貸主の任意です。"
            "候補物件ごとに契約期間と再契約条項を個別確認してください。",
        )

    # 相場照会が必要な組み合わせ（S2bのWebSearch対象）
    rent = num(data, "BUD_rent_max")
    area = val(data, "LOC_area_include")
    layout = val(data, "ROM_layout")
    sqm = num(data, "ROM_area_min")
    if rent and area and layout:
        rep.info(
            "I5_MARKET_CHECK_NEEDED",
            "予算と条件の現実性は相場照会で確認してください（WebSearchで取得可能）。",
            {"エリア": area, "間取り": layout, "面積下限": sqm, "家賃上限": rent},
        )

    # ルームシェア
    occ = val(data, "CTR_occupants")
    if isinstance(occ, str) and ("友人" in occ or "シェア" in occ):
        rep.warn(
            "W11_ROOMSHARE",
            "友人同士の入居です。「二人入居可」と「ルームシェア可」は別条件で、"
            "後者を許可する物件は大きく限られます。検索時に必ず区別してください。",
        )


def check_stay_months(data, rep):
    meta = data.get("_meta") or {}
    if meta.get("stay_months_assumed", True):
        rep.info(
            "I6_STAY_ASSUMED",
            f"想定居住月数は {meta.get('stay_months', DEFAULT_STAY_MONTHS)}ヶ月の仮定値です。"
            "初期費用の月割りに影響するため、ユーザーに確認して確定させてください。",
        )


# --------------------------------------------------------------------------

def render(rep, schema, data):
    order = {"BLOCK": 0, "WARN": 1, "INFO": 2}
    icon = {"BLOCK": "🚫", "WARN": "⚠️ ", "INFO": "ℹ️ "}
    lines = ["=" * 68, " S2b 現実性の検算", "=" * 68, ""]
    for item in sorted(rep.items, key=lambda i: order[i["level"]]):
        lines.append(f"{icon[item['level']]} [{item['code']}] {item['message']}")
        for k, v in (item["detail"] or {}).items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                for e in v:
                    lines.append(f"      - {e.get('id')}  {e.get('label', '')}")
            elif isinstance(v, (list, dict)):
                lines.append(f"      {k}: {json.dumps(v, ensure_ascii=False)}")
            else:
                lines.append(f"      {k}: {v}")
        lines.append("")

    total = len([c for c in schema if not c.startswith("PRI_")])
    filled = len([c for c in schema if not c.startswith("PRI_") and not is_unknown(data, c)])
    lines += ["-" * 68, f"充足: {filled}/{total} 項目"]
    if rep.has("BLOCK"):
        lines.append("判定: 🚫 凍結不可。BLOCK を解消してから S3 へ進んでください。")
    else:
        lines.append("判定: ✅ BLOCK なし。WARN をユーザーに提示し、承認を得たうえで凍結できます。")
    lines.append("-" * 68)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="conditions.yaml の凍結前検算")
    ap.add_argument("conditions", nargs="?", help="conditions.yaml のパス")
    ap.add_argument("--init", action="store_true", help="空の雛形YAMLを標準出力へ")
    ap.add_argument("--json", action="store_true", help="機械可読なJSONで出力")
    ap.add_argument("--taxonomy", default=str(TAXONOMY), help="タクソノミMarkdownのパス")
    args = ap.parse_args()

    schema = load_taxonomy(Path(args.taxonomy))

    if args.init:
        print(emit_skeleton(schema))
        return 0

    if not args.conditions:
        ap.error("conditions.yaml のパスを指定するか --init を使ってください")

    path = Path(args.conditions)
    if not path.exists():
        print(f"[FATAL] ファイルがありません: {path}", file=sys.stderr)
        return 2
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        print(f"[FATAL] YAMLを解析できません: {e}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("[FATAL] conditions.yaml のトップレベルはマッピングである必要があります", file=sys.stderr)
        return 2

    rep = Report()
    check_completeness(data, schema, rep)
    check_ranks(data, schema, rep)
    check_exchange_rates(data, schema, rep)
    check_must_count(data, schema, rep)
    check_budget(data, rep)
    check_income(data, rep)
    check_timing(data, rep)
    check_consistency(data, rep)
    check_stay_months(data, rep)

    if args.json:
        print(json.dumps(
            {"freezable": not rep.has("BLOCK"), "findings": rep.items},
            ensure_ascii=False, indent=2,
        ))
    else:
        print(render(rep, schema, data))
    return 1 if rep.has("BLOCK") else 0


if __name__ == "__main__":
    sys.exit(main())
