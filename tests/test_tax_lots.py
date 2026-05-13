"""Tests for sentinelq.portfolio.tax_lots — T002 spec §6."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from sentinelq.adapters.kis_history import Transaction
from sentinelq.portfolio.tax_lots import (
    InsufficientLotsError,
    MissingFxRateError,
    TaxLotLedger,
)


def _kr_tx(
    side: str,
    qty: int,
    price: str,
    *,
    ticker: str = "005930",
    trade_date: date = date(2025, 1, 2),
    fee: str = "0",
    tax: str = "0",
) -> Transaction:
    return Transaction(
        trade_date=trade_date,
        settle_date=trade_date,
        ticker=ticker,
        market="KR",
        side=side,  # type: ignore[arg-type]
        quantity=qty,
        price=Decimal(price),
        currency="KRW",
        fee=Decimal(fee),
        tax=Decimal(tax),
        fx_rate=None,
    )


def _us_tx(
    side: str,
    qty: int,
    price: str,
    fx_rate: str | None,
    *,
    ticker: str = "AAPL",
    trade_date: date = date(2025, 1, 2),
    fee: str = "0",
    tax: str = "0",
) -> Transaction:
    return Transaction(
        trade_date=trade_date,
        settle_date=trade_date,
        ticker=ticker,
        market="US",
        side=side,  # type: ignore[arg-type]
        quantity=qty,
        price=Decimal(price),
        currency="USD",
        fee=Decimal(fee),
        tax=Decimal(tax),
        fx_rate=Decimal(fx_rate) if fx_rate is not None else None,
    )


# ---- 정확성 그룹 ----


def test_single_buy_single_sell_kr() -> None:
    ledger = TaxLotLedger()
    ledger.apply(_kr_tx("BUY", 10, "70000", trade_date=date(2025, 1, 2)))
    sale = ledger.apply(_kr_tx("SELL", 10, "80000", trade_date=date(2025, 6, 1)))
    assert sale is not None
    # gain = (80000-70000) * 10 = 100000
    assert sale.total_realized_gain_krw == Decimal("100000")
    assert sale.total_qty == 10
    assert len(sale.consumptions) == 1
    assert sale.consumptions[0].holding_days == (date(2025, 6, 1) - date(2025, 1, 2)).days
    assert ledger.open_lots("KR", "005930") == []


def test_partial_sell_kr() -> None:
    ledger = TaxLotLedger()
    ledger.apply(_kr_tx("BUY", 10, "70000"))
    s1 = ledger.apply(_kr_tx("SELL", 4, "80000"))
    s2 = ledger.apply(_kr_tx("SELL", 6, "90000"))
    assert s1 is not None and s2 is not None
    assert s1.total_realized_gain_krw == Decimal("40000")
    assert s2.total_realized_gain_krw == Decimal("120000")
    assert ledger.open_lots("KR", "005930") == []


def test_multi_buy_fifo_order_kr() -> None:
    ledger = TaxLotLedger()
    ledger.apply(_kr_tx("BUY", 5, "70000", trade_date=date(2025, 1, 2)))
    ledger.apply(_kr_tx("BUY", 5, "80000", trade_date=date(2025, 2, 2)))
    sale = ledger.apply(_kr_tx("SELL", 5, "90000", trade_date=date(2025, 3, 2)))
    assert sale is not None
    # First lot consumed entirely first
    assert len(sale.consumptions) == 1
    assert sale.consumptions[0].acquired_date == date(2025, 1, 2)
    assert sale.total_realized_gain_krw == Decimal("100000")  # (90000-70000)*5


def test_three_buy_partial_sell_kr() -> None:
    ledger = TaxLotLedger()
    ledger.apply(_kr_tx("BUY", 3, "100", trade_date=date(2025, 1, 1)))
    ledger.apply(_kr_tx("BUY", 3, "200", trade_date=date(2025, 1, 2)))
    ledger.apply(_kr_tx("BUY", 3, "300", trade_date=date(2025, 1, 3)))
    sale = ledger.apply(_kr_tx("SELL", 5, "500", trade_date=date(2025, 1, 4)))
    assert sale is not None
    # Consumes lot1 (3 @ 100) + lot2 (2 @ 200)
    assert len(sale.consumptions) == 2
    assert sale.consumptions[0].qty == 3
    assert sale.consumptions[0].acquired_date == date(2025, 1, 1)
    assert sale.consumptions[1].qty == 2
    assert sale.consumptions[1].acquired_date == date(2025, 1, 2)
    # acq_cost = 3*100 + 2*200 = 700; proceeds = 5*500 = 2500; gain = 1800
    assert sale.total_acq_cost_krw == Decimal("700")
    assert sale.total_proceeds_krw == Decimal("2500")
    assert sale.total_realized_gain_krw == Decimal("1800")
    # Remaining: lot2 has 1 left @ 200, lot3 intact @ 300
    open_lots = ledger.open_lots("KR", "005930")
    assert len(open_lots) == 2
    assert open_lots[0].remaining_qty == 1
    assert open_lots[1].remaining_qty == 3


def test_us_with_fx_conversion() -> None:
    ledger = TaxLotLedger()
    # Buy: 10 shares @ $100, fx=1300 → cost_krw = 10*100*1300 = 1,300,000
    ledger.apply(_us_tx("BUY", 10, "100", "1300", trade_date=date(2025, 1, 2)))
    # Sell: 10 shares @ $120, fx=1400 → proceeds_krw = 10*120*1400 = 1,680,000
    sale = ledger.apply(_us_tx("SELL", 10, "120", "1400", trade_date=date(2025, 6, 1)))
    assert sale is not None
    assert sale.total_acq_cost_krw == Decimal("1300000")
    assert sale.total_proceeds_krw == Decimal("1680000")
    assert sale.total_realized_gain_krw == Decimal("380000")


def test_same_ticker_kr_us_separate() -> None:
    """Same string ticker on KR vs US → separate matching queues."""
    ledger = TaxLotLedger()
    # Hypothetical: a ticker "TEST" exists on both markets
    kr = Transaction(
        trade_date=date(2025, 1, 2),
        settle_date=date(2025, 1, 2),
        ticker="TEST",
        market="KR",
        side="BUY",
        quantity=5,
        price=Decimal("1000"),
        currency="KRW",
        fee=Decimal("0"),
        tax=Decimal("0"),
        fx_rate=None,
    )
    us = Transaction(
        trade_date=date(2025, 1, 2),
        settle_date=date(2025, 1, 2),
        ticker="TEST",
        market="US",
        side="BUY",
        quantity=5,
        price=Decimal("10"),
        currency="USD",
        fee=Decimal("0"),
        tax=Decimal("0"),
        fx_rate=Decimal("1300"),
    )
    ledger.apply(kr)
    ledger.apply(us)
    assert len(ledger.open_lots("KR", "TEST")) == 1
    assert len(ledger.open_lots("US", "TEST")) == 1
    # SELL KR side does not consume US lot
    sell_kr = Transaction(
        trade_date=date(2025, 2, 2),
        settle_date=date(2025, 2, 2),
        ticker="TEST",
        market="KR",
        side="SELL",
        quantity=5,
        price=Decimal("1500"),
        currency="KRW",
        fee=Decimal("0"),
        tax=Decimal("0"),
        fx_rate=None,
    )
    sale = ledger.apply(sell_kr)
    assert sale is not None
    assert sale.market == "KR"
    assert len(ledger.open_lots("KR", "TEST")) == 0
    assert len(ledger.open_lots("US", "TEST")) == 1


def test_buy_fees_increase_cost_basis() -> None:
    ledger = TaxLotLedger()
    # Buy 10 @ 1000, fee=50, tax=20 → total cost = 10070; per share = 1007
    ledger.apply(_kr_tx("BUY", 10, "1000", fee="50", tax="20"))
    lots = ledger.open_lots("KR", "005930")
    assert lots[0].cost_per_share_krw == Decimal("1007")


def test_sell_fees_decrease_proceeds() -> None:
    ledger = TaxLotLedger()
    ledger.apply(_kr_tx("BUY", 10, "1000"))
    # Sell 10 @ 2000, fee=30, tax=70 → net proceeds = 20000 - 100 = 19900
    sale = ledger.apply(_kr_tx("SELL", 10, "2000", fee="30", tax="70"))
    assert sale is not None
    assert sale.total_proceeds_krw == Decimal("19900")
    assert sale.total_realized_gain_krw == Decimal("9900")


def test_invariant_sum_gain_equals_proceeds_minus_cost() -> None:
    ledger = TaxLotLedger()
    txs = [
        _kr_tx("BUY", 10, "100", trade_date=date(2025, 1, 1)),
        _kr_tx("BUY", 20, "150", trade_date=date(2025, 1, 5)),
        _kr_tx("SELL", 15, "200", trade_date=date(2025, 2, 1), fee="50"),
        _kr_tx("BUY", 5, "180", trade_date=date(2025, 3, 1)),
        _kr_tx("SELL", 10, "250", trade_date=date(2025, 4, 1), fee="30", tax="20"),
    ]
    ledger.apply_all(txs)
    total_gain = sum((r.total_realized_gain_krw for r in ledger.realizations()), Decimal(0))
    total_proc = sum((r.total_proceeds_krw for r in ledger.realizations()), Decimal(0))
    total_acq = sum((r.total_acq_cost_krw for r in ledger.realizations()), Decimal(0))
    assert total_gain == total_proc - total_acq
    # consumption-level invariant
    for r in ledger.realizations():
        for c in r.consumptions:
            assert c.realized_gain_krw == c.sale_proceeds_krw - c.acq_cost_krw


# ---- 견고성 그룹 ----


def test_short_sale_raises() -> None:
    ledger = TaxLotLedger()
    ledger.apply(_kr_tx("BUY", 5, "1000"))
    with pytest.raises(InsufficientLotsError):
        ledger.apply(_kr_tx("SELL", 6, "1100"))


def test_short_sale_no_lots_raises() -> None:
    ledger = TaxLotLedger()
    with pytest.raises(InsufficientLotsError):
        ledger.apply(_kr_tx("SELL", 1, "1000"))


def test_us_missing_fx_raises_on_buy() -> None:
    ledger = TaxLotLedger()
    with pytest.raises(MissingFxRateError):
        ledger.apply(_us_tx("BUY", 1, "100", None))


def test_us_missing_fx_raises_on_sell() -> None:
    ledger = TaxLotLedger()
    ledger.apply(_us_tx("BUY", 1, "100", "1300"))
    with pytest.raises(MissingFxRateError):
        ledger.apply(_us_tx("SELL", 1, "120", None))


def test_zero_quantity_raises() -> None:
    ledger = TaxLotLedger()
    with pytest.raises(ValueError):
        ledger.apply(_kr_tx("BUY", 0, "1000"))


def test_negative_quantity_raises() -> None:
    ledger = TaxLotLedger()
    with pytest.raises(ValueError):
        ledger.apply(_kr_tx("BUY", -1, "1000"))


def test_kr_non_krw_currency_raises() -> None:
    ledger = TaxLotLedger()
    bad = Transaction(
        trade_date=date(2025, 1, 2),
        settle_date=date(2025, 1, 2),
        ticker="005930",
        market="KR",
        side="BUY",
        quantity=1,
        price=Decimal("1000"),
        currency="USD",  # invalid for KR
        fee=Decimal("0"),
        tax=Decimal("0"),
        fx_rate=Decimal("1300"),
    )
    with pytest.raises(ValueError):
        ledger.apply(bad)


def test_empty_input() -> None:
    ledger = TaxLotLedger()
    assert ledger.apply_all([]) == []
    assert ledger.realizations() == []
    assert ledger.open_lots_all() == {}


def test_idempotent_apply_all() -> None:
    """Two fresh ledgers fed the same input produce bit-equal results."""
    txs = [
        _kr_tx("BUY", 10, "100", trade_date=date(2025, 1, 1)),
        _kr_tx("BUY", 10, "150", trade_date=date(2025, 1, 5), fee="20"),
        _kr_tx("SELL", 15, "200", trade_date=date(2025, 2, 1), fee="10", tax="5"),
    ]
    a = TaxLotLedger()
    b = TaxLotLedger()
    a.apply_all(txs)
    b.apply_all(txs)
    assert a.realizations() == b.realizations()
    assert a.open_lots_all() == b.open_lots_all()


# ---- 보조 ----


def test_open_lots_query() -> None:
    ledger = TaxLotLedger()
    ledger.apply(_kr_tx("BUY", 5, "100"))
    ledger.apply(_kr_tx("BUY", 3, "200", ticker="000660"))
    all_lots = ledger.open_lots_all()
    assert set(all_lots.keys()) == {("KR", "005930"), ("KR", "000660")}
    assert ledger.open_lots("KR", "999999") == []


def test_holding_period_days() -> None:
    ledger = TaxLotLedger()
    ledger.apply(_kr_tx("BUY", 5, "100", trade_date=date(2025, 1, 1)))
    sale = ledger.apply(_kr_tx("SELL", 5, "150", trade_date=date(2025, 12, 31)))
    assert sale is not None
    assert sale.consumptions[0].holding_days == 364


def test_invalid_side_raises() -> None:
    ledger = TaxLotLedger()
    bad = Transaction(
        trade_date=date(2025, 1, 2),
        settle_date=date(2025, 1, 2),
        ticker="005930",
        market="KR",
        side="HOLD",  # type: ignore[arg-type]
        quantity=1,
        price=Decimal("1000"),
        currency="KRW",
        fee=Decimal("0"),
        tax=Decimal("0"),
        fx_rate=None,
    )
    with pytest.raises(ValueError):
        ledger.apply(bad)
