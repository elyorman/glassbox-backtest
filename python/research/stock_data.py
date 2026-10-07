"""Pinned private stock research inputs; no qualified-data or index claims."""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo

from quant_core.data import Bar, Dividend, Split, Security, Snapshot, DataMetadata
from quant_core.data.quality import check_quality
from quant_core.data.storage import load_snapshot, save_snapshot
from quant_core.provenance import primitive
from research.alpaca_download import credentials, download
from research.market_backtest import publish

STOCKS = ('AAPL','MSFT','AMZN','GOOGL','NVDA','CSCO','JPM','BAC','GS','XOM','CVX','JNJ',
          'MRK','PFE','PG','KO','PEP','WMT','COST','HD','CAT','UNP','UPS','MCD')
FIRST, LAST = date(2016,1,4), date(2026,10,2)


def normalize_records(bars_payload, actions_payload, calendar, spy, symbols, raw_hashes, observed_at, defer_unknown=False):
    """Unknown pay dates remain visible; explicit deferral never claims a real date."""
    calendar = tuple(calendar); first, last = calendar[0], calendar[-1]
    symbols = tuple(sorted(symbols))
    if set(bars_payload['bars']) != set(symbols):
        raise ValueError('Stock bar symbol panel differs from frozen inputs')
    bars = []
    for asset, records in bars_payload['bars'].items():
        for v in records:
            day = datetime.fromisoformat(v['t'].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date()
            if first <= day <= last:
                bars.append(Bar(asset, day, v['o'], v['h'], v['l'], v['c'], v['v']))
    events = actions_payload['corporate_actions']
    supplemental=[]; unknown={}
    for kind, records in events.items():
        if kind in ('cash_dividends','forward_splits','reverse_splits'): continue
        for v in records:
            if (kind in ('cash_mergers','stock_mergers') and v.get('acquirer_symbol')
                    and v.get('acquiree_symbol') and v['acquiree_symbol'] not in symbols):
                supplemental.append({'kind':kind,'reason':'acquirer_only' if v['acquirer_symbol'] in symbols else 'outside_panel','record':v})
            elif (kind=='name_changes' and v.get('old_symbol')==v.get('new_symbol')
                  and v.get('old_symbol') in symbols):
                supplemental.append({'kind':kind,'reason':'same_symbol_identity_metadata_only','record':v})
            else: unknown[kind]=unknown.get(kind,0)+1
    if unknown:
        raise ValueError(f'Unsupported corporate actions require review, no panel replacements: {unknown}')
    actions, missing = [], []
    for kind, records in events.items():
        if kind not in ('cash_dividends','forward_splits','reverse_splits'): continue
        for v in records:
            if v['symbol'] not in symbols:
                raise ValueError('Action outside frozen stock panel')
            day = date.fromisoformat(v['ex_date'])
            if not first <= day <= last: continue
            if kind == 'cash_dividends':
                payable = v.get('payable_date')
                if not payable:
                    missing.append({'security_id':v['symbol'], 'ex_date':day.isoformat(), 'amount':str(v['rate']),
                                    'original_payable_date':None, 'availability_policy':'withheld_through_sample'})
                    if not defer_unknown: raise ValueError('Missing dividend payable date; explicit research deferral required')
                pay = date.fromisoformat(payable) if payable else last + timedelta(days=366)
                actions.append(Dividend(v['symbol'], day, v['rate'], pay))
            else:
                actions.append(Split(v['symbol'], day, Decimal(str(v['new_rate']))/Decimal(str(v['old_rate']))))
    bars.extend(b for b in spy.bars if b.security_id=='SPY' and first <= b.session <= last)
    actions.extend(a for a in spy.actions if a.security_id=='SPY' and first <= a.session <= last)
    limitations = (
        f'Private exploratory surviving{len(symbols)} custom stock panel, no historical index/PIT membership or delisting claim',
        'Alpaca source/action/calendar/identity and research/commercial usage rights remain unqualified',
        'Historical revisions and daily aggregated open are not point-in-time data or verified auction fills',
        'All 2016-2026 market periods already exposed; no fresh final holdout',
        'Missing payable dates explicitly withheld as receivables through sample; modeled availability is not an observed pay date',
        'SPY actions/price reference reused from prior pinned issuer-reconciled snapshot',
    )
    metadata = DataMetadata('alpaca_sip_stock_research_with_cached_spy', observed_at,
                            f'fixed_retrospective_surviving{len(symbols)}_custom_panel', False,
                            'alpaca_calendar_reused_independently_of_bars', limitations=limitations, input_hashes=raw_hashes)
    data = Snapshot(calendar, tuple(bars), metadata,
                    tuple(Security(a,a,'UNQUALIFIED_EXCHANGE') for a in symbols+('SPY',)), tuple(actions))
    quality = check_quality(data)
    if quality.has_errors: raise ValueError('Missing/invalid observations; no bars or panel members silently repaired')
    caps = {name:{'status':'unresolved', 'evidence':text} for name,text in (
        ('research_usage_rights','Standard free account; no separately reviewed commercial research agreement'),
        ('exchange_calendar','Provider calendar independently supplied from bars, but not exchange-reconciled'),
        ('raw_prices_and_open_convention','Explicit raw SIP bars; daily open approximation, not auction qualification'),
        ('split_and_dividend_coverage','Only received supported actions; no independent completeness evidence'),
        ('dividend_payment_dates',f'{len(missing)} unknown payable dates; conservatively withheld through sample'),
        ('security_identity','Fixed ticker panel; no historical alias/lifetime qualification'),
        ('universe_history_or_fixed_sample_disclosure','Fixed surviving sample disclosed; no PIT membership'),
        ('delisting_treatment','No delisted sample members; delisting completeness not established'))}
    report = {'dataset_hash':data.dataset_hash, 'qualified':False, 'exploratory_only':True,
              'scope':f'fixed_surviving{len(symbols)}_custom_panel', 'bar_count':len(bars), 'session_count':len(calendar),
              'start':first, 'end':last, 'missing_payable_dates':missing, 'capabilities':caps,
              'action_counts':dict(Counter(type(a).__name__ for a in actions)), 'quality':quality,
              'non_position_transforming_actions':supplemental,
              'independent_retest_status':'requires_separate_qualified_snapshot_and_reviewed_evidence'}
    return data, primitive(report)


def collect(output, env_file, spy_path):
    output.mkdir(parents=True, exist_ok=False)
    raw=output/'raw'; raw.mkdir()
    publish(output/'INPUT_PLAN.json',{'stocks':STOCKS,'benchmark':'SPY','start':FIRST,'end':LAST,
        'adjustment':'raw','feed':'sip','asof':'2026-10-03','panel_selected_before_returns':True,
        'missing_payable_policy':'withheld_through_sample','purpose':'private_exploratory_only'})
    headers=credentials(env_file)
    try:
        download(headers,raw,'stock_actions','https://data.alpaca.markets/v1/corporate-actions',
                 {'symbols':','.join(STOCKS),'start':'2015-01-01','end':'2026-12-31','limit':1000,'data_quality':'all'})
        download(headers,raw,'stock_bars','https://data.alpaca.markets/v2/stocks/bars',
                 {'symbols':','.join(STOCKS),'start':'2016-01-01','end':'2026-10-02T20:00:00Z',
                  'timeframe':'1Day','limit':10000,'feed':'sip','adjustment':'raw','asof':'2026-10-03','sort':'asc'})
        normalize(output, spy_path)
    except Exception as exc:
        publish(output/'DATA_FAILURE.json',{'status':'failed','error_type':type(exc).__name__,'error':str(exc),
                                          'panel_unchanged':True,'qualified':False})
        raise


def normalize(output, spy_path, exclude=()):
    raw=output/'raw'; hashes=[]; bars={}; actions={}; retrievals=[]
    input_plan=output/'INPUT_PLAN.json'
    hashes.append((input_plan.name,hashlib.sha256(input_plan.read_bytes()).hexdigest()))
    for meta in sorted(raw.glob('*.request.json')):
        m=json.loads(meta.read_text()); path=raw/m['body_file']; digest=hashlib.sha256(path.read_bytes()).hexdigest()
        retrievals.append(datetime.fromisoformat(m['retrieved_at']))
        if digest!=m['sha256'] or m['status']!=200: raise ValueError('Failed or changed raw response')
        hashes.extend(((path.name,digest),(meta.name,hashlib.sha256(meta.read_bytes()).hexdigest())))
        payload=json.loads(path.read_text(),parse_float=Decimal)
        target=bars if path.name.startswith('stock_bars') else actions
        key='bars' if target is bars else 'corporate_actions'
        for asset,records in payload[key].items(): target.setdefault(asset,[]).extend(records)
    if not bars or not actions: raise ValueError('Missing downloaded bars/actions')
    spy=load_snapshot(spy_path)
    if any(a not in STOCKS for a in exclude): raise ValueError('Unknown exclusion; frozen requested panel unchanged')
    eligible=tuple(a for a in STOCKS if a not in exclude)
    scope={'requested':STOCKS,'eligible':eligible,'excluded':exclude,
           'reason':'Unsupported PFE/VTRS and MRK/OGN noncash share distributions, identified before any strategy performance',
           'not_selected_by_returns':True,'no_replacement':True,'original_failure_retained':(output/'DATA_FAILURE.json').exists()}
    if exclude:
        if tuple(exclude) not in (('PFE',),('PFE','MRK')): raise ValueError('Only documented spinoff exclusions are approved')
        decision=output/'DATA_SCOPE_DECISION.json'
        if decision.exists():
            if json.loads(decision.read_text())!=primitive(scope): raise ValueError('Previously recorded data scope changed')
        else: publish(decision,scope)
        hashes.append((decision.name,hashlib.sha256(decision.read_bytes()).hexdigest()))
        bars={a:v for a,v in bars.items() if a in eligible}
        actions={k:[v for v in records if v.get('symbol',v.get('source_symbol')) not in exclude]
                 for k,records in actions.items()}
    hashes.append(('spy.snapshot.json',hashlib.sha256(spy_path.read_bytes()).hexdigest()))
    calendar=tuple(d for d in spy.sessions if FIRST<=d<=LAST)
    data,review=normalize_records({'bars':bars},{'corporate_actions':actions},calendar,spy,eligible,
                                 tuple(hashes),max(retrievals),True)
    review['panel_scope_decision']=primitive(scope)
    review['spy_snapshot']=str(spy_path.resolve())
    save_snapshot(data,output/'stock.snapshot.json'); publish(output/'DATA_READINESS.json',review)
    print(json.dumps({'status':'normalized','bars':len(data.bars),'sessions':len(data.sessions),
                      'missing_payable_dates':len(review['missing_payable_dates']),'qualified':False}),flush=True)


def refresh_actions(output, previous, env_file, spy_path):
    """Retain price download exactly; extend process-date coverage without overwrites."""
    output.mkdir(parents=True,exist_ok=False); raw=output/'raw'; raw.mkdir()
    prior=json.loads((previous/'INPUT_PLAN.json').read_text())
    if prior['stocks']!=list(STOCKS): raise ValueError('Requested stock panel changed')
    for path in sorted((previous/'raw').glob('stock_bars.*.json')):
        shutil.copyfile(path,raw/path.name)
    publish(output/'INPUT_PLAN.json',dict(prior,action_process_date_end='2026-12-31',
        bars_reused_from=str(previous.resolve()),supersedes_unqualified_snapshot=True,
        excluded_before_performance=['PFE','MRK']))
    download(credentials(env_file),raw,'stock_actions','https://data.alpaca.markets/v1/corporate-actions',
             {'symbols':','.join(STOCKS),'start':'2015-01-01','end':'2026-12-31','limit':1000,'data_quality':'all'})
    normalize(output,spy_path,('PFE','MRK'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('collect','normalize','refresh-actions'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--env-file',type=Path,default=Path('.env'))
    parser.add_argument('--spy-snapshot',type=Path,default=Path('local/market-backtest-2026-10-03/market.snapshot.json'))
    parser.add_argument('--exclude-pfe-unsupported-spinoff',action='store_true')
    parser.add_argument('--reuse-data',type=Path)
    args=parser.parse_args()
    if args.command=='collect': collect(args.output,args.env_file,args.spy_snapshot)
    elif args.command=='refresh-actions':
        if args.reuse_data is None: parser.error('--reuse-data is required')
        refresh_actions(args.output,args.reuse_data,args.env_file,args.spy_snapshot)
    else: normalize(args.output,args.spy_snapshot,('PFE',) if args.exclude_pfe_unsupported_spinoff else ())


if __name__=='__main__': main()
