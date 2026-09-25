"""품번으로 KREAM / POIZON 시세를 조회한다.

사용법 (주력: 품번 + 매입가 -> 사이즈 추천):
    python price_check.py DD1391-100 69000
    python price_check.py DD1391-100 69000 --sizes 250-290 --min-profit 15000

사용법 (사이즈 하나만 자세히):
    python price_check.py DD1391-100
    python price_check.py DD1391-100 --size 270
    python price_check.py DD1391-100 --size 270 --buy 69000
    python price_check.py DD1391-100 --size 270 --buy 69000 --kream-level 2
    python price_check.py --login          (처음 한 번: 크림 + 포이즌 셀러센터 로그인)

- POIZON은 판매자 센터(seller.poizon.com)를 조회한다. --poizon-public 을 붙이면 소비자 사이트(kr.poizon.com).
- 수수료 설정은 fees.py에 있다.

- 매 조회마다 debug 폴더에 화면 캡처(png)와 페이지 글자(txt)를 저장한다.
- 가격 읽는 규칙은 parsers.py에 있다.
"""
import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from parsers import normalize, parse_kream, parse_poizon, parse_poizon_seller, size_key
from fees import KREAM_DEFAULT_LEVEL, KREAM_SHIP_COST, kream_fee, kream_net_profit, poizon_cost, poizon_net_profit
from profit import net_profit
from scan import MIN_PROFIT, build_table, kream_size_row, parse_sizes, recommend, report

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "browser_profile"
DEBUG_DIR = BASE_DIR / "debug"
# 열 구성이 바뀌어 새 파일에 기록한다 (예전 기록은 price_log.csv에 그대로 남음)
LOG_FILE = BASE_DIR / "results" / "price_log_v2.csv"
SCAN_LOG = BASE_DIR / "results" / "scan_log.csv"
MEN_SIZES = "230-300"
WOMEN_SIZES = "220-280"   # 크림 상품명이 "(W)"로 시작하면 자동 사용
POIZON_SELLER_URL = "https://seller.poizon.com/main/dataBoard"
KREAM_MAX_CANDIDATES = 5
SEARCH_HINTS = ["货号", "품번", "商品", "상품", "SKU", "SPU", "Article", "검색", "搜索", "Search"]


def save_debug(page, site, code):
    DEBUG_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = DEBUG_DIR / f"{site}_{normalize(code)}_{stamp}"
    try:
        page.screenshot(path=f"{base}.png", full_page=False)
        Path(f"{base}.txt").write_text(page.inner_text("body"), encoding="utf-8")
    except Exception as e:  # 캡처 실패는 조회 결과에 영향 주지 않음
        print(f"  (디버그 저장 실패: {e})")
    return base


def all_links(page, pattern):
    """페이지에서 href가 pattern(정규식)에 맞는 링크 주소를 순서대로 (중복 없이) 돌려준다."""
    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
    out = []
    for h in hrefs:
        h = h.split("?")[0]
        if re.search(pattern, h) and h not in out:
            out.append(h)
    return out


def save_text(name, text):
    """사이즈별 페이지 글자만 저장 (문제 생겼을 때 확인용). 같은 이름은 덮어쓴다."""
    try:
        DEBUG_DIR.mkdir(exist_ok=True)
        (DEBUG_DIR / f"{name}.txt").write_text(text, encoding="utf-8")
    except Exception:
        pass


def first_link(page, pattern):
    links = all_links(page, pattern)
    return links[0] if links else None


def check_kream(page, code, size):
    r = {"site": "KREAM", "found": False}
    page.goto(f"https://kream.co.kr/search?keyword={quote(code)}", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    links = all_links(page, r"kream\.co\.kr/products/\d+$")[:KREAM_MAX_CANDIDATES]
    if not links:
        r["note"] = "검색 결과에서 상품 링크를 못 찾음"
        r["debug"] = str(save_debug(page, "kream_search", code))
        return r

    # 같은 이름의 다른 상품이 먼저 나올 수 있어서, 모델번호가 맞는 상품이 나올 때까지 차례로 연다.
    seen = []
    first = None
    for link in links:
        url = link + (f"?size={size}" if size else "")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        info = parse_kream(page.inner_text("body"))
        seen.append(info["model"] or "?")
        cur = dict(info, url=url, model_match=normalize(info["model"]) == normalize(code))
        if first is None:
            first = cur
        if cur["model_match"]:
            r.update(cur, found=True, debug=str(save_debug(page, "kream", code)))
            return r
    r.update(first, found=True, debug=str(save_debug(page, "kream", code)),
             note=f"검색 상위 {len(seen)}개 모두 모델번호 불일치: {', '.join(seen)}")
    return r


def find_kream_product(page, code):
    """크림 검색 결과를 차례로 열어 모델번호가 맞는 상품 주소를 찾는다. 못 찾으면 (None, 확인한 모델번호들)."""
    page.goto(f"https://kream.co.kr/search?keyword={quote(code)}", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    seen = []
    for link in all_links(page, r"kream\.co\.kr/products/\d+$")[:KREAM_MAX_CANDIDATES]:
        page.goto(link, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        info = parse_kream(page.inner_text("body"))
        seen.append(info["model"] or "?")
        if normalize(info["model"]) == normalize(code):
            return link, info, seen
    return None, None, seen


def kream_scan(page, code, sizes):
    """사이즈마다 크림 페이지(?size=)를 열어 구매가와 최근 체결 5건을 모은다."""
    r = {"site": "KREAM", "found": False, "rows": []}
    link, info, seen = find_kream_product(page, code)
    if not link:
        r["note"] = f"모델번호가 같은 상품을 못 찾음 (확인한 모델번호: {', '.join(seen) or '없음'})"
        r["debug"] = str(save_debug(page, "kream_scan_fail", code))
        return r
    r.update(found=True, url=link, title=info["title"], model=info["model"],
             release_price=info["release_price"], login_needed=info["login_needed"])
    if not sizes:
        women = (info["title"] or "").startswith("(W)")
        sizes = parse_sizes(WOMEN_SIZES if women else MEN_SIZES)
        print(f"  {'여성' if women else '남성'} 상품 -> 사이즈 {sizes[0]}~{sizes[-1]} 조회")
    for s in sizes:
        page.goto(f"{link}?size={s}", wait_until="domcontentloaded")
        try:
            page.wait_for_selector(f"text={s} 구매가", timeout=7000)
            page.wait_for_selector("text=거래일", timeout=4000)
        except Exception:
            pass  # 없는 사이즈이거나 늦게 뜬 경우. 아래에서 빈 값으로 처리
        page.wait_for_timeout(800)
        text = page.inner_text("body")
        save_text(f"kream_{normalize(code)}_{s}", text)
        si = parse_kream(text)
        row = kream_size_row(si, s)
        r["rows"].append(row)
        print(f"  크림 {s}: 예상가 {row['kream_expected'] or '-'} / 최근{row['trades']}건 {row['speed']}")
    r["debug"] = str(save_debug(page, "kream_scan", code))
    return r


def check_poizon_seller(page, code):
    """POIZON 판매자 센터. 화면 구조를 아직 확인하지 못해 캡처 저장 + 검색 시도까지만 한다."""
    r = {"site": "POIZON 셀러센터", "found": False, "seller": True}
    page.goto(POIZON_SELLER_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    r["url"] = page.url
    if "login" in page.url.lower():
        r["note"] = "로그인 안 됨 -> run.cmd --login 으로 셀러센터에 한 번 로그인"
        r["debug"] = str(save_debug(page, "poizon_seller_login", code))
        return r
    r["debug_board"] = str(save_debug(page, "poizon_seller_board", code))

    # 검색창 찾기: placeholder에 품번/상품/SKU 같은 글자가 있는 입력칸
    box = None
    for el in page.locator("input:visible").all():
        ph = (el.get_attribute("placeholder") or "")
        if any(h.lower() in ph.lower() for h in SEARCH_HINTS):
            box = el
            break
    r["searched"] = False
    if box:
        box.fill(code)
        page.wait_for_timeout(1000)
        # Enter로는 검색이 안 되고 "검색 및 입찰" 버튼을 눌러야 한다 (2026-09-26 확인).
        # 결과가 새 탭으로 열릴 수 있어서 새 탭도 기다린다.
        btn = page.get_by_text("검색 및 입찰", exact=True).first
        before = len(page.context.pages)
        btn.click()
        page.wait_for_timeout(6000)
        if len(page.context.pages) > before:
            page = page.context.pages[-1]
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(4000)
            r["new_tab"] = True
        r["searched"] = True
        r["url"] = page.url
    text = page.inner_text("body")
    r["debug"] = str(save_debug(page, "poizon_seller_search", code))
    info = parse_poizon_seller(text, code)
    if info["match"]:
        r.update(info["match"], found=True)
    else:
        codes = ", ".join(x["code"] for x in info["rows"]) or "없음"
        r["note"] = f"검색 결과에 품번이 같은 상품이 없음 (결과 품번: {codes})"
    return r


def check_poizon(page, code):
    r = {"site": "POIZON", "found": False}
    page.goto(f"https://kr.poizon.com/search?keyword={quote(code)}", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    link = first_link(page, r"kr\.poizon\.com/.*(product|goods|detail)")
    if not link:
        r["note"] = "검색 결과에서 상품 링크를 못 찾음"
        r["debug"] = str(save_debug(page, "poizon_search", code))
        return r

    page.goto(link, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    info = parse_poizon(page.inner_text("body"))
    r.update(info, found=True, url=link, debug=str(save_debug(page, "poizon", code)))
    return r


def won(v):
    return f"{v:,}원" if isinstance(v, int) else "확인 불가"


def profit_text(price, buy, level=None, channel="smartstore"):
    """channel: smartstore = 스마트스토어 공식, kream = 크림 판매 수수료, poizon = 포이즌 수수료."""
    if not (buy and isinstance(price, int)):
        return ""
    ss = f"스마트스토어 판매 시 {net_profit(price, buy):,}원"
    if channel == "kream":
        return (f"\n      순수익: 크림 판매 시 {kream_net_profit(price, buy, level):,}원 "
                f"(수수료 {kream_fee(price, level):,}원 + 택배 {KREAM_SHIP_COST:,}원) / {ss}")
    if channel == "poizon":
        return (f"\n      순수익: 포이즌 판매 시 {poizon_net_profit(price, buy):,}원 "
                f"(수수료+택배 {poizon_cost(price):,}원) / {ss}")
    return f"\n      순수익: {ss}"


def print_kream(r, size, buy, level):
    print("\n[KREAM]")
    if not r["found"]:
        print(f"  {r.get('note', '')}\n  디버그: {r.get('debug')}.png")
        return
    print(f"  상품: {r['title'] or '확인 불가'}")
    match = "예" if r["model_match"] else f"아니오 (페이지 모델번호 {r['model']}, 확인 필요)"
    print(f"  모델번호 일치: {match}")
    print(f"  발매가: {won(r['release_price'])}")
    label = r.get("top_label") or "상단 구매가"
    print(f"  {label}: {won(r['top_price'])}{profit_text(r['top_price'], buy, level, 'kream')}")

    trades = r["trades"]
    if size:
        same = [t for t in trades if size_key(t["size"]) == str(size)]
        if same:
            t = same[0]
            print(f"  {size} 최근 체결: {won(t['price'])} ({t['when']}){profit_text(t['price'], buy, level, 'kream')}")
        else:
            print(f"  {size} 최근 체결: 보이는 목록에 없음")
    if trades:
        print("  최근 체결 거래: " + ", ".join(f"{t['size']} {t['price']:,}원({t['when']})" for t in trades))
    if r.get("note"):
        print(f"  ⚠ {r['note']}")
    if r["login_needed"]:
        print("  참고: 로그인 안 된 상태라 체결 거래가 일부만 보임 -> run.cmd --login 으로 한 번 로그인")


def print_poizon(r, size, buy, kream_title):
    print("\n[POIZON]")
    if not r["found"]:
        print(f"  {r.get('note', '')}\n  디버그: {r.get('debug')}.png")
        return
    print(f"  상품: {r['title'] or '확인 불가'}")
    if kream_title:
        same = normalize(r["title"]) == normalize(kream_title)
        print(f"  크림 상품명과 일치: {'예' if same else '아니오 (다른 상품일 수 있음, 확인 필요)'}")
    print("  (포이즌 페이지에는 모델번호가 없어 품번으로 확인 불가)")

    priced = [s for s in r["sizes"] if s["price"]]
    if size:
        hits = [s for s in r["sizes"] if s["size"] == str(size)]
        if not hits:
            print(f"  {size}: 사이즈표에 없음")
        for s in hits:
            print(f"  {s['label']}: {won(s['price'])}{profit_text(s['price'], buy, channel='poizon')}")
    if priced:
        low = min(priced, key=lambda s: s["price"])
        print(f"  전체 사이즈 최저: {low['label']} {low['price']:,}원")
        print("  사이즈별: " + ", ".join(f"{s['label']} {s['price'] // 1000:,}천" for s in priced))
    else:
        print(f"  사이즈별 가격: 확인 불가 (상단 가격 {won(r['top_price'])})")


def print_poizon_seller(r, buy):
    print("\n[POIZON 셀러센터]")
    if not r["found"]:
        print(f"  {r.get('note', '')}\n  디버그: {r.get('debug')}.png")
        return
    print(f"  상품: {r['title']} (품번 {r['code']}, SPU {r['spu_id']}, {r['status']})")
    print(f"  최근 30일 평균 거래가: {won(r['avg30'])}{profit_text(r['avg30'], buy, channel='poizon')}")
    print(f"  중국 구매자 페이지 노출가: {won(r['exposure'])}{profit_text(r['exposure'], buy, channel='poizon')}")
    print(f"  최근 30일 판매량: {r['sales30'] or '확인 불가'} / 현지 판매자 30일 판매량: {r['local_sales30'] or '확인 불가'}")
    print("  (사이즈별 가격은 아직 미지원, 위 가격은 전체 사이즈 기준)")


def append_log(code, size, buy, kream, poizon):
    LOG_FILE.parent.mkdir(exist_ok=True)
    new = not LOG_FILE.exists()
    k, p = kream or {}, poizon or {}
    k_trade = next((t["price"] for t in k.get("trades", []) if size_key(t["size"]) == str(size)), "")
    p_size = next((s["price"] for s in p.get("sizes", []) if s["size"] == str(size) and s["price"]), "")
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "code", "size", "buy", "title",
                        "kream_model_match", "kream_top_label", "kream_top", "kream_size_trade",
                        "poizon_avg30", "poizon_exposure", "poizon_sales30", "poizon_public_size",
                        "kream_url"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), code, size or "", buy or "",
                    k.get("title") or p.get("title") or "",
                    k.get("model_match", ""), k.get("top_label") or "", k.get("top_price") or "", k_trade,
                    p.get("avg30") or "", p.get("exposure") or "", p.get("sales30") or "", p_size,
                    k.get("url", "")])


def open_browser(p, headless):
    # 윈도우에 기본 설치된 Edge를 사용한다. 로그인 상태는 browser_profile 폴더에 남는다.
    return p.chromium.launch_persistent_context(
        str(PROFILE_DIR), channel="msedge", headless=headless,
        locale="ko-KR", viewport={"width": 1280, "height": 900},
    )


def login():
    with sync_playwright() as p:
        ctx = open_browser(p, headless=False)
        page = ctx.new_page()
        page.goto("https://kream.co.kr/login")
        page2 = ctx.new_page()
        page2.goto(POIZON_SELLER_URL)
        input("열린 창의 두 탭에서 크림, 포이즌 셀러센터에 각각 로그인한 뒤, 여기서 Enter를 누르세요...")
        ctx.close()
    print("로그인 상태를 저장했습니다.")


def run_scan(ctx, page, code, buy, sizes, level, min_profit, kream_only, use_poizon=False):
    rng = f"사이즈 {sizes[0]}~{sizes[-1]}" if sizes else "사이즈 자동(남성 230~300 / 여성 220~280)"
    print(f"품번 {code} / 매입가 {buy:,}원 / {rng} 조회 중... (1~2분 걸림)")
    kream = poizon_pub = seller = None
    try:
        kream = kream_scan(page, code, sizes)
    except Exception as e:
        kream = {"found": False, "rows": [], "note": f"오류: {e}", "debug": str(save_debug(page, "kream_error", code))}
    if not kream_only:
        try:
            poizon_pub = check_poizon(page, code)
        except Exception as e:
            poizon_pub = {"found": False, "note": f"오류: {e}"}
        try:
            seller = check_poizon_seller(page, code)
        except Exception as e:
            seller = {"found": False, "note": f"오류: {e}"}

    if not kream["found"]:
        print(f"\n[KREAM] {kream.get('note')}")
        return None
    pz_sizes = []
    if poizon_pub and poizon_pub.get("found"):
        same = normalize(poizon_pub.get("title")) == normalize(kream.get("title"))
        if same:
            pz_sizes = poizon_pub.get("sizes", [])
        else:
            print(f"\n[POIZON] 크림 상품명과 달라 제외: {poizon_pub.get('title')}")
    rows = build_table(kream["rows"], pz_sizes, buy, level, poizon_in_best=use_poizon)
    rec = recommend(rows, min_profit)
    text = report(code, kream.get("title"), buy, rows, rec,
                  seller if seller and seller.get("found") else None, poizon_in_best=use_poizon)
    if kream.get("login_needed"):
        text += "\n* 크림 로그인이 안 된 상태라 체결 거래가 부족할 수 있음 -> run.cmd --login"
    print("\n" + text)
    save_scan(code, buy, kream, rows, rec, text)
    return text


def save_scan(code, buy, kream, rows, rec, text):
    SCAN_LOG.parent.mkdir(exist_ok=True)
    (SCAN_LOG.parent / "last_report.txt").write_text(text, encoding="utf-8")
    new = not SCAN_LOG.exists()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(SCAN_LOG, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "code", "title", "buy", "verdict", "size", "kream_ask", "kream_last",
                        "kream_trades", "kream_span_days", "kream_speed", "kream_profit",
                        "poizon_price", "poizon_profit", "best_channel", "best_profit", "kream_url"])
        for r in rows:
            w.writerow([now, code, kream.get("title") or "", buy, rec["verdict"], r["size"],
                        r["ask"] or "", r["last"] or "", r["trades"], "" if r["span"] is None else r["span"],
                        r["speed"], r["kream_profit"] if r["kream_profit"] is not None else "",
                        r["poizon_price"] or "", r["poizon_profit"] if r["poizon_profit"] is not None else "",
                        r["best_channel"] or "", r["best_profit"] if r["best_profit"] is not None else "",
                        kream.get("url", "")])


def main():
    ap = argparse.ArgumentParser(description="KREAM / POIZON 시세 조회")
    ap.add_argument("code", nargs="?", help="품번 (예: DD1391-100)")
    ap.add_argument("buy_pos", nargs="?", type=int, metavar="매입가", help="매입가 (예: 69000)")
    ap.add_argument("--sizes", help=f"조회할 사이즈 범위 (기본: 남성 {MEN_SIZES}, 여성 {WOMEN_SIZES} 자동. 예: 250-290 또는 250,260,270)")
    ap.add_argument("--min-profit", type=int, default=MIN_PROFIT, help=f"사입 기준 순수익 (기본 {MIN_PROFIT:,}원)")
    ap.add_argument("--kream-only", action="store_true", help="포이즌 조회를 아예 건너뜀 (더 빠름)")
    ap.add_argument("--use-poizon-price", action="store_true",
                    help="포이즌 소비자 사이트 사이즈별 가격도 판정에 포함 (정산가와 같다고 확인된 경우만)")
    ap.add_argument("--size", help="사이즈 (예: 270)")
    ap.add_argument("--buy", type=int, help="매입가 (넣으면 순수익 계산)")
    ap.add_argument("--headless", action="store_true", help="브라우저 창 숨기기")
    ap.add_argument("--only", choices=["kream", "poizon"], help="한 사이트만 조회")
    ap.add_argument("--login", action="store_true", help="크림 + 포이즌 셀러센터 로그인 창 열기 (처음 한 번)")
    ap.add_argument("--kream-level", type=int, choices=[1, 2, 3, 4, 5], default=KREAM_DEFAULT_LEVEL,
                    help="크림 판매자 등급 (기본 1 = 수수료 6%%)")
    ap.add_argument("--poizon-public", action="store_true", help="포이즌 소비자 사이트(kr.poizon.com)로 조회")
    args = ap.parse_args()

    if args.login:
        return login()
    if not args.code:
        ap.error("품번을 입력하세요. 예: run.cmd DD1391-100 69000")
    buy = args.buy_pos or args.buy

    if not args.size:
        if not buy:
            ap.error("매입가를 입력하세요. 예: run.cmd DD1391-100 69000")
        with sync_playwright() as p:
            ctx = open_browser(p, args.headless)
            page = ctx.new_page()
            run_scan(ctx, page, args.code, buy, parse_sizes(args.sizes) if args.sizes else None, args.kream_level,
                     args.min_profit, args.kream_only, args.use_poizon_price)
            ctx.close()
        return
    args.buy = buy

    print(f"품번 {args.code}" + (f" / 사이즈 {args.size}" if args.size else "") + " 조회 중...")
    kream = poizon = None
    with sync_playwright() as p:
        ctx = open_browser(p, args.headless)
        page = ctx.new_page()
        if args.only != "poizon":
            try:
                kream = check_kream(page, args.code, args.size)
            except Exception as e:
                kream = {"site": "KREAM", "found": False, "note": f"오류: {e}",
                         "debug": str(save_debug(page, "kream_error", args.code))}
        if args.only != "kream":
            try:
                if args.poizon_public:
                    poizon = check_poizon(page, args.code)
                else:
                    poizon = check_poizon_seller(page, args.code)
            except Exception as e:
                poizon = {"site": "POIZON", "found": False, "note": f"오류: {e}",
                          "debug": str(save_debug(page, "poizon_error", args.code))}
        ctx.close()

    if kream:
        print_kream(kream, args.size, args.buy, args.kream_level)
    if poizon and poizon.get("seller"):
        print_poizon_seller(poizon, args.buy)
    elif poizon:  # --poizon-public
        print_poizon(poizon, args.size, args.buy, kream.get("title") if kream else None)
    append_log(args.code, args.size, args.buy, kream, poizon)
    print(f"\n기록 저장: {LOG_FILE}")


if __name__ == "__main__":
    sys.exit(main())
