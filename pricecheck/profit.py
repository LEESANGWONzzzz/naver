"""스마트스토어 순수익 계산 (2026.08 실정산 검증 공식)."""
import math

SHIPPING_FEE = 3500      # 고객이 내는 배송비
FEE_RATE = 0.0663        # 주문관리 3.63% + 판매연동 3.00%
PACKING_COST = 3066      # 박스 476 + 스티커 90 + 택배 2,500


def net_profit(sell_price, buy_price):
    """판매가와 매입가로 스마트스토어 순수익을 계산한다."""
    total = sell_price + SHIPPING_FEE
    fee = total * FEE_RATE
    return round(total - fee - PACKING_COST - buy_price)


def price_for_profit(target_profit, buy_price):
    """목표 순수익을 내기 위한 판매가 (1,000원 단위 올림)."""
    need_total = (target_profit + buy_price + PACKING_COST) / (1 - FEE_RATE)
    return math.ceil((need_total - SHIPPING_FEE) / 1000) * 1000


if __name__ == "__main__":
    # 간단 확인: python profit.py
    print(net_profit(100000, 70000))
    print(price_for_profit(20000, 70000))
