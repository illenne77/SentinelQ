"""위택스 지방소득세 신고 안내 리포트 생성 (T012).

PREREG: PREREG-0008-amendment-2 §2.5
Mandate: 지방소득세 별도 신고 안내 자동화

G2 실증에서 확인: NTS 홈택스 신고 확인서에는 지방소득세 미포함.
위택스(wetax.go.kr)를 통해 별도 신고·납부 필요 (신고기한: 다음 해 5월 31일).

OUT: 위택스 API 자동 제출 (API 미공개).
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO
from pathlib import Path

from sentinelq.reports.nts_form import NTSCapitalGainsForm


def _fmt(amount: Decimal | int) -> str:
    return f"{int(amount):,}"


def build_wetax_guide(form: NTSCapitalGainsForm) -> str:
    """NTSCapitalGainsForm → 위택스 지방소득세 신고 안내 텍스트."""
    buf = StringIO()
    w = buf.write

    w("=" * 70 + "\n")
    w("  위택스 지방소득세 신고 안내 (양도소득에 대한 개인지방소득세)\n")
    w(f"  과세기간: {form.tax_year}년 | 신고기한: {form.filing_period_end}\n")
    w("=" * 70 + "\n\n")

    w("■ 왜 위택스에서 별도 신고가 필요한가?\n")
    w("  - 양도소득세(국세)는 국세청 홈택스에서 신고·납부\n")
    w("  - 양도소득에 대한 지방소득세는 지방자치단체 세금 → 위택스에서 별도 신고\n")
    w("  - 홈택스 확인서에 '지방소득세' 항목이 없는 것은 정상입니다\n\n")

    w("■ 납부해야 할 지방소득세\n")
    w(f"  국세 산출세액 (홈택스 납부액) : {_fmt(form.national_tax_krw)} 원\n")
    w("  지방소득세율                  : 10%\n")
    w(f"  납부할 지방소득세             : {_fmt(form.local_tax_krw)} 원\n\n")

    if form.local_tax_krw <= 0:
        w("  ※ 납부할 지방소득세 없음 (산출세액 = 0)\n\n")
    else:
        w("■ 위택스 신고 절차\n")
        w("  1. 위택스(wetax.go.kr) 접속 → 로그인\n")
        w("  2. [신고하기] → [지방소득세] → [양도소득분]\n")
        w("  3. 과세기간 선택: 2025년 (1.1 ~ 12.31)\n")
        w("  4. 납세자 정보 입력\n")
        w(f"  5. 과세표준:    {_fmt(form.taxable_base_krw)} 원\n")
        w("  6. 세율:        10% (국세 산출세액의 10%)\n")
        w(f"  7. 산출세액:    {_fmt(form.local_tax_krw)} 원  ← 이 금액을 입력\n")
        w("  8. 납부 방법 선택 → 납부\n\n")

    w("■ 신고 기한\n")
    w(f"  {form.filing_period_end}\n")
    w("  ※ 홈택스 양도소득세 신고기한과 동일\n\n")

    w("■ 미신고·미납부 시 불이익\n")
    w("  - 무신고 가산세: 산출세액 x 20%\n")
    w("  - 납부지연 가산세: 미납세액 x 일수 x 0.022% (연 8.03%)\n\n")

    w("■ 홈택스 신고 후 위택스 자동 연동 여부\n")
    w("  홈택스에서 양도소득세 신고 완료 후 위택스로 자동 연동되지 않습니다.\n")
    w("  반드시 위택스에서 별도로 신고·납부하세요.\n\n")

    w("=" * 70 + "\n")
    w("  ※ 본 가이드는 SentinelQ가 자동 생성한 보조 자료입니다.\n")
    w("     정확한 세액은 세무사 또는 위택스 담당자에게 확인하세요.\n")
    w("=" * 70 + "\n")

    return buf.getvalue()


def export_wetax_guide(
    form: NTSCapitalGainsForm,
    out_dir: Path,
    stem: str = "wetax",
) -> Path:
    """위택스 안내 텍스트를 파일로 저장."""
    out_dir.mkdir(parents=True, exist_ok=True)
    guide_path = out_dir / f"{stem}_wetax_guide.txt"
    guide_path.write_text(build_wetax_guide(form), encoding="utf-8")
    return guide_path
