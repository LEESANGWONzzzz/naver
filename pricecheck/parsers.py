"""페이지 글자(inner_text)에서 가격 정보를 뽑는다.

2026-09-26 실제 페이지(DD1391-100) 글자 구조를 기준으로 만들었다.
사이트 화면이 바뀌면 여기만 고치면 된다.
"""
import re

PRICE_LINE = re.compile(r"^([0-9]{1,3}(?:,[0-9]{3})*)원$")
SIZE_LINE = re.compile(r"^(\d{3})(?:\s*\((.*)\))?$")


def lines_of(text):
    return [l.strip() for l in text.splitlines() if l.strip()]


def to_int(price_text):
    return int(price_text.replace(",", "").replace("원", ""))


def size_key(s):
    """크림 여성 사이즈는 "W265"처럼 W가 붙는다. 비교할 때는 숫자만 쓴다."""
    return re.sub(r"^W", "", str(s or "").strip().upper())


def normalize(s):
    """비교용: 대소문자, 공백, 하이픈 차이를 없앤다."""
    return re.sub(r"[\s\-/]", "", s or "").upper()


def parse_kream(text):
    """KREAM 상품 페이지 글자 -> 상품명, 모델번호, 상단 가격, 체결 거래."""
    ls = lines_of(text)
    out = {"title": None, "model": None, "top_price": None, "top_label": None,
           "release_price": None, "trades": [],
           "login_needed": "모든 시세는 로그인 후 확인 가능합니다." in ls}

    m = re.search(r"모델번호\s+(\S+)", text)
    if m:
        out["model"] = m.group(1)
    m = re.search(r"발매가\s+([0-9,]+)원", text)
    if m:
        out["release_price"] = to_int(m.group(1))

    # 상단 가격 구조: 라벨 -> ("38%") -> "86,000원" -> 상품명
    #   사이즈 선택 안 함: 라벨 = "발매가 139,000원"
    #   사이즈 선택함(?size=270): 라벨 = "270 구매가" (여성 사이즈는 "W265 구매가")
    for i, l in enumerate(ls):
        if l.startswith("발매가 ") or re.match(r"^W?\d{3} 구매가$", l):
            for j in range(i + 1, min(i + 4, len(ls))):
                p = PRICE_LINE.match(ls[j])
                if p:
                    out["top_price"] = to_int(p.group(1))
                    out["top_label"] = l if l.endswith("구매가") else "구매가(전체 사이즈)"
                    out["title"] = ls[j + 1] if j + 1 < len(ls) else None
                    break
            if out["top_price"]:
                break

    # 체결 거래 표: "옵션" "거래가" "거래일" 다음에 (사이즈, 가격, 시간) 3줄씩
    for i in range(len(ls) - 2):
        if ls[i:i + 3] == ["옵션", "거래가", "거래일"]:
            k = i + 3
            while k + 2 < len(ls) and PRICE_LINE.match(ls[k + 1]):
                out["trades"].append({"size": ls[k], "price": to_int(ls[k + 1]), "when": ls[k + 2]})
                k += 3
            break
    return out


def parse_poizon(text):
    """POIZON 상품 페이지 글자 -> 상품명, 상단 가격, 사이즈별 가격표."""
    ls = lines_of(text)
    out = {"title": None, "top_price": None, "sizes": []}

    # 구조: "메인 페이지/스니커즈/나이키" -> 상품명 -> "123,200원"
    for i, l in enumerate(ls):
        if l.startswith("메인 페이지/") and i + 2 < len(ls):
            out["title"] = ls[i + 1]
            p = PRICE_LINE.match(ls[i + 2])
            if p:
                out["top_price"] = to_int(p.group(1))
            break

    # 사이즈표: "사이즈: KR" "사이즈 가이드" 다음에 (사이즈, 가격) 2줄씩. 가격 없으면 "--원"
    if "사이즈: KR" in ls:
        k = ls.index("사이즈: KR") + 1
        if k < len(ls) and ls[k] == "사이즈 가이드":
            k += 1
        while k + 1 < len(ls):
            s = SIZE_LINE.match(ls[k])
            if not s:
                break
            p = PRICE_LINE.match(ls[k + 1])
            if not p and ls[k + 1] != "--원":
                break
            out["sizes"].append({"size": s.group(1), "label": ls[k],
                                 "price": to_int(p.group(1)) if p else None})
            k += 2
    return out


WON_LINE = re.compile(r"^₩\s*([0-9]{1,3}(?:,[0-9]{3})*)$")


def parse_poizon_seller(text, code):
    """POIZON 판매자 센터 상품 검색 결과 표 -> 품번이 맞는 행의 시장 데이터.

    2026-09-26 확인한 행 구조:
      "상품 번호:" -> 품번 -> 상품명 -> "SPU_ID：1237613" -> 브랜드 -> 카테고리 -> 상태
      -> "₩110,000"(최근 30일 평균 거래가) -> "₩91,000"(중국 구매자 페이지 노출)
      -> "3,900+"(최근 30일 판매량) -> "80"(현지 판매자 최근 30일 판매량) ... "입찰 등록"
    """
    ls = lines_of(text)
    rows = []
    for i, l in enumerate(ls):
        if l != "상품 번호:" or i + 3 >= len(ls):
            continue
        row = {"code": ls[i + 1], "title": ls[i + 2], "spu_id": None, "status": None,
               "avg30": None, "exposure": None, "sales30": None, "local_sales30": None}
        m = re.search(r"SPU_ID\s*[:：]\s*(\d+)", ls[i + 3])
        if m:
            row["spu_id"] = m.group(1)
        # 이 행의 끝("입찰 등록" 또는 다음 "상품 번호:")까지
        end = len(ls)
        for j in range(i + 4, len(ls)):
            if ls[j] in ("입찰 등록", "상품 번호:"):
                end = j
                break
        cells = ls[i + 4:end]
        wons = [k for k, c in enumerate(cells) if WON_LINE.match(c)]
        if wons:
            row["status"] = cells[wons[0] - 1] if wons[0] >= 1 else None
            row["avg30"] = to_int(WON_LINE.match(cells[wons[0]]).group(1))
            if len(wons) > 1 and wons[1] == wons[0] + 1:
                row["exposure"] = to_int(WON_LINE.match(cells[wons[1]]).group(1))
                rest = cells[wons[1] + 1:]
                row["sales30"] = rest[0] if len(rest) > 0 else None
                row["local_sales30"] = rest[1] if len(rest) > 1 else None
        rows.append(row)

    match = [r for r in rows if normalize(r["code"]) == normalize(code)]
    return {"rows": rows, "match": match[0] if match else None}
