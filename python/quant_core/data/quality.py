"""Report data limitations without inventing bars or repairing observations."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from quant_core.data import CashDelisting, Dividend, Snapshot, Split, number


@dataclass(frozen=True)
class QualityIssue:
    severity: str
    code: str
    security_id: str | None
    session: date | None
    message: str


@dataclass(frozen=True)
class QualityReport:
    dataset_hash: str
    bar_count: int
    security_count: int
    session_count: int
    actions_declared_complete: bool
    issues: tuple[QualityIssue, ...]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


def check_quality(snapshot: Snapshot, jump_threshold="0.50", *, strict_discontinuities=False) -> QualityReport:
    threshold = number(jump_threshold)
    if threshold <= 0:
        raise ValueError("jump_threshold must be positive")
    if type(strict_discontinuities) is not bool:
        raise ValueError("strict_discontinuities must be a boolean")
    issues = []
    by_asset = defaultdict(dict)
    price_actions = defaultdict(list)
    delistings = {a.security_id: a for a in snapshot.actions if isinstance(a, CashDelisting)}
    for action in snapshot.actions:
        if isinstance(action, (Split, Dividend)):
            price_actions[action.security_id].append(action)
    for actions in price_actions.values():
        actions.sort(key=lambda action: (action.session, isinstance(action, Dividend)))
    for bar in snapshot.bars:
        by_asset[bar.security_id][bar.session] = bar
        if bar.volume == 0:
            issues.append(QualityIssue("warning", "zero_volume", bar.security_id, bar.session,
                                       "Zero volume: bar is not evidence of executable liquidity"))
    for security in snapshot.securities:
        records = by_asset[security.security_id]
        previous = None
        for day in snapshot.sessions:
            if not security.active_on(day):
                continue
            if day not in records:
                issues.append(QualityIssue("error", "missing_bar", security.security_id, day,
                                           "Expected session has no bar; no price was filled in"))
                continue
            bar = records[day]
            if previous is not None:
                with localcontext() as ctx:
                    ctx.prec = 28
                    reference = previous.close
                    for action in price_actions[security.security_id]:
                        if previous.session < action.session <= day:
                            reference = (action.adjust_price(reference) if isinstance(action, Split)
                                         else reference - action.amount)
                    if reference <= 0:
                        issues.append(QualityIssue("warning", "nonpositive_action_adjusted_reference",
                                                   security.security_id, day,
                                                   "Known distributions exhaust the previous price; percentage-gap check is undefined"))
                        previous = bar
                        continue
                    relative = bar.open / reference
                    jump = abs(relative - 1)
                    common_factors = (Decimal(1) / 2, Decimal(2) / 3, Decimal(4) / 5,
                                      Decimal(5) / 4, Decimal(3) / 2, Decimal(2))
                    suspicious = any(abs(relative / factor - 1) <= Decimal("0.005")
                                     for factor in common_factors)
                severity = "error" if strict_discontinuities else "warning"
                if jump >= threshold:
                    issues.append(QualityIssue(severity, "price_discontinuity", security.security_id, day,
                                               "Large open/previous-close change after known splits and dividends; investigate actions/data"))
                if suspicious:
                    issues.append(QualityIssue(severity, "suspected_missing_split", security.security_id, day,
                                               "Unexplained split-sized price change; reconcile source evidence. "
                                               "This heuristic is not proof of a split and does not repair data."))
            previous = bar
        if (security.delisted_on is not None
                and snapshot.sessions[0] <= security.delisted_on <= snapshot.sessions[-1]
                and security.security_id not in delistings):
            issues.append(QualityIssue("warning", "missing_delisting_settlement", security.security_id,
                                       security.delisted_on, "Delisting known, but held-position settlement is unresolved"))
    if not snapshot.metadata.actions_complete:
        issues.append(QualityIssue("warning", "actions_incomplete", None, None,
                                   "Corporate-action coverage is unqualified; total-return research is not qualified"))
    for limitation in snapshot.metadata.limitations:
        issues.append(QualityIssue("warning", "source_limitation", None, None, limitation))
    issues.sort(key=lambda issue: (issue.session or date.min, issue.security_id or "", issue.code))
    return QualityReport(snapshot.dataset_hash, len(snapshot.bars), len(snapshot.securities),
                         len(snapshot.sessions), snapshot.metadata.actions_complete, tuple(issues))
