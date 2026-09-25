"""품번 + 매입가 -> 사이즈별 차익 계산, 사입 판정, 추천 사이즈.

사이트 접속 없이 계산만 하는 부분이다 (시험하기 쉽게 분리).
"""
import re
from datetime import date, datetime, timedelta

from fees import kream_net_profit, poizon_net_profit
from parsers import size_key

MIN_PROFIT = 10000   # 이 금액 이상 남아야 "차익 있음"으로 본다 (--min-profit 으로 변경)


def days_ago(when, today=None):
    """크림 체결 거래일 글자 -> 오늘로부터 며칠 전인지. 모르면 None.

    형식 예: "7시간 전", "30분 전", "3일 전", "26/09/23"
    """
    today = today or date.today()
    w = (when or "").strip()
    if re.match(r"^\d+\s*(초|분|시간)\s*전$", w) or w in ("방금 전", "오늘"):
        return 0
    m = re.match(r"^(\d+)\s*일\s*전$", w)
    if m:
        return int(m.group(1))
    if w == "어제":
        return 1
    m = re.match(r"^(\d{2})/(\d{2})/(\d{2})$", w)
    if m:
        d = date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return (today - d).days
    return None


def speed_label(span_days, trade_count):
    """최근 체결 5건이 며칠 사이에 일어났는지로 판매 속도를 매긴다."""
    if trade_count < 5 or span_days is None:
        return "거래 적음", 0.0
    if span_days <= 3:
        return "매우 빠름", 1.0
    if span_days <= 7:
        return "빠름", 0.9
    if span_days <= 21:
        return "보통", 0.7
    return "느림", 0.4


def kream_size_row(info, size, today=None):
    """크림 사이즈 페이지 파싱 결과 -> 사이즈 한 줄 요약."""
    size = str(size)
    label = (info.get("top_label") or "").replace(" 구매가", "")
    ask = info["top_price"] if label and size_key(label) == size else None
    trades = [t for t in info.get("trades", []) if size_key(t["size"]) == size]
    last = trades[0]["price"] if trades else None
    span = days_ago(trades[-1]["when"], today) if trades else None
    speed, weight = speed_label(span, len(trades))
    # 예상 판매가: 지금 최저 판매가(구매가)와 최근 체결가 중 낮은 값 (보수적으로)
    candidates = [p for p in (ask, last) if p]
    expected = min(candidates) if candidates else None
    return {"size": size, "ask": ask, "last": last, "trades": len(trades), "span": span,
            "speed": speed, "weight": weight, "kream_expected": expected}


def build_table(kream_rows, poizon_sizes, buy, level, poizon_in_best=False):
    """사이즈별로 크림/포이즌 순수익을 계산하고 더 나은 채널을 고른다.

    poizon_in_best=False(기본): 포이즌 소비자 사이트 가격은 판매자 정산가보다 높을 수 있어서
    판정에는 크림만 쓰고 포이즌은 참고로만 보여준다.
    """
    pz = {}
    for s in poizon_sizes or []:
        if s["price"] and s["size"] not in pz:
            pz[s["size"]] = s["price"]
    rows = []
    for r in kream_rows:
        row = dict(r)
        row["kream_profit"] = kream_net_profit(r["kream_expected"], buy, level) if r["kream_expected"] else None
        row["poizon_price"] = pz.get(r["size"])
        row["poizon_profit"] = poizon_net_profit(row["poizon_price"], buy) if row["poizon_price"] else None
        options = [(row["kream_profit"], "크림")]
        if poizon_in_best:
            options.append((row["poizon_profit"], "포이즌"))
        options = [o for o in options if o[0] is not None]
        if options:
            row["best_profit"], row["best_channel"] = max(options)
        else:
            row["best_profit"], row["best_channel"] = None, None
        rows.append(row)
    return rows


def recommend(rows, min_profit=MIN_PROFIT, top=3):
    """추천 사이즈와 사입 판정.

    - 추천: 순수익 >= min_profit 이고 크림 판매 속도가 "보통" 이상인 사이즈를
            (순수익 x 속도 가중치) 높은 순으로 top개
    - 판정: 추천 사이즈가 있으면 "사입 추천", 차익은 있는데 느리면 "신중",
            차익 없으면 "사입 비추천"
    """
    profitable = [r for r in rows if r["best_profit"] is not None and r["best_profit"] >= min_profit]
    good = [r for r in profitable if r["weight"] >= 0.7]
    good.sort(key=lambda r: r["best_profit"] * r["weight"], reverse=True)
    slow = [r for r in profitable if r["weight"] < 0.7]
    slow.sort(key=lambda r: r["best_profit"], reverse=True)
    if good:
        verdict = "사입 추천"
    elif slow:
        verdict = "신중 (차익은 있지만 크림 판매가 느리거나 거래가 적음)"
    else:
        verdict = "사입 비추천 (차익이 기준 미달)"
    return {"verdict": verdict, "picks": good[:top], "slow": slow[:top], "min_profit": min_profit}


def parse_sizes(spec):
    """"250-290" 또는 "250,260,270" -> ["250", "255", ...]"""
    spec = spec.replace(" ", "")
    if "-" in spec:
        a, b = spec.split("-", 1)
        return [str(s) for s in range(int(a), int(b) + 1, 5)]
    return [s for s in spec.split(",") if s]


def fmt_won(v):
    return f"{v:,}" if isinstance(v, int) else "-"


def fmt_profit(v):
    return f"{v:+,}" if isinstance(v, int) else "-"


def report(code, title, buy, rows, rec, seller=None, poizon_in_best=False):
    """모바일에서 읽기 좋게 결과 글자를 만든다."""
    out = [f"{code} {title or ''}".strip(), f"매입가 {buy:,}원 / 기준 순수익 {rec['min_profit']:,}원 이상", ""]
    out.append(f"판정: {rec['verdict']}")
    if rec["picks"]:
        out.append("추천 사이즈:")
        for i, r in enumerate(rec["picks"], 1):
            price = r["kream_expected"] if r["best_channel"] == "크림" else r["poizon_price"]
            mark = " ※포이즌 소비자가 기준" if r["best_channel"] == "포이즌" else ""
            out.append(f"  {i}) {r['size']}  {r['best_channel']} {fmt_won(price)}원 -> 순수익 {fmt_profit(r['best_profit'])}원"
                       f"  (크림 최근5건 {r['span']}일, {r['speed']}){mark}")
    if rec["slow"]:
        out.append("차익은 있지만 느린 사이즈:")
        for r in rec["slow"]:
            span = f"{r['span']}일" if r["span"] is not None else "-"
            out.append(f"  - {r['size']}  {r['best_channel']} 순수익 {fmt_profit(r['best_profit'])}원 (크림 최근{r['trades']}건 {span}, {r['speed']})")
    if seller:
        out.append("")
        out.append(f"포이즌 셀러센터(전체 사이즈): 30일 평균 {fmt_won(seller.get('avg30'))}원, "
                   f"노출가 {fmt_won(seller.get('exposure'))}원, 30일 판매 {seller.get('sales30') or '-'}")
    out.append("")
    pz_head = "포이즌가 | 포이즌 순익" if poizon_in_best else "포이즌가(참고) | 포이즌 순익(참고)"
    out.append(f"사이즈 | 크림 예상가 | 크림 순익 | 크림 속도 | {pz_head}")
    for r in rows:
        span = f"{r['span']}일" if r["span"] is not None else "-"
        out.append(f"{r['size']} | {fmt_won(r['kream_expected'])} | {fmt_profit(r['kream_profit'])} | "
                   f"{r['speed']}({span}) | {fmt_won(r['poizon_price'])} | {fmt_profit(r['poizon_profit'])}")
    out.append("")
    out.append("* 크림 예상가 = 현재 구매가와 최근 체결가 중 낮은 값. 속도 = 최근 체결 5건이 며칠 사이였는지")
    if poizon_in_best:
        out.append("* 포이즌가 = 소비자 사이트 사이즈별 가격, 판정에 포함함 (--use-poizon-price)")
    else:
        out.append("* 판정은 크림 기준. 포이즌가는 소비자 사이트 가격이라 판매자 정산가보다 높을 수 있어 참고만")

    return "\n".join(out)
