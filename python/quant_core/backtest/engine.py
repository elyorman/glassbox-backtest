"""Deterministic shared-cash simulation, independent of strategy and data vendors."""

from collections import defaultdict
from dataclasses import replace
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path
import sys
from types import MappingProxyType

from quant_core import __version__
from quant_core.backtest.contracts import (
    BacktestResult, CashMovement, CorporateActionRecord, DailyState, FillRecord,
    OrderRecord, RunConfig, RunManifest, RunSummary, SourceSpec,
)
from quant_core.backtest.sources import OrderBatch, OrderSchedule, OrderSource, SessionContext
from quant_core.data import CashDelisting, Dividend, Snapshot, Split, require_raw_volume
from quant_core.data.quality import check_quality
from quant_core.data.rates import MAX_RATE_AGE_DAYS
from quant_core.execution import OrderRequest
from quant_core.portfolio import PortfolioLedger, Receivable, ZERO, reconciles
from quant_core.provenance import content_hash
from quant_core.risk import RiskBook, RiskDecision, assess_buy, portfolio_breaches, portfolio_heat, reserve_buy
from quant_core.sizing import EntryIntent, normalized_history, size_entry, wilder_atr


def _engine_hash():
    root = Path(__file__).resolve().parents[1]
    return content_hash(tuple((path.relative_to(root).as_posix(), path.read_text(encoding="utf-8"))
                              for path in sorted(root.rglob("*.py"))))


def run_backtest(snapshot: Snapshot, source: OrderSource, config: RunConfig | None = None) -> BacktestResult:
    """Run a long-only daily-market portfolio with an explicit, immutable contract."""
    if not isinstance(snapshot, Snapshot):
        raise ValueError("Backtest requires a normalized Snapshot")
    config = config if config is not None else RunConfig()
    if not isinstance(config, RunConfig):
        raise ValueError("Backtest requires RunConfig")
    # Fresh context prevents caller precision, rounding, or traps changing results.
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        return _Simulation(snapshot, source, config).run()


class _Simulation:
    def __init__(self, snapshot, source, config):
        self.snapshot = snapshot
        self.source = source
        self.spec = source.spec
        if not isinstance(self.spec, SourceSpec):
            raise ValueError("Order source requires SourceSpec")
        self.registry = {s.security_id: s for s in snapshot.securities}
        universe = config.universe or tuple(sorted(self.registry))
        if any(a not in self.registry for a in universe):
            raise ValueError("Universe contains unknown security IDs")
        if any(a not in self.registry or a in universe for a in config.references):
            raise ValueError("References must be known securities outside the trading universe")
        start, end = config.start or snapshot.sessions[0], config.end or snapshot.sessions[-1]
        if start not in snapshot.sessions or end not in snapshot.sessions or start > end:
            raise ValueError("Run boundaries must be supplied calendar sessions, start <= end")
        self.config = replace(config, start=start, end=end, universe=universe)
        if config.risk is not None:
            require_raw_volume(snapshot.metadata, "Risk liquidity limits")
        validator = getattr(source, "validate_run", None)
        if validator is not None:
            if not callable(validator):
                raise ValueError("Source validate_run hook must be callable")
            validator(snapshot, self.config)
        if source.spec != self.spec:
            raise ValueError("Order source metadata changed during preflight")
        self.sessions = tuple(d for d in snapshot.sessions if start <= d <= end)
        if config.cash_rates is not None:
            for previous in self.sessions[:-1]:
                config.cash_rates.rate_before(previous)  # Refuse missing or stale rates before simulating.
        if isinstance(source, OrderSchedule):
            calendar = set(snapshot.sessions)
            if any(entry.signal_date not in calendar for entry in source.entries):
                raise ValueError("Scheduled signal date lies outside the supplied calendar")
        quality = check_quality(snapshot, strict_discontinuities=config.strict_discontinuities)
        watched = set(universe) | set(config.references)
        errors = [i for i in quality.issues if i.severity == "error" and i.security_id in watched
                  and (i.session is None or i.session <= end)]
        blocking = [issue for issue in errors
                    if config.data_policy == "strict" or issue.code != "missing_bar"]
        if blocking:
            first = blocking[0]
            raise ValueError(f"Data quality error: {first.code} for {first.security_id} on {first.session}")
        if not snapshot.metadata.actions_complete and config.actions_policy == "require_complete":
            raise ValueError("Corporate-action completeness is unqualified; opt into a diagnostic explicitly")
        cash_yield = ("cash return zero" if config.cash_rates is None else
                      f"idle cash at each session's close earns {config.cash_rates.series} "
                      f"({config.cash_rates.source}) until the next session: the latest observation strictly "
                      f"before the earlier session (at most {MAX_RATE_AGE_DAYS} days old), simple ACT/365 over "
                      "the calendar days between them, credited at the start of the next session before "
                      "corporate actions, stops and orders; unpaid dividend receivables earn nothing")
        assumptions = (
            f"USD long-only; no leverage; {cash_yield}",
            "Decimal precision 28, half-even rounding; intermediate money is not rounded to cents",
            ("Close-generated market requests execute once at the next supplied session open"
             if config.execution_delay_sessions == 1 else
             "Close-generated market requests execute once at the second supplied session open"),
            "Daily open plus adverse slippage is an approximation, not an opening-auction model",
            "Sells precede buys; priority ascending, then security ID, then canonical request hash",
            "Economic proceeds reuse; no historical settled-cash brokerage model",
            "Full fills or rejection; no automatic resizing; zero-volume bars cannot fill",
            "Average-cost basis includes entry fees; realized sale P&L includes exit fees",
            "Dividends accrue before ex-date fills; cash arrives at the first session on/after payment",
            "Split fractions are retained; no broker-specific cash-in-lieu or share rounding",
            "Missing held-security marks and unresolved held delistings invalidate the run",
            "Final positions remain open; no forced final-close liquidation",
            "Source completeness and universe policy are declarations, not independent qualification",
            "Order-source artifact hash is supplied by its author; callbacks are not a Python sandbox",
        )
        if config.data_policy != "strict" or config.actions_policy != "require_complete":
            assumptions += ("Diagnostic data policies are enabled; results are unqualified",)
        assumptions += (
            "Protective long stops: gap at open, otherwise stop trigger plus adverse costs; no targets/trailing",
            "Opening stops precede scheduled orders; intraday stops follow all opening orders",
            "Daily volume zero is an ex-post no-fill check; past ADV is a capacity proxy, not auction liquidity",
            "Protected holdings cannot be pyramided; cash dividends do not adjust stop triggers",
        )
        if config.risk:
            assumptions += (
                "Risk enabled: every buy requires a stop; limits are admission rules, not mark-to-market guarantees",
                "Close sizing reserves cash without anticipated sales; open gates reject rather than resize",
                "Group labels are explicit static assumptions, not point-in-time sectors or ETF look-through",
                "Drawdown is observed at close; halt liquidates next open and stays latched through run end",
                "Stop-risk/portfolio heat are modeled budgets; gaps and costs can exceed planned losses",
            )
        if config.execution_delay_sessions == 2:
            assumptions += ("Registered delay diagnostic: original close signals/quantities execute at the second session open",)
        self.manifest = RunManifest(4, __version__, sys.version.split()[0], _engine_hash(), quality.dataset_hash,
                                    content_hash(self.config), self.spec, snapshot.metadata,
                                    self.config, quality.issues, assumptions)
        self.bars = defaultdict(dict)
        histories = defaultdict(list)
        for bar in snapshot.bars:
            self.bars[bar.session][bar.security_id] = bar
            histories[bar.security_id].append(bar)
        self.histories = MappingProxyType({a: tuple(b) for a, b in histories.items()})
        self.history_dates = MappingProxyType({a: tuple(b.session for b in bars)
                                               for a, bars in self.histories.items()})
        self.splits = tuple(a for a in snapshot.actions if isinstance(a, Split))
        self.dividends = tuple(a for a in snapshot.actions if isinstance(a, Dividend))
        self.actions = defaultdict(list)
        for action in snapshot.actions:
            self.actions[action.session].append(action)
        self.ledger = PortfolioLedger(config.initial_cash)
        self.orders = []
        self.pending = []  # Indices into immutable order records, replaced on status transitions.
        self.fills = []
        self.cash_movements = []
        self.action_records = []
        self.states = []
        self.audit_cash = ZERO
        self.peak = config.initial_cash
        self.previous_equity = config.initial_cash
        self.stops = {}  # asset -> (current-share-unit trigger, original signal date)
        self.risk_decisions = []
        self.signal_decisions = []
        self.risk_inputs = {}  # order ID -> (past average volume, dollar volume, ATR, method)
        self.halted = False
        self.budget_scale = Decimal("1")
        self.drawdown = ZERO
        self._cash(start, "initial_capital", None, config.initial_cash)

    def _cash(self, day, kind, asset, amount, order_id=None):
        self.audit_cash += amount
        if not reconciles(self.audit_cash, self.ledger.cash, self.ledger.cash):
            raise ArithmeticError("Cash movement ledger does not reconcile")
        self.cash_movements.append(CashMovement(len(self.cash_movements) + 1, day, kind, asset,
                                                amount, self.ledger.cash, order_id))

    def _interest(self, previous, day):
        amount = self.config.cash_rates.accrual(self.ledger.cash, previous, day)
        if amount:
            self.ledger.credit_interest(amount)
            self._cash(day, "interest", None, amount)

    def _action(self, day, kind, asset, quantity, amount, ratio=None, pay_date=None, pnl=None):
        self.action_records.append(CorporateActionRecord(len(self.action_records) + 1, day, kind,
                                                         asset, quantity, amount, ratio, pay_date, pnl))

    def _corporate_actions(self, day):
        # Explicit phase order, independent of action input order.
        actions = self.actions.get(day, ())
        for action in actions:
            if not isinstance(action, Split):
                continue
            position = self.ledger.positions.get(action.security_id)
            quantity = ZERO
            if position is not None:
                position.quantity = action.adjust_quantity(position.quantity)
                quantity = position.quantity
            if action.security_id in self.stops:
                stop, signal_date = self.stops[action.security_id]
                self.stops[action.security_id] = (action.adjust_price(stop), signal_date)
            for index in self.pending:
                order = self.orders[index]
                if order.request.security_id == action.security_id:
                    self.orders[index] = replace(
                        order, adjusted_quantity=action.adjust_quantity(order.adjusted_quantity),
                        adjusted_stop_price=(action.adjust_price(order.adjusted_stop_price)
                                             if order.adjusted_stop_price is not None else None))
                    if order.order_id in self.risk_inputs:
                        volume, dollars, atr, method = self.risk_inputs[order.order_id]
                        self.risk_inputs[order.order_id] = (action.adjust_quantity(volume), dollars,
                                                          action.adjust_price(atr) if atr is not None else None, method)
            self._action(day, "split", action.security_id, quantity, ZERO, ratio=action.ratio)
        for action in actions:
            if not isinstance(action, Dividend):
                continue
            position = self.ledger.positions.get(action.security_id)
            quantity = position.quantity if position else ZERO
            amount = quantity * action.amount
            if amount:
                self.ledger.receivables.append(Receivable(action.security_id, day, action.pay_date, amount))
                self.ledger.dividend_income += amount
            self._action(day, "dividend_entitlement", action.security_id, quantity, amount, pay_date=action.pay_date)
        for action in actions:
            if not isinstance(action, CashDelisting):
                continue
            position = self.ledger.positions.get(action.security_id)
            quantity = position.quantity if position else ZERO
            amount = quantity * action.amount
            pnl = self.ledger.sell(action.security_id, quantity, amount) if position else ZERO
            self.stops.pop(action.security_id, None)
            if position:
                self._cash(day, "delisting_settlement", action.security_id, amount)
            self._action(day, "cash_delisting", action.security_id, quantity, amount, pnl=pnl)
        unpaid = []
        for receivable in self.ledger.receivables:
            if receivable.pay_date <= day:
                self.ledger.cash += receivable.amount
                self._cash(day, "dividend_payment", receivable.security_id, receivable.amount)
                self._action(day, "dividend_payment", receivable.security_id, ZERO, receivable.amount,
                             pay_date=receivable.pay_date)
            else:
                unpaid.append(receivable)
        self.ledger.receivables = unpaid

    def _reject(self, index, day, code):
        order = self.orders[index]
        self.orders[index] = replace(order, processed_date=day, status="rejected", reason_code=code)
        if (self.config.risk and order.request.side == "buy" and order.order_id in self.risk_inputs
                and not any(r.order_id == order.order_id and r.phase == "open" for r in self.risk_decisions)):
            volume, dollars, atr, method = self.risk_inputs[order.order_id]
            bar = self.bars.get(day, {}).get(order.request.security_id)
            self._risk_record(day, "open", order.request.security_id, order.order_id, method,
                              "rejected", (code,), order.adjusted_quantity,
                              reference=bar.open if bar else None, stop=order.adjusted_stop_price,
                              atr=atr, volume=volume, dollars=dollars)

    def _book(self, marks):
        values = {a: p.quantity * marks[a] for a, p in self.ledger.positions.items()}
        equity = self.ledger.cash + sum(values.values(), ZERO) + sum((r.amount for r in self.ledger.receivables), ZERO)
        return RiskBook(self.ledger.cash, equity, values,
                        {a: p.quantity for a, p in self.ledger.positions.items()},
                        {a: s[0] for a, s in self.stops.items() if a in values})

    def _risk_record(self, day, phase, asset, order_id, method, status, codes, requested=ZERO,
                     approved=ZERO, reference=None, stop=None, atr=None, volume=None,
                     dollars=None, equity=None, loss=None, book=None):
        self.risk_decisions.append(RiskDecision(
            len(self.risk_decisions) + 1, day, phase, asset, order_id, method, status,
            tuple(codes), requested, approved, reference, stop, atr, volume, dollars,
            equity, loss, self.budget_scale, self.drawdown, self.halted,
            sum(book.values.values(), ZERO) / book.equity if book and book.equity > 0 else None,
            book.cash / book.equity if book and book.equity > 0 else None,
            portfolio_heat(book, self.config.execution) / book.equity if book and book.equity > 0 else None))

    def _fill(self, index, day, raw_price, kind="market_open", trigger=None):
        order = self.orders[index]
        request, quantity = order.request, order.adjusted_quantity
        asset = request.security_id
        price, notional, fees, slippage = self.config.execution.quote(raw_price, quantity, request.side)
        if request.side == "buy":
            self.ledger.buy(asset, quantity, notional, fees, slippage)
            pnl, cash_delta = None, -(notional + fees)
            if order.adjusted_stop_price is not None:
                self.stops[asset] = (order.adjusted_stop_price, order.signal_date)
        else:
            pnl = self.ledger.sell(asset, quantity, notional, fees, slippage)
            cash_delta = notional - fees
            if asset not in self.ledger.positions:
                self.stops.pop(asset, None)
        fill_id = f"fill-{len(self.fills) + 1:06d}"
        after = self.ledger.positions.get(asset)
        self.fills.append(FillRecord(
            fill_id, order.order_id, order.signal_date, day, asset, self.registry[asset].symbol,
            request.side, quantity, self.bars[day][asset].open, price, notional, fees, slippage,
            pnl, self.ledger.cash, after.quantity if after else ZERO, kind, trigger, raw_price))
        self._cash(day, request.side, asset, cash_delta, order.order_id)
        self.orders[index] = replace(order, processed_date=day, status="filled",
                                     reason_code="filled" if kind == "market_open" else kind, fill_id=fill_id)

    def _stop_orders(self, day, opening):
        for asset in sorted(tuple(self.stops)):
            if asset not in self.ledger.positions:
                continue
            stop, signal_date = self.stops[asset]
            bar = self.bars.get(day, {}).get(asset)
            if bar is None:
                raise ValueError(f"Missing held-security stop bar: {asset} on {day}")
            hit = bar.open <= stop if opening else bar.open > stop and bar.low <= stop
            if not hit:
                continue
            raw_price = bar.open if bar.open <= stop else stop
            kind = "stop_gap" if bar.open <= stop else "stop_intraday"
            request = OrderRequest(asset, "sell", self.ledger.positions[asset].quantity, reason=kind)
            index = self._append_order(day, day, request, signal_date=signal_date)
            if bar.volume == 0:
                self._reject(index, day, "zero_volume")
                continue
            _, proceeds, fees, _ = self.config.execution.quote(raw_price, request.quantity, "sell")
            if self.ledger.cash + proceeds < fees:
                self._reject(index, day, "insufficient_cash_for_fees")
                continue
            self._fill(index, day, raw_price, kind, stop)

    def _execute(self, day):
        for index in self.pending:
            order = self.orders[index]
            if order.eligible_date != day:
                continue
            request = order.request
            asset = request.security_id
            security = self.registry[asset]
            bar = self.bars.get(day, {}).get(asset)
            if not security.active_on(day):
                self._reject(index, day, "outside_security_lifetime")
                continue
            if bar is None:
                self._reject(index, day, "missing_execution_bar")
                continue
            if bar.volume == 0:
                self._reject(index, day, "zero_volume")
                continue
            quantity = order.adjusted_quantity
            position = self.ledger.positions.get(asset)
            held = position.quantity if position else ZERO
            if request.side == "sell" and quantity > held:
                self._reject(index, day, "insufficient_position")
                continue
            if request.side == "buy":
                stop = order.adjusted_stop_price
                if held and (stop is not None or asset in self.stops):
                    self._reject(index, day, "pyramiding_unsupported")
                    continue
                if stop is not None and stop >= bar.open:
                    self._reject(index, day, "entry_open_below_stop")
                    continue
                if self.config.risk:
                    marks = {}
                    for held_asset in self.ledger.positions:
                        held_bar = self.bars.get(day, {}).get(held_asset)
                        if held_bar is None:
                            raise ValueError(f"Missing held-security opening risk mark: {held_asset} on {day}")
                        marks[held_asset] = held_bar.open
                    book = self._book(marks)
                    volume, dollars, atr, method = self.risk_inputs[order.order_id]
                    codes, loss = assess_buy(self.config.risk, self.config.execution, book, asset,
                                              quantity, bar.open, stop, volume, self.budget_scale)
                    self._risk_record(day, "open", asset, order.order_id, method,
                                      "rejected" if codes else "approved", codes or ("within_limits",),
                                      quantity, ZERO if codes else quantity, bar.open, stop, atr,
                                      volume, dollars, book.equity, loss)
                    if codes:
                        self._reject(index, day, "risk:" + ",".join(codes))
                        continue
            price, notional, fees, slippage = self.config.execution.quote(bar.open, quantity, request.side)
            if request.side == "buy" and notional + fees > self.ledger.cash:
                self._reject(index, day, "insufficient_cash")
                continue
            if request.side == "sell" and self.ledger.cash + notional < fees:
                self._reject(index, day, "insufficient_cash_for_fees")
                continue
            self._fill(index, day, bar.open)
        self.pending = [index for index in self.pending if self.orders[index].status == "pending"]

    def _state(self, day):
        current_bars = self.bars.get(day, {})
        for asset in self.ledger.positions:
            if not self.registry[asset].active_on(day):
                raise ValueError(f"Unresolved held delisting: {asset} on {day}")
            if asset not in current_bars:
                raise ValueError(f"Missing held-security valuation bar: {asset} on {day}")
        marks = {asset: current_bars[asset].close for asset in self.ledger.positions}
        values = self.ledger.values(marks)
        equity = self.ledger.assert_identity(values)
        self.peak = max(self.peak, equity)
        session_return = equity / self.previous_equity - 1 if self.previous_equity else None
        state = DailyState(day, self.ledger.cash, sum((r.amount for r in self.ledger.receivables), ZERO),
                           sum((v.market_value for v in values), ZERO), equity, self.ledger.realized_pnl,
                           sum((v.unrealized_pnl for v in values), ZERO), self.ledger.dividend_income,
                           self.ledger.fees, self.ledger.slippage, session_return, 1 - equity / self.peak, values,
                           self.ledger.interest_income)
        self.previous_equity = equity
        self.states.append(state)
        return state

    def _append_order(self, day, next_day, request, code=None, signal_date=None):
        status = "rejected" if code else ("pending" if next_day else "expired")
        self.orders.append(OrderRecord(
            f"order-{len(self.orders) + 1:06d}", signal_date or day, next_day,
            day if status != "pending" else None, request, request.quantity, status,
            code or ("pending" if next_day else "no_next_session"),
            adjusted_stop_price=request.stop_price))
        return len(self.orders) - 1

    def _signal_code(self, request, day):
        if request.security_id not in self.registry:
            return "unknown_security"
        if request.security_id not in self.config.universe:
            return "outside_universe"
        if not self.registry[request.security_id].active_on(day):
            return "outside_security_lifetime"
        if request.security_id not in self.bars.get(day, {}):
            return "missing_signal_bar"
        return None

    def _plan_entry(self, item, context, book, next_day):
        """Causal close plan. Raw quantities reject in full; sized intents may be capped."""
        policy, execution = self.config.risk, self.config.execution
        day, asset = context.as_of, item.security_id
        equity_reference = book.equity
        intent = isinstance(item, EntryIntent)
        method = item.method if intent else "explicit_quantity"
        quantity = ZERO if intent else item.quantity
        stop, atr, volume, dollars, loss, reference = item.stop_price, None, None, None, None, None
        code = self._signal_code(item, day)
        if code is None and self.halted:
            code = "drawdown_halt"
        if code is None and book.equity <= 0:
            code = "nonpositive_equity"
        if code is None:
            history = normalized_history(context.history(asset), context.splits)
            reference = history[-1].close
            expected = tuple(d for d in self.snapshot.sessions if history[0].session <= d <= day)
            if tuple(b.session for b in history) != expected:
                code = "missing_risk_history"
            elif len(history) < policy.volume_lookback:
                code = "insufficient_liquidity_history"
            else:
                window = history[-policy.volume_lookback:]
                volume = sum((b.volume for b in window), ZERO) / policy.volume_lookback
                dollars = sum((b.volume * b.close for b in window), ZERO) / policy.volume_lookback
                if dollars < policy.min_average_dollar_volume or volume <= 0:
                    code = "insufficient_liquidity"
            if code is None and intent and item.method == "atr":
                atr = wilder_atr(history, item.atr_period)
                if atr is None:
                    code = "insufficient_atr_history"
                elif atr <= 0:
                    code = "zero_atr"
                else:
                    stop = reference - item.atr_multiple * atr
            if code is None and (stop is None or stop <= 0 or stop >= reference):
                code = "missing_protective_stop" if stop is None else "invalid_stop_distance"
            if code is None and intent:
                quantity = size_entry(item, book.equity, reference, stop, execution, self.budget_scale)
            if code is None and quantity <= 0:
                code = "below_one_share"
        requested = quantity
        codes = (code,) if code else ()
        if not codes:
            codes, loss = assess_buy(policy, execution, book, asset, quantity, reference,
                                     stop, volume, self.budget_scale)
            if intent and codes:
                # Constraints are monotone in new shares. Find the largest admissible integer.
                low, high = 0, int(quantity)
                while low < high:
                    middle = (low + high + 1) // 2
                    failures, _ = assess_buy(policy, execution, book, asset, Decimal(middle),
                                             reference, stop, volume, self.budget_scale)
                    if failures:
                        high = middle - 1
                    else:
                        low = middle
                quantity = Decimal(low)
                if quantity:
                    _, loss = assess_buy(policy, execution, book, asset, quantity, reference,
                                          stop, volume, self.budget_scale)
        approved = quantity > 0 and (not codes or intent and code is None and quantity < requested)
        order_index = None
        if approved:
            request = (OrderRequest(asset, "buy", quantity, item.priority, item.reason, stop)
                       if intent else item)
            order_index = self._append_order(day, next_day, request)
            self.risk_inputs[self.orders[order_index].order_id] = (volume, dollars, atr, method)
            reserve_buy(book, execution, asset, quantity, reference, stop)
        elif not intent:
            order_index = self._append_order(day, next_day, item, "risk:" + ",".join(codes))
        self._risk_record(day, "close", asset,
                          self.orders[order_index].order_id if order_index is not None else None,
                          method, "capped" if approved and codes else ("approved" if approved else "rejected"),
                          codes or ("within_limits",), requested, quantity if approved else ZERO,
                          reference, stop, atr, volume, dollars, equity_reference, loss)
        return order_index if approved else None

    def _submit(self, day, next_day, state):
        context = SessionContext(day, self.config.universe, state.cash, state.equity, state.positions,
                                 self.histories, self.history_dates, self.splits, self.dividends,
                                 self.config.references, self.snapshot.sessions, self.config.cash_rates)
        response = self.source.orders(context)
        if isinstance(response, OrderBatch):
            decisions = response.decisions
            if (any(d.session != day or d.security_id not in self.config.universe for d in decisions)
                    or len({d.security_id for d in decisions}) != len(decisions)):
                raise ValueError("Signal batch requires unique in-universe decisions at the signal session")
            self.signal_decisions.extend(decisions)
            response = response.requests
        try:
            requests = tuple(response)
        except TypeError as exc:
            raise ValueError(f"Order source must return an iterable of requests on {day}") from exc
        if any(not isinstance(request, (OrderRequest, EntryIntent)) for request in requests):
            raise ValueError(f"Order source returned unsupported request on {day}")
        if self.config.risk is None and any(isinstance(r, EntryIntent) for r in requests):
            raise ValueError("Entry intents require an enabled risk policy")
        if self.source.spec != self.spec:
            raise ValueError("Order source metadata changed during the run")
        requests = sorted(requests, key=lambda r: (0 if isinstance(r, OrderRequest) and r.side == "sell" else 1,
                                                   r.priority, r.security_id, content_hash(r)))
        if self.config.risk:
            self.drawdown = state.drawdown
            self.halted = self.halted or state.drawdown >= self.config.risk.drawdown_halt
            self.budget_scale = (ZERO if self.halted else self.config.risk.reduced_budget_scale
                                 if state.drawdown >= self.config.risk.drawdown_reduce else Decimal("1"))
            book = self._book({v.security_id: v.close for v in state.positions})
            drift = portfolio_breaches(self.config.risk, self.config.execution, book, self.budget_scale)
            self._risk_record(day, "portfolio", None, None, "drawdown", "halted" if self.halted else
                              "reduced" if self.budget_scale < 1 else "active",
                              ("drawdown_halt" if self.halted else "drawdown_reduce" if self.budget_scale < 1
                               else "drawdown_normal",) + drift, equity=state.equity, book=book)
            if self.halted:
                for position in state.positions:
                    request = OrderRequest(position.security_id, "sell", position.quantity,
                                           priority=-1, reason="drawdown_halt_liquidation")
                    index = self._append_order(day, next_day, request)
                    if self.orders[index].status == "pending":
                        self.pending.append(index)
        for request in requests:
            if self.config.risk and (isinstance(request, EntryIntent) or request.side == "buy"):
                index = self._plan_entry(request, context, book, next_day)
            elif self.config.risk and self.halted and request.side == "sell":
                self._append_order(day, next_day, request, "drawdown_exit_supersedes")
                index = None
            else:
                index = self._append_order(day, next_day, request, self._signal_code(request, day))
            if index is not None and self.orders[index].status == "pending":
                self.pending.append(index)

    def run(self):
        for index, day in enumerate(self.sessions):
            if index and self.config.cash_rates is not None:
                self._interest(self.sessions[index - 1], day)
            self._corporate_actions(day)
            self._stop_orders(day, opening=True)
            self._execute(day)
            self._stop_orders(day, opening=False)
            state = self._state(day)
            target = index + self.config.execution_delay_sessions
            next_day = self.sessions[target] if target < len(self.sessions) else None
            self._submit(day, next_day, state)
        final = self.states[-1]
        summary = RunSummary(self.config.initial_cash, final.equity,
                              final.equity / self.config.initial_cash - 1,
                              max(s.drawdown for s in self.states), len(self.fills),
                              sum(o.status == "rejected" for o in self.orders),
                              sum(o.status == "expired" for o in self.orders), final.fees, final.slippage)
        return BacktestResult(self.manifest, tuple(self.orders), tuple(self.fills), tuple(self.cash_movements),
                              tuple(self.action_records), tuple(self.states), tuple(self.ledger.receivables), summary,
                              tuple(self.risk_decisions), tuple(self.signal_decisions))
