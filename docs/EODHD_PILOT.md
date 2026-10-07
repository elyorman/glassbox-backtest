# EODHD Public-Demo Technical Pilot — 2026-10-05

Subsequent user decision: [stay with Alpaca for now](ALPACA_RESEARCH.md).
Additional EODHD collection and paid data acquisition are deferred until
promising customer interest. This completed demo is preserved as historical
technical evidence, not the active provider choice.

The existing importer processed real EODHD responses successfully. The demo
supplies useful historical payment dates but cannot support the full frozen
retest. No strategy execution, tuning, ML training, purchase or frozen-result
change occurred. Production sources remain version 0.5.1.

## Scope and observations

`local/eodhd-demo-pilot-2026-10-05/PILOT_PLAN.json` registered seven requests for
2016-01-04 through 2026-10-02 before collection. Only the documented public
`demo` token was used; no private credentials were read. A sandbox transport
failure was preserved separately, then collection succeeded with network
approval. All seven actual responses were retained without vendor retries.

| Endpoint | HTTP status | Returned observations |
| --- | --- | --- |
| AAPL daily prices | 200 | 2,703 bars; both requested boundary sessions |
| AAPL splits | 200 | One 4-for-1 event on 2020-08-31 |
| AAPL dividends | 200 | 43 events; all have payment dates |
| MSFT dividends | 200 | 43 events; all have payment dates |
| AMZN splits | 200 | One 20-for-1 event on 2022-06-06 |
| NVDA splits | 403 | Plain Forbidden response |
| SPY dividends | 403 | Plain Forbidden response |

The denials are consistent with documented demo restrictions, not evidence
those histories are unavailable with an appropriate account. Public demo access
and a free personal account are separate entitlements. See the
[daily API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)
and [action API](https://eodhd.com/financial-apis/api-splits-dividends).

## Import evidence

All returned action rows resolved within their requested endpoint scopes.
Exact split dates/ratios bind to retained primary-source review notes for
[Apple](https://www.apple.com/newsroom/2020/07/apple-reports-third-quarter-results/)
and [Amazon, Item 5.03](https://www.sec.gov/Archives/edgar/data/1018724/000110465922065872/tm2215904d1_8k.htm).
Record/distribution dates remain distinct from split-adjusted trading dates.
Notes retain URLs and paraphrased findings; full issuer HTML was not archived.

Apple's 2020-05-08 dividend row has historical cash **USD 0.82**, adjusted `value`
**USD 0.205**, and payment date **2020-05-14**. The importer uses 0.82.
[Apple's announcement](https://www.apple.com/newsroom/2020/04/apple-reports-second-quarter-results/)
corroborates cash, payment date and the separate May 11 record date; it does not
independently confirm the provider's May 8 ex-date. One sample does not audit the
whole feed.

Both dividend feeds match the original 43 ex-dates and cash amounts per issuer.
They supply dates for **17 previously modeled late receivables each**, 34 total.
The original snapshot and its 336-unknown-payment-date disclosure remain intact.
MSFT's dividend-only and AMZN's split-only parser audits explicitly identify
unrequested counterpart arrays as local empty diagnostic placeholders, not
downloaded feeds or evidence of absent actions.

AAPL imports raw OHLC, preserves supplied volume and reviewed actions, and
round-trips through storage. Its dates match the 2,703-session cached Alpaca
calendar. Strict mechanical checks give **zero errors and seven warnings**.
Shared calendar/registry use is disclosed, and `actions_complete` remains false.

## Unresolved conventions and next decision

Comparison with the original AAPL bars finds differences in 404 opens, 269
highs, 276 lows, 52 closes and 2,698 volumes. Neither provider is ground truth.
On **2018-08-09**, Alpaca's open is **207.28** and EODHD's **209.53**, about
**1.09% higher**. Investigate opening-price conventions and source differences
before execution-sensitive retesting; passing bar checks does not resolve this.

EODHD documents split-adjusted volume. The adapter discloses that basis without
reconstructing raw volume from incomplete actions. The frozen dollar-volume and
participation rules still need a reviewed volume basis.
[Field conventions](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes).
Exact split counts produce a schema-2 diagnostic snapshot; the frozen runtime
accepts schema 1. Any legacy conversion requires explicit, exact review.

Next, resolve open/volume conventions and obtain appropriately permitted full
22-stock-plus-SPY inputs. Independently reviewed sessions, effective identities,
noncash/terminal events, source independence and project research rights remain
outstanding. Demo access does not qualify commercial research or imply a paid
plan fixes every gap. All eight qualification capabilities remain unpassed;
previously exposed dates remain exposed.

## Retained evidence

Ignored `local/eodhd-demo-pilot-2026-10-05/` holds original response bytes,
credential-free metadata, hashes, event reviews, audits, a diagnostic snapshot,
quality report and `analysis/SUMMARY.json`. `analysis/COMPLETE.json` binds these
files, scripts, reused original snapshot and unchanged sources. Observations
are reused after hash verification; conflicting outputs are refused.

The existing **28 EODHD importer/action tests pass**. This is technical input
evidence, not independent strategy validation. The
[qualification/preflight contract](DATA_QUALIFICATION.md) is unchanged.
