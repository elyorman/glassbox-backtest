# Current Research Data Policy — 2026-10-05

> Superseded by the [2026-10-08 strategy qualification standard](STRATEGY_EVIDENCE.md); retained as research history.

The user chose to continue with the existing Alpaca account and cached data
until there is promising customer interest. Paid independent data acquisition
and additional EODHD collection are deferred. The earlier EODHD demo remains
preserved as a technical evaluation, without becoming our active research feed.

## Work we can continue

Use Alpaca for development, accounting/execution checks and explicitly
exploratory strategy backtests and robustness comparisons. Reuse cached inputs,
record every recipe and attempt, include costs, cash, risk constraints and
benchmarks, and preserve unsuccessful results. New performance experiments need
their own bounded registration; the existing frozen campaign is unchanged.

Keep the current limitations visible: a retrospective surviving custom panel,
unqualified identities/calendar/terminal outcomes, 336 originally unknown
payment dates, provider aggregation assumptions, historical revisions and
already exposed 2016–2026 history. Existing data can support engineering and
exploration; it cannot establish independent validation or an untouched test.
Do not splice EODHD dividend dates into the frozen Alpaca snapshot or invent
missing actions. Account access is not a new declaration of project usage rights.

The requirement for three to four distinct qualified built-in strategies remains.

The first subsequent task is complete: a separately registered
[corrected-engine replay](ENGINE_REPLAY.md) reran all 99 original trials without
new recipes, tuning or data changes. All financial results and parent decisions
remain unchanged; the original frozen evidence is preserved.
The subsequent [universe-transfer study](UNIVERSE_TRANSFER.md) tests all four
unchanged parents on 47 mechanically sampled additional surviving names,
retaining all 60 requested names and 13 exclusions. All 99 simulations complete;
none passes the full robustness rule. SMA200's continuous defensive result
passes, but only one of three folds does. The [prospective signal journal](FORWARD_SHADOW.md)
is registered for the original recipe, with its first window on October 30 and
zero backdated observations. It records operational signal evidence, not returns
or brokerage execution. These findings preserve, rather than relax, release gates.
Independent validation and applicable data/model-use review are deferred release
work, not passed gates. Customer interest can trigger that investment before
shipping/reference claims. The [independent-data brief](INDEPENDENT_DATA_RETEST.md)
is retained for that later decision.

## Alpaca opening-price diagnostic

Four bounded read-only Alpaca requests inspected AAPL on 2018-08-09. No new
EODHD HTTP request occurred after the user's change of scope. Both plans and
the initial sandbox transport failures are preserved.

The original raw response, normalized snapshot and fresh daily response agree
on OHLCV. The daily open **207.28** matches 100-share regular-sale trades at
**09:30:00.104 ET**. The first regular-session minute also opens at 207.28.
Separate market-center opening prints are **207.50**. The daily open therefore
has a concrete sampled trade basis; it is not an importer-generated value or
a promise of an auction fill. The cached EODHD open of 209.53 remains unexplained.

| Volume observation | Shares |
| --- | ---: |
| Alpaca daily volume | 24,937,614 |
| Sum of sampled 04:00–20:00 ET minute bars | 24,858,821 |
| Sum of 09:30–16:00 ET minute bars | 21,951,836 |
| Daily minus sampled full-session minute sum | 78,793 |

Minute sums and daily volume use different price/emission rules. Alpaca documents
that extended-hours/odd-lot conditions can update daily volume without updating
daily prices, and some volume-only minutes do not emit bars. That explains why
the quantities need not match in general; this bounded sample does **not** prove
the cause of all 78,793 residual shares. Preserve supplied daily volume rather
than replacing it with a guessed correction. [Alpaca aggregation rules](https://docs.alpaca.markets/us/docs/market-data-faq).

The daily query also returned a boundary row for August 10; it is retained and
identified separately, not merged into the August 9 diagnostic. None of the
four responses was paginated. This is a one-session investigation, not provider
qualification across the full history or a performance experiment.

Ignored evidence: `local/eodhd-conventions-2026-10-05/ALPACA_PLAN.json`,
`SUMMARY.json`, original response bytes/metadata and `COMPLETE.json`. The
completion manifest binds the scripts, original observations, snapshot and
unchanged production sources. No frozen input or portfolio result was altered.
