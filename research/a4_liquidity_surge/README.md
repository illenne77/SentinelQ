# A4 — Liquidity Surge

알파 카탈로그 A4 백테스트 워크스페이스. **현 상태: 골격(skeleton)** — Sprint 1에서 채워짐.

## 가설
당일 10:30 KST 시점의 누적 거래량이 직전 20영업일 동시간대 거래량의 중앙값 대비 2배 이상이고, 알려진 일정 이벤트(실적·배당·거래정지)에 기인하지 않는 경우, 향후 1~3일 수익률 기대값 양(+).

## 입력
- KIS `inquire-price.prdy_vrss_vol_rate` (실시간 운영용)
- 분봉 OHLCV (백테스트용, Lean)
- Earnings/Dividend/Halt 캘린더 (T-1 기준)

## 산출물
- 폴드별 Sharpe / MDD / Hit Rate / 거래 수
- 비용 민감도 (슬리피지 0/4/8/15 bps)
- 레짐별 분해 (강세/약세/횡보)

## 졸업 조건 (Phase 0 → 0.5)
- OOS Sharpe ≥ 1.0 (비용 후)
- MDD ≥ -10% 유지
- Hit Rate ≥ 52%
- 60분 이내 백테스트 1회 재현 (시드 고정)
- §7.4.2 편향 체크리스트 8/8

## 파일
- `main.py` — Lean QCAlgorithm 골격
- `walk_forward.py` — TODO
- `grid_search.yaml` — TODO

## 주의
- LONG ONLY (계획서 §1A.2 Out-of-Scope: 공매도 제외)
- 모의 시세와 실거래 시세를 **절대 혼합 금지** (`api_env` 컬럼 분리)
- 그리드 서치는 1회만 — 모든 시도 결과를 기록 (p-hacking 방지)
