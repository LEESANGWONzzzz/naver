"""품번으로 KREAM / POIZON 시세를 조회한다.

사용법:
    python price_check.py DD1391-100
    python price_check.py DD1391-100 --size 270
    python price_check.py DD1391-100 --size 270 --buy 69000

주의:
- 두 사이트의 화면 구조를 미리 확인하지 못한 상태로 만든 첫 버전이다.
  매 조회마다 debug 폴더에 화면 캡처(png)와 페이지 글자(txt)를 저장하니,
  결과가 이상하면 그 파일을 보고 고친다.
- 사이즈별 가격 조회(KREAM ?size= 주소)는 검증되지 않았다.
"""
import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from profit import net_profit

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "browser_profile"
DEBUG_DIR = BASE_DIR / "debug"
LOG_FILE = BASE_DIR / "results" / "price_log.csv"

PRICE_RE = r"([0-9]{1,3}(?:,[0-9]{3})+)\s*원"


def normalize_code(code):
    """비교용: 대소문자, 공백, 하이픈 차이를 없앤다."""
    return re.sub(r"[\s\-/]", "", code).upper()


def price_after(text, label, window=60):
    """text 안에서 label 뒤 window 글자 이내의 첫 가격(원)을 찾는다."""
    for m in re.finditer(re.escape(label), text):
        seg = text[m.end():m.end() + window]
        p = re.search(PRICE_RE, seg)
        if p:
            return int(p.group(1).replace(",", ""))
    return None


def save_debug(page, site, code):
    DEBUG_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = DEBUG_DIR / f"{site}_{normalize_code(code)}_{stamp}"
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
    result = {"site": "KREAM", "found": False}
    page.goto(f"https://kream.co.kr/search?keyword={quote(code)}", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    link = first_link(page, r"kream\.co\.kr/products/\d+")
    if not link:
        result["note"] = "검색 결과에서 상품 링크를 못 찾음"
        result["debug"] = str(save_debug(page, "kream_search", code))
        return result

    url = link.split("?")[0] + (f"?size={size}" if size else "")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    text = page.inner_text("body")

    result.update(
        found=True,
        url=url,
        model_match=normalize_code(code) in normalize_code(text),
        recent=price_after(text, "최근 거래가"),
        buy_now=price_after(text, "즉시 구매가"),
        sell_now=price_after(text, "즉시 판매가"),
        debug=str(save_debug(page, "kream", code)),
    )
    return result


def check_poizon(page, code, size):
    result = {"site": "POIZON", "found": False}
    # 검색 주소 형식을 확인하지 못해 후보를 차례로 시도한다.
    candidates = [
        f"https://kr.poizon.com/search?keyword={quote(code)}",
        f"https://kr.poizon.com/search?q={quote(code)}",
    ]
    link = None
    for c in candidates:
        page.goto(c, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        link = first_link(page, r"kr\.poizon\.com/.*(product|goods|detail)")
        if link:
            break
    if not link:
        result["note"] = "검색 결과에서 상품 링크를 못 찾음 (검색 주소 형식 미확인)"
        result["debug"] = str(save_debug(page, "poizon_search", code))
        return result

    page.goto(link, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    text = page.inner_text("body")
    prices = [int(p.replace(",", "")) for p in re.findall(PRICE_RE, text)]
    won_sign = [int(p.replace(",", "")) for p in re.findall(r"₩\s*([0-9]{1,3}(?:,[0-9]{3})+)", text)]
    all_prices = prices + won_sign

    result.update(
        found=True,
        url=link,
        model_match=normalize_code(code) in normalize_code(text),
        lowest=min(all_prices) if all_prices else None,
        debug=str(save_debug(page, "poizon", code)),
    )
    if size:
        result["note"] = "사이즈별 가격은 아직 미지원, 페이지 최저가 표시"
    return result


def won(v):
    return f"{v:,}원" if isinstance(v, int) else "확인 불가"


def print_result(r, buy):
    print(f"\n[{r['site']}]")
    if not r["found"]:
        print(f"  {r.get('note', '')}")
        print(f"  디버그: {r.get('debug')}.png / .txt")
        return
    print(f"  주소: {r['url']}")
    print(f"  품번 일치: {'예' if r['model_match'] else '아니오 (다른 상품일 수 있음, 확인 필요)'}")
    keys = [("recent", "최근 거래가"), ("buy_now", "즉시 구매가"),
            ("sell_now", "즉시 판매가"), ("lowest", "페이지 최저가")]
    for k, label in keys:
        if k in r:
            line = f"  {label}: {won(r[k])}"
            if buy and isinstance(r[k], int) and k in ("recent", "buy_now", "lowest"):
                line += f"  -> 스마트스토어에서 이 가격에 팔면 순수익 {net_profit(r[k], buy):,}원"
            print(line)
    if r.get("note"):
        print(f"  참고: {r['note']}")


def append_log(code, size, buy, results):
    LOG_FILE.parent.mkdir(exist_ok=True)
    new = not LOG_FILE.exists()
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "code", "size", "buy", "site", "model_match",
                        "recent", "buy_now", "sell_now", "lowest", "url"])
        for r in results:
            w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), code, size or "", buy or "",
                        r["site"], r.get("model_match", ""), r.get("recent", ""),
                        r.get("buy_now", ""), r.get("sell_now", ""), r.get("lowest", ""),
                        r.get("url", "")])


def main():
    ap = argparse.ArgumentParser(description="KREAM / POIZON 시세 조회")
    ap.add_argument("code", help="품번 (예: DD1391-100)")
    ap.add_argument("--size", help="사이즈 (예: 270)")
    ap.add_argument("--buy", type=int, help="매입가 (넣으면 순수익 계산)")
    ap.add_argument("--headless", action="store_true", help="브라우저 창 숨기기")
    ap.add_argument("--only", choices=["kream", "poizon"], help="한 사이트만 조회")
    args = ap.parse_args()

    print(f"품번 {args.code}" + (f" / 사이즈 {args.size}" if args.size else "") + " 조회 중...")
    results = []
    with sync_playwright() as p:
        # 윈도우에 기본 설치된 Edge를 사용한다. 로그인 상태는 browser_profile 폴더에 남는다.
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE_DIR), channel="msedge", headless=args.headless,
            locale="ko-KR", viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        for name, fn in (("kream", check_kream), ("poizon", check_poizon)):
            if args.only and args.only != name:
                continue
            try:
                results.append(fn(page, args.code, args.size))
            except Exception as e:
                results.append({"site": name.upper(), "found": False, "note": f"오류: {e}",
                                "debug": str(save_debug(page, name + "_error", args.code))})
        ctx.close()

    for r in results:
        print_result(r, args.buy)
    append_log(args.code, args.size, args.buy, results)
    print(f"\n기록 저장: {LOG_FILE}")


if __name__ == "__main__":
    sys.exit(main())
