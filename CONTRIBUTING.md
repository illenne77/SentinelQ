# 기여 가이드

SentinelQ에 기여해 주셔서 감사합니다. 버그 제보, 증권사 CSV 파서 추가,
세법 엣지케이스 개선 등 모든 기여를 환영합니다.

## 개발 환경 설정

```bash
git clone https://github.com/illenne77/SentinelQ.git
cd SentinelQ
python -m venv .venv
.venv/Scripts/Activate.ps1          # Windows / source .venv/bin/activate (macOS·Linux)
pip install -e ".[dev,ui]"
```

검증:

```bash
pytest tests/ -v          # 전체 테스트 (현재 421 passed)
ruff check sentinelq/ tests/
ruff format --check sentinelq/ tests/
```

PR을 올리기 전에 위 세 명령이 모두 통과해야 합니다. CI(`/.github/workflows/ci.yml`)가
동일한 검사 + 시크릿 스캔 + 테스트 회귀 floor를 강제합니다.

## 가장 필요한 기여: 증권사 CSV 파서 추가

현재 키움증권·미래에셋증권·한국투자증권(KIS) 거래내역만 지원합니다. NH투자증권,
삼성증권 등 다른 증권사 파서가 절실합니다. 추가 방법은 다음과 같습니다.

> 👉 **바로 시작하기**: 등록된 증권사 파서 작업은
> [`good first issue` 이슈 목록](https://github.com/illenne77/SentinelQ/labels/good%20first%20issue)에서
> 확인하세요. 원하는 증권사가 목록에 없으면 새 이슈로 제안해 주세요.

### 1. 기존 파서를 참고

`sentinelq/adapters/kiwoom_csv.py`가 가장 좋은 템플릿입니다. 파서는 다음 한
가지 규칙만 지키면 됩니다.

> **CSV 파일 경로를 받아 `list[Transaction]`을 반환하는 함수를 만든다.**

```python
def parse_<broker>_csv(
    path: Path,
    *,
    col_map: dict[str, str] | None = None,
) -> list[Transaction]:
    ...
```

### 2. Transaction 객체로 변환

각 체결 행을 `sentinelq.adapters.kis_history.Transaction`으로 변환합니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `trade_date` | `date` | 체결일 |
| `settle_date` | `date \| None` | 결제일 (없으면 None) |
| `ticker` | `str` | KR 6자리 코드 또는 US 심볼 |
| `market` | `"KR"` \| `"US"` | 시장 구분 |
| `side` | `"BUY"` \| `"SELL"` | 매매 구분 |
| `quantity` | `int` | 체결 수량 |
| `price` | `Decimal` | 체결 단가 |
| `currency` | `"KRW"` \| `"USD"` | 통화 |
| `fee` | `Decimal` | 수수료 |
| `tax` | `Decimal` | 세금·제세금 |
| `fx_rate` | `Decimal \| None` | 환율 (해외주식, 선택) |
| `raw` | `dict` | 원본 행 보존 |

### 3. 권장 패턴

- **인코딩 자동 감지**: 국내 증권사 CSV는 EUC-KR/CP949가 많습니다.
  `kiwoom_csv.py`의 `_open_csv()` 패턴(utf-8-sig → euc-kr → cp949 → utf-8)을 재사용하세요.
- **컬럼명 후보 리스트**: 증권사가 헤더명을 바꿔도 견디도록, 단일 문자열이 아닌
  후보 리스트(`_COL_DATE = ["체결일자", "거래일자", ...]`)로 매칭하세요.
- **금액 부호**: 일부 증권사는 매도 수량을 음수로 표기합니다. `side` 판정과
  `quantity` 부호 처리를 분명히 하세요.

### 4. 테스트 추가

`tests/test_<broker>_csv.py`를 만들고, 실제 CSV의 헤더 구조를 본뜬 **익명화된**
샘플 데이터로 테스트하세요. **본인의 실제 거래내역 파일은 절대 커밋하지 마세요**
(`data/private/`는 `.gitignore`에 등록되어 있습니다).

테스트는 최소한 다음을 다뤄야 합니다: 정상 파싱, 빈 파일, 매수·매도 혼재,
해외주식 환율 처리, 잘못된 형식의 행.

## 버그 제보·기능 제안

GitHub Issues에 등록해 주세요. 버그는 재현 절차와 함께, CSV 관련 문제는
**개인정보를 제거한** 헤더·샘플 행을 함께 올려주시면 빠르게 확인할 수 있습니다.

## 범위 밖 (Scope)

이 프로젝트는 세금·공시 자동화 도구입니다. 다음 기능 제안은 받지 않습니다.

- 알파 발견·자동매매·시장 타이밍·수익률 예측
- 실제 매매 주문 실행

배경은 [`docs/adr/ADR-0013-phase3-kr-investor-tools.md`](docs/adr/ADR-0013-phase3-kr-investor-tools.md)를 참고하세요.

## 커밋·PR

- 커밋 메시지는 간결하게, 무엇을 왜 바꿨는지 적어주세요.
- PR 하나는 하나의 논리적 변경에 집중해 주세요.
- 모든 PR은 CI를 통과해야 머지됩니다.

## 라이선스

기여하신 코드는 프로젝트와 동일하게 [MIT License](LICENSE)로 배포됩니다.
