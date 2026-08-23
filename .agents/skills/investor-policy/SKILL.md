---
name: investor-policy
description: 개인의 투자기간·손실 감내·종목 및 섹터 한도를 투자 판단과 비중 제안에 반영한다. "내 상황에 맞는 비중", "얼마나 사도 돼" 같은 질문에 사용.
---

# investor-policy

기업의 질과 개인에게 맞는 투자 비중을 분리한다. 비중·매수 속도·포트폴리오 위험을 묻는 경우 `config/investor-policy.json`을 먼저 확인한다.

- 파일이 없거나 필요한 값이 `null`이면 해당 값만 사용자에게 묻는다. 기업 분석 자체는 중단하지 않는다.
- 정책 값은 `USER_ASSUMPTION`이며 시장 데이터나 객관적 최적값으로 표현하지 않는다.
- `max_single_position_pct`, `max_sector_pct`, `max_portfolio_drawdown_pct`는 상한이지 목표 비중이 아니다.
- 비상자금과 가까운 시일의 필요자금은 투자 가능 자산에 포함하지 않는다.
- 여러 항목을 단일 risk score로 합치지 않는다.
- `_pct` 값은 0~100의 퍼센트 숫자다. 예: 20%는 `20`으로 기록한다.

설정은 `config/investor-policy.example.json`을 복사해 작성한다. 비중 질문은 `portfolio` Skill의 실제 보유 비중·집중도와 정책 상한을 나란히 비교해 답한다.
