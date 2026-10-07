"""Daily portfolio research API. Strategies supply orders through OrderSource."""

from quant_core.backtest.contracts import BacktestResult, RunConfig, SourceSpec
from quant_core.backtest.engine import run_backtest
from quant_core.backtest.sources import OrderSchedule, ScheduledOrder, SessionContext

__all__ = ["BacktestResult", "RunConfig", "SourceSpec", "run_backtest",
           "OrderSchedule", "ScheduledOrder", "SessionContext"]
