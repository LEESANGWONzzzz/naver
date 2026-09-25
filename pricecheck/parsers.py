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


def normalize(s):
    """비교용: 대소문자, 공백, 하이픈 차이를 없앤다."""
    return re.sub(r"[\s\-/]", "", s or "").upper()


def parse_kream(text):
    """KREAM 상품 페이지 글자 -> 상품명, 모델번호, 상단 가격, 체결 거래."""
    ls = lines_of(text)
    out = {"title": None, "model": None, "top_price": None, "release_price": None,
           "trades": [], "login_needed": "모든 시세는 로그인 후 확인 가능합니다." in ls}

    m = re.search(r"모델번호\s+(\S+)", text)
    if m:
        out["model"] = m.group(1)

    # 구조: "발매가 139,000원" -> ("38%") -> "85,000원" -> 상품명
    for i, l in enumerate(ls):
        if l.startswith("발매가 "):
            for j in range(i + 1, min(i + 4, len(ls))):
                p = PRICE_LINE.match(ls[j])
                if p:
                    out["top_price"] = to_int(p.group(1))
                    out["title"] = ls[j + 1] if j + 1 < len(ls) else None
                    rp = re.search(r"([0-9,]+)원", l)
                    out["release_price"] = to_int(rp.group(1)) if rp else None
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
