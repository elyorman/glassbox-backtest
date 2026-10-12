"""Read-only reference series and cash growth available to order sources."""

from datetime import date, datetime, timezone
from decimal import Context, Decimal, localcontext
import unittest

from quant_core.backtest import RunConfig, SourceSpec, run_backtest
from quant_core.data import Bar, DataMetadata, Dividend, Security, Snapshot, Split
from quant_core.data.rates import CashRateSeries
from quant_core.execution import ExecutionProfile, OrderRequest

META = DataMetadata("synthetic", datetime(2024, 1, 10, tzinfo=timezone.utc),
                    "fixed_synthetic_universe", True, "synthetic_explicit_sessions")
DAYS = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5), date(2024, 1, 8))
SECURITIES = (Security("A", "AAA", "SYNTHETIC"), Security("R", "RRR", "SYNTHETIC"), Security("X", "XXX", "SYNTHETIC"))
# 3.65% is 0.0001 a day; 7.3%, observed on Wednesday 2024-01-03, is 0.0002 a day.
RATES = CashRateSeries("test_source", "test_3m", META.retrieved_at,
                       ((date(2023, 12, 29), "0.0365"), (date(2024, 1, 3), "0.073")))


def snapshot(skip=None):
    # R splits 2-for-1 on DAYS[2] (20 to 10); X, never readable, pays a dividend and splits on DAYS[3] (30 to 15).
    closes = {"A": ("10",) * 5, "R": ("20", "20", "10", "10", "10"), "X": ("30", "30", "30", "15", "15")}
    bars = tuple(Bar(asset, day, price, price, price, price, "1000")
                 for asset, series in closes.items() for day, price in zip(DAYS, series)
                 if (asset, day) != skip)
    actions = (Dividend("R", DAYS[1], "1", DAYS[1]), Split("R", DAYS[2], new_shares=2, old_shares=1),
               Dividend("X", DAYS[1], "1", DAYS[1]), Split("X", DAYS[3], new_shares=2, old_shares=1))
    return Snapshot(DAYS, bars, META, SECURITIES, actions)


class Reader:
    """Calls `action(context)` at every close and keeps what it returns."""
    spec = SourceSpec("reader", "1", "0" * 64)

    def __init__(self, action):
        self.action, self.seen = action, []

    def orders(self, context):
        value = self.action(context)
        self.seen.append((context.as_of, value))
        return value if isinstance(value, tuple) and all(isinstance(v, OrderRequest) for v in value) else ()


def run(source, data=None, **options):
    options.setdefault("universe", ("A",))
    return run_backtest(data or snapshot(), source, RunConfig("100000", ExecutionProfile("0"), **options))


class ReferenceTests(unittest.TestCase):
    def test_references_are_readable_with_their_dividends_but_never_traded(self):
        reader = Reader(lambda c: (len(c.history("R")), tuple(d.security_id for d in c.dividends)))
        run(reader, references=("R",))
        self.assertEqual(reader.seen[0][1], (1, ()))
        self.assertEqual(reader.seen[1][1], (2, ("R",)))
        buyer = Reader(lambda c: (OrderRequest("R", "buy", "1"),) if c.as_of == DAYS[0] else ())
        result = run(buyer, references=("R",))
        self.assertEqual([(o.status, o.reason_code) for o in result.orders], [("rejected", "outside_universe")])
        self.assertEqual(result.fills, ())

    def test_reference_actions_appear_on_their_date_and_unreadable_ones_never(self):
        reader = Reader(lambda c: tuple((type(a).__name__, a.security_id) for a in c.splits + c.dividends))
        run(reader, references=("R",))
        seen = dict(reader.seen)
        self.assertEqual(seen[DAYS[0]], ())
        self.assertEqual(seen[DAYS[1]], (("Dividend", "R"),))
        self.assertEqual(seen[DAYS[2]], (("Split", "R"), ("Dividend", "R")))
        self.assertEqual(seen[DAYS[4]], (("Split", "R"), ("Dividend", "R")))

    def test_securities_outside_universe_and_references_stay_unreadable(self):
        with self.assertRaisesRegex(ValueError, "trading universe or references"):
            run(Reader(lambda c: c.history("X")), references=("R",))

    def test_references_must_be_known_and_outside_the_universe(self):
        for options in ({"references": ("A",)}, {"references": ("Z",)}, {"universe": (), "references": ("R",)}):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, "References must be known"):
                run(Reader(lambda c: ()), **options)
        with self.assertRaisesRegex(ValueError, "Duplicate reference"):
            RunConfig(references=("R", "R"))
        self.assertEqual(RunConfig(references=("X", "R")).references, ("R", "X"))

    def test_reference_data_errors_block_the_run(self):
        with self.assertRaisesRegex(ValueError, "missing_bar for R"):
            run(Reader(lambda c: ()), snapshot(skip=("R", DAYS[2])), references=("R",))
        run(Reader(lambda c: ()), snapshot(skip=("X", DAYS[2])), references=("R",))  # Unread X is ignored.


class CashGrowthTests(unittest.TestCase):
    def test_growth_compounds_daily_accruals_by_hand(self):
        reader = Reader(lambda c: c.cash_growth(DAYS[0], c.as_of))
        run(reader, cash_rates=RATES)
        growth = dict(reader.seen)
        self.assertEqual(growth[DAYS[0]], 1)
        self.assertEqual(growth[DAYS[1]], Decimal("1.0001"))
        # Thursday still uses 3.65%: the 7.3% was observed on Wednesday, not strictly before it.
        self.assertEqual(growth[DAYS[2]], Decimal("1.00020001"))
        self.assertEqual(growth[DAYS[3]], Decimal("1.000400050002"))
        # Friday to Monday is three calendar days at 7.3%.
        self.assertEqual(growth[DAYS[4]], growth[DAYS[3]] * (1 + Decimal("0.0006")))

    def test_cash_only_run_grows_exactly_like_cash_growth(self):
        reader = Reader(lambda c: c.cash_growth(DAYS[0], c.as_of))
        result = run(reader, cash_rates=RATES)
        # Exact because 100000 is a power of ten; other amounts agree to about 1e-24 relative.
        self.assertEqual(result.equity[-1].equity, 100000 * reader.seen[-1][1])

    def test_growth_ignores_the_callers_decimal_context(self):
        def low_precision(context):
            with localcontext(Context(prec=6)):
                return context.cash_growth(DAYS[0], context.as_of)

        reader = Reader(low_precision)
        result = run(reader, cash_rates=RATES)
        self.assertEqual(result.equity[-1].equity, 100000 * reader.seen[-1][1])

    def test_growth_cannot_look_past_as_of_or_off_calendar(self):
        cases = [(DAYS[0], DAYS[0], DAYS[1]),  # End after as_of.
                 (DAYS[4], date(2024, 1, 6), DAYS[4]),  # Saturday start.
                 (DAYS[4], DAYS[0], date(2024, 1, 7)),  # Sunday end.
                 (DAYS[4], DAYS[2], DAYS[1])]  # Start after end.
        for as_of, start, end in cases:
            action = lambda c: c.cash_growth(start, end) if c.as_of == as_of else ()
            with self.subTest(start=start, end=end), self.assertRaisesRegex(ValueError, "start <= end <= as_of"):
                run(Reader(action), cash_rates=RATES)
        with self.assertRaisesRegex(ValueError, "requires RunConfig.cash_rates"):
            run(Reader(lambda c: c.cash_growth(DAYS[0], DAYS[0])))


if __name__ == "__main__":
    unittest.main()
