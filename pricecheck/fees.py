"""판매 채널별 수수료 설정. 요율이 바뀌면 여기만 고친다.

KREAM (2026-03-02 적용, 확인일 2026-09-26)
  출처: 크림 FAQ "[수수료] 판매자 등급 및 수수료 기준(2026.3.2 적용)" https://kream.co.kr/faq/221
        머니투데이 2026-02-04 기사, 패션비즈 기사
  - 등급 수수료(VAT 별도): 레벨1 6% / 레벨2 5.95% / 레벨3 5.7% / 레벨4 5.6% / 레벨5 5.5%
    (레벨 기준 정산금액: 1 = 200만 미만, 2 = 200만~1000만, 3 = 1000만~2000만,
     4 = 2000만~6000만, 5 = 6000만 이상)
  - 기본 수수료 2,500원(VAT 별도) = 2,750원(VAT 포함)
  - 수수료(기본+등급) 합계 VAT 포함 최대 300,000원
  - 프리미엄 상품은 별도 요율 (여기 반영 안 함)
  - 원 단위 반올림/절사 방식은 확인 불가 -> 반올림으로 계산

POIZON 개인 판매자 (사용자 확인, 2026-09-26)
  - 판매금액 150,000원 이하: 기본 수수료 15,000원 + 택배비 판매자 부담
  - 판매금액 150,000원 초과: 결제금액의 10%
    (150,000원 초과일 때 택배비를 판매자가 내는지는 확인 필요 -> 지금은 안 냄으로 계산)
"""
import math

KREAM_LEVEL_RATE = {1: 0.06, 2: 0.0595, 3: 0.057, 4: 0.056, 5: 0.055}
KREAM_BASE_FEE = 2500
KREAM_VAT = 1.1
KREAM_FEE_CAP = 300000
KREAM_DEFAULT_LEVEL = 1     # 사용자 등급 레벨1 (2026-09-26 확인)
KREAM_SHIP_COST = 2500      # 크림 검수센터로 보내는 택배비 (사용자 확인)

POIZON_THRESHOLD = 150000   # 이 금액 이하면 고정 수수료
POIZON_FIXED_FEE = 15000
POIZON_SHIP_COST = 2500     # 150,000원 이하일 때 판매자 부담 택배비 (크림과 같은 금액으로 가정, 확인 필요)
POIZON_HIGH_RATE = 0.10     # 150,000원 초과 시 결제금액의 10%


def kream_fee(price, level=KREAM_DEFAULT_LEVEL):
    fee = (price * KREAM_LEVEL_RATE[level] + KREAM_BASE_FEE) * KREAM_VAT
    return min(round(fee), KREAM_FEE_CAP)


def kream_net_profit(price, buy_price, level=KREAM_DEFAULT_LEVEL):
    return price - kream_fee(price, level) - KREAM_SHIP_COST - buy_price


def poizon_cost(price):
    """포이즌 판매 시 수수료 + 판매자 부담 택배비."""
    if price <= POIZON_THRESHOLD:
        return POIZON_FIXED_FEE + POIZON_SHIP_COST
    return round(price * POIZON_HIGH_RATE)


def poizon_net_profit(price, buy_price):
    return price - poizon_cost(price) - buy_price


def kream_price_for_profit(target_profit, buy_price, level=KREAM_DEFAULT_LEVEL):
    """크림에서 목표 순수익을 내기 위한 판매가 (1,000원 단위 올림)."""
    rate = KREAM_LEVEL_RATE[level] * KREAM_VAT
    need = (target_profit + buy_price + KREAM_SHIP_COST + KREAM_BASE_FEE * KREAM_VAT) / (1 - rate)
    return math.ceil(need / 1000) * 1000
