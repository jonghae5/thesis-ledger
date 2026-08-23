---
name: portfolio
description: 보유종목 등록/삭제, position sizing, sector exposure, 손익을 계산한다. "내 포트폴리오", "보유종목 어때" 같은 질문에 사용.
---

# portfolio

## 목적
보유 종목 전체를 놓고 position sizing, sector exposure, 어떤 종목이 가장 위험한지 판단한다 (원본 스펙 §6.20). "가장 위험하다"는 판단 자체는 Codex 몫이다 — 이 skill은 weight/gain/sector exposure 같은 객관적 숫자만 계산한다.

## 실행할 CLI 커맨드

### 보유 등록/삭제
```bash
uv run thesis portfolio add <TICKER> --shares N --avg-cost N --opened-at YYYY-MM-DD [--sector "..."]
uv run thesis portfolio remove <TICKER>
```
`add-holding`은 티커당 한 row만 유지한다(같은 티커 다시 add하면 shares/avg_cost/opened_at/sector가 통째로 갱신됨 — 매수 추가/전량 재계산은 Codex가 새 평균단가를 계산해서 넘긴다). `sector`는 Codex가 직접 채운다 — 이 프로젝트엔 섹터를 자동으로 알아내는 데이터 소스가 없다.

### 포트폴리오 조회
```bash
uv run thesis portfolio show
uv run thesis data macro
```
모든 보유종목을 대상으로 하며 티커를 받지 않는다. 각 보유종목에 최신 가격이 있어야 하며, 없으면 `uv run thesis data fetch <TICKER>`를 먼저 실행한다.

출력:
```json
{
  "positions": [
    {"ticker": "NVDA", "shares": 10.0, "avg_cost": 150.0, "price": 214.72, "sector": "Semiconductors",
     "market_value": 2147.2, "cost_basis": 1500.0, "unrealized_gain_pct": 0.431, "weight": 0.62}
  ],
  "total_market_value": 0, "total_cost_basis": 0, "total_unrealized_gain_pct": 0,
  "top_holding_ticker": "NVDA", "top_holding_weight": 0.62,
  "sector_exposure": {"Semiconductors": 0.62, "UNKNOWN": 0.38}
}
```
`positions`는 `weight` 내림차순(가장 큰 비중이 먼저). `risk`에는 공통 가격
이력이 20개 이상일 때 `annualized_volatility`, `max_drawdown`,
`concentration_hhi`, `effective_number_of_positions`, 종목 쌍별
`correlations`가 포함된다. SPY 가격이 저장되어 있고 최신이면 `beta_spy`도 계산한다.

## "가장 위험한 종목" 질문에 답하는 법
1. `uv run thesis portfolio show` — weight, gain/loss, sector exposure 확보.
2. weight 상위 종목들 각각에 대해 `uv run thesis data market <TICKER>`(변동성, 200일선 거리) + `uv run thesis valuation multiples <TICKER>`(밸류에이션 스트레치) 호출.
3. Codex가 종합: 비중 크고 + 변동성 높고 + 밸류에이션 과도하게 늘어난 종목이 보통 "가장 위험" — 하지만 최종 판단 문구는 Codex가 쓴다, Python은 숫자만 준다.

## 매크로와 position sizing

개인에게 맞는 비중을 묻는 경우 `investor-policy` Skill의 기간·손실 감내·종목 및 섹터 상한을 먼저 확인한다. 설정이 없으면 필요한 값만 질문하며, 임의의 적정 비중을 만들지 않는다.

포트폴리오 위험 또는 비중 조정을 묻는 경우 `data macro`의 금리, 신용·유동성, VIX, Fear & Greed를 별도 축으로 확인한다. snapshot이 없으면 `data macro-fetch`를 먼저 실행한다.

- 실질금리와 신용 스프레드는 장기 성장주·고부채 종목의 할인율 및 자금조달 민감도와 연결한다.
- VIX와 Fear & Greed는 시장 위험선호와 진입 속도·position sizing의 보조 근거로만 사용한다.
- 극단적 공포를 자동 매수, 극단적 탐욕을 자동 축소로 변환하지 않는다.
- 종목별 변동성·상관관계·비중과 macro 축을 나란히 제시하며 단일 portfolio risk score로 합치지 않는다.

## 구현하지 않은 것
거래 lot, 현금·환율, 배당·세금·수수료, 옵션/공매도, 브로커 대사는 아직 없다.
따라서 `portfolio`는 리서치용 위험 요약이지 계좌 원장의 대체물이 아니다.
