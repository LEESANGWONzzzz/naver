"""품번으로 KREAM / POIZON 시세를 조회한다.

사용법:
    python price_check.py DD1391-100
    python price_check.py DD1391-100 --size 270
    python price_check.py DD1391-100 --size 270 --buy 69000
    python price_check.py --login          (처음 한 번: 크림 로그인)

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

from parsers import normalize, parse_kream, parse_poizon
from profit import net_profit

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "browser_profile"
DEBUG_DIR = BASE_DIR / "debug"
LOG_FILE = BASE_DIR / "results" / "price_log.csv"


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


def first_link(page, pattern):
    """페이지에서 href가 pattern(정규식)에 맞는 첫 링크 주소를 돌려준다."""
    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
    for h in hrefs:
        if re.search(pattern, h):
            return h
    return None


def check_kream(page, code, size):
    r = {"site": "KREAM", "found": False}
    page.goto(f"https://kream.co.kr/search?keyword={quote(code)}", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    link = first_link(page, r"kream\.co\.kr/products/\d+")
    if not link:
        r["note"] = "검색 결과에서 상품 링크를 못 찾음"
        r["debug"] = str(save_debug(page, "kream_search", code))
        return r

    url = link.split("?")[0] + (f"?size={size}" if size else "")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    info = parse_kream(page.inner_text("body"))
    r.update(info, found=True, url=url,
             model_match=normalize(info["model"]) == normalize(code),
             debug=str(save_debug(page, "kream", code)))
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


def profit_text(price, buy):
    if buy and isinstance(price, int):
        return f"  (스마트스토어 {price:,}원 판매 시 순수익 {net_profit(price, buy):,}원)"
    return ""


def print_kream(r, size, buy):
    print("\n[KREAM]")
    if not r["found"]:
        print(f"  {r.get('note', '')}\n  디버그: {r.get('debug')}.png")
        return
    print(f"  상품: {r['title'] or '확인 불가'}")
    match = "예" if r["model_match"] else f"아니오 (페이지 모델번호 {r['model']}, 확인 필요)"
    print(f"  모델번호 일치: {match}")
    print(f"  발매가: {won(r['release_price'])}")
    label = f"상단 구매가(사이즈 {size} 주소로 조회, 사이즈 반영 여부 미검증)" if size else "상단 구매가(전체 사이즈 중)"
    print(f"  {label}: {won(r['top_price'])}{profit_text(r['top_price'], buy)}")

    trades = r["trades"]
    if size:
        same = [t for t in trades if t["size"] == str(size)]
        if same:
            t = same[0]
            print(f"  {size} 최근 체결: {won(t['price'])} ({t['when']}){profit_text(t['price'], buy)}")
        else:
            print(f"  {size} 최근 체결: 보이는 목록에 없음")
    if trades:
        print("  최근 체결 거래: " + ", ".join(f"{t['size']} {t['price']:,}원({t['when']})" for t in trades))
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
            print(f"  {s['label']}: {won(s['price'])}{profit_text(s['price'], buy)}")
    if priced:
        low = min(priced, key=lambda s: s["price"])
        print(f"  전체 사이즈 최저: {low['label']} {low['price']:,}원")
        print("  사이즈별: " + ", ".join(f"{s['label']} {s['price'] // 1000:,}천" for s in priced))
    else:
        print(f"  사이즈별 가격: 확인 불가 (상단 가격 {won(r['top_price'])})")


def append_log(code, size, buy, kream, poizon):
    LOG_FILE.parent.mkdir(exist_ok=True)
    new = not LOG_FILE.exists()
    k_size = next((t["price"] for t in (kream or {}).get("trades", []) if t["size"] == str(size)), "")
    p_size = next((s["price"] for s in (poizon or {}).get("sizes", []) if s["size"] == str(size) and s["price"]), "")
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "code", "size", "buy", "title", "kream_model_match",
                        "kream_top", "kream_size_trade", "poizon_top", "poizon_size", "kream_url", "poizon_url"])
        k, p = kream or {}, poizon or {}
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), code, size or "", buy or "",
                    k.get("title") or p.get("title") or "", k.get("model_match", ""),
                    k.get("top_price") or "", k_size, p.get("top_price") or "", p_size,
                    k.get("url", ""), p.get("url", "")])


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
        input("열린 창에서 크림에 로그인한 뒤, 여기서 Enter를 누르세요...")
        ctx.close()
    print("로그인 상태를 저장했습니다.")


def main():
    ap = argparse.ArgumentParser(description="KREAM / POIZON 시세 조회")
    ap.add_argument("code", nargs="?", help="품번 (예: DD1391-100)")
    ap.add_argument("--size", help="사이즈 (예: 270)")
    ap.add_argument("--buy", type=int, help="매입가 (넣으면 순수익 계산)")
    ap.add_argument("--headless", action="store_true", help="브라우저 창 숨기기")
    ap.add_argument("--only", choices=["kream", "poizon"], help="한 사이트만 조회")
    ap.add_argument("--login", action="store_true", help="크림 로그인 창 열기 (처음 한 번)")
    args = ap.parse_args()

    if args.login:
        return login()
    if not args.code:
        ap.error("품번을 입력하세요. 예: run.cmd DD1391-100 --size 270")

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
                poizon = check_poizon(page, args.code)
            except Exception as e:
                poizon = {"site": "POIZON", "found": False, "note": f"오류: {e}",
                          "debug": str(save_debug(page, "poizon_error", args.code))}
        ctx.close()

    if kream:
        print_kream(kream, args.size, args.buy)
    if poizon:
        print_poizon(poizon, args.size, args.buy, kream.get("title") if kream else None)
    append_log(args.code, args.size, args.buy, kream, poizon)
    print(f"\n기록 저장: {LOG_FILE}")


if __name__ == "__main__":
    sys.exit(main())
