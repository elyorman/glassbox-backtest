"""Local prospective monthly SMA signal journal; no execution or return claims."""
import argparse
from collections import defaultdict
from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from quant_core.backtest.sources import SessionContext
from quant_core.data import Bar, DataMetadata, Dividend, Security, Split, Snapshot
from quant_core.data.quality import check_quality
from quant_core.data.storage import load_snapshot, save_snapshot
from quant_core.execution import ExecutionProfile
from quant_core.provenance import content_hash, primitive
from quant_core.strategies import StrategyConfig, RuleStrategy, rebalance_dates
from research.market_backtest import publish
from research.robustness_audit import source_hashes
from research.source_archive import archive_sources, verify_source_archive
from research.alpaca_download import credentials
from research.stock_data import normalize_records
from research.universe_transfer import member_events, request_pages


def now(): return datetime.now(timezone.utc)


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def calendar_sessions(rows):
    result=[]; previous=None
    for r in rows:
        day=date.fromisoformat(r['date'])
        opening=datetime.combine(day,time.fromisoformat(r['open']),ZoneInfo('America/New_York'))
        closing=datetime.combine(day,time.fromisoformat(r['close']),ZoneInfo('America/New_York'))
        if opening>=closing or (previous is not None and day<=previous):
            raise ValueError('Calendar must have ordered distinct dates and opening before close')
        result.append((day,opening,closing));previous=day
    if len(result)<2: raise ValueError('Calendar requires signal and following execution session')
    return tuple(result)


def register_journal(output,configuration,calendar_path):
    if configuration.family!='trend' or configuration.profile!='scheduled_slots':
        raise ValueError('Shadow journal requires the frozen scheduled trend recipe')
    rows=json.loads(calendar_path.read_text()); sessions=calendar_sessions(rows)
    registered=now()
    if not any(closing>registered for _,_,closing in sessions):
        raise ValueError('Calendar needs future signal and execution sessions')
    output.mkdir(parents=True,exist_ok=False);(output/'records').mkdir()
    with (output/'calendar.json').open('xb') as handle:handle.write(calendar_path.read_bytes())
    archive=archive_sources(Path(__file__).resolve().parents[2],output/'source-archive')
    registration=primitive(dict(schema_version=1,registered_at=registered,configuration=configuration,
        source_hashes=source_hashes(),archive_hash=digest(output/'source-archive/SOURCE_ARCHIVE.json'),
        calendar_hash=digest(output/'calendar.json'),signal_policy='completed month-end close before next regular session open',
        input_policy='snapshot retrieval after close and no later than record time; complete trailing history',
        account_policy='independent zero-position USD100000 diagnostic at each signal; no continuous portfolio or returns',
        initial_cash='100000',slippage_bps='10',cash_yield='0',qualified=False,broker_orders_sent=False))
    publish(output/'REGISTRATION.json',registration)
    publish(output/'REGISTRATION_HASH.json',dict(sha256=digest(output/'REGISTRATION.json')))
    return registration


def verify_journal(output):
    expected=json.loads((output/'REGISTRATION_HASH.json').read_text())['sha256']
    if digest(output/'REGISTRATION.json')!=expected:raise ValueError('Registration bytes changed')
    registration=json.loads((output/'REGISTRATION.json').read_text())
    if digest(output/'calendar.json')!=registration['calendar_hash']:raise ValueError('Calendar bytes changed')
    sessions=calendar_sessions(json.loads((output/'calendar.json').read_text()))
    archive=output/'source-archive'
    if digest(archive/'SOURCE_ARCHIVE.json')!=registration['archive_hash']:raise ValueError('Source archive binding changed')
    sources=verify_source_archive(archive)['files']
    if sources!=registration['source_hashes']:raise ValueError('Source archive/registration disagree')
    previous=content_hash(registration); latest=None; rows=[]
    files=sorted((output/'records').iterdir())
    for index,path in enumerate(files,1):
        if path.name!=f'{index:06d}.json' or path.is_symlink():raise ValueError('Journal sequence gap or unsafe file')
        body=path.read_bytes(); row=json.loads(body)
        payload={k:v for k,v in row.items() if k!='record_hash'}
        if row['record_hash']!=content_hash(payload) or row['previous_hash']!=previous or row['sequence']!=index:
            raise ValueError('Journal record chain changed')
        # Bind exact serialized bytes as well as semantic fields.
        from quant_core.provenance import canonical_json
        if body!=(canonical_json(row)+'\n').encode():raise ValueError('Journal record bytes changed')
        day=date.fromisoformat(row['signal_session'])
        execution_day,closing=validate_window(registration,sessions,day,datetime.fromisoformat(row['recorded_at']))
        if (row['eligible_execution_session']!=execution_day.isoformat()
            or datetime.fromisoformat(row['signal_close'])!=closing
            or row['configuration_hash']!=content_hash(registration['configuration'])
            or row['qualified'] is not False or row['broker_orders_sent'] is not False
            or row['account_policy']!=registration['account_policy']):
            raise ValueError('Recorded execution/configuration/purpose differs from registration')
        if latest is not None and day<=latest:raise ValueError('Duplicate/non-increasing signal session')
        snapshot=Path(row['snapshot_path'])
        if digest(snapshot)!=row['snapshot_file_hash']:raise ValueError('Recorded snapshot input changed')
        data=load_snapshot(snapshot)
        if data.dataset_hash!=row['dataset_hash']:raise ValueError('Recorded dataset binding changed')
        if row['actions_complete']!=data.metadata.actions_complete or row['limitations']!=list(data.metadata.limitations):
            raise ValueError('Recorded data limitations changed')
        recorded=datetime.fromisoformat(row['recorded_at'])
        close=next(close for d,_,close in sessions if d==day)
        if not close<=data.metadata.retrieved_at<=recorded:raise ValueError('Recorded retrieval chronology invalid')
        if row['decisions']!=signal_decisions(data,registration,sessions,day):raise ValueError('Saved decisions differ from frozen rule')
        previous=row['record_hash'];latest=day;rows.append(row)
    return dict(signal_records=len(rows),latest_signal=None if latest is None else latest.isoformat(),
        chain_head=previous,qualified=False,broker_orders_sent=False,registration=registration)


def validate_window(registration,sessions,day,recorded):
    dates=tuple(d for d,_,_ in sessions)
    if day not in rebalance_dates(dates,'month_end'):raise ValueError('Signal date is not a completed calendar month-end rebalance')
    index=dates.index(day);close=sessions[index][2];opening=sessions[index+1][1]
    if datetime.fromisoformat(registration['registered_at'])>=close:
        raise ValueError('Signal close predates registration; no retrospective record allowed')
    if recorded.utcoffset() is None or not close<=recorded<opening:
        raise ValueError('Record must be after signal close and before next execution open')
    return dates[index+1],close


def signal_decisions(data,registration,sessions,day):
    cfg=StrategyConfig(**registration['configuration']); dates=tuple(d for d,_,_ in sessions)
    past=tuple(d for d in dates if d<=day)[-cfg.required_history:]
    if len(past)<cfg.required_history:raise ValueError('Insufficient trailing coverage')
    registry={s.security_id:s for s in data.securities}
    if set(cfg.universe)-set(registry):raise ValueError('Snapshot registry differs from frozen universe')
    actions=tuple(a for a in data.actions if a.security_id in cfg.universe and a.session<=day)
    bars=tuple(b for b in data.bars if b.security_id in cfg.universe and b.session in past)
    # Actions before the truncated window still enter the causal context below.
    window=Snapshot(past,bars,data.metadata,tuple(registry[a] for a in cfg.universe),
                    tuple(a for a in actions if a.session in past))
    if check_quality(window,strict_discontinuities=True).has_errors:raise ValueError('Missing or invalid signal coverage')
    histories=defaultdict(list)
    for bar in data.bars:
        if bar.security_id in cfg.universe:histories[bar.security_id].append(bar)
    history={asset:tuple(sorted(rows,key=lambda b:b.session)) for asset,rows in histories.items()}
    context=SessionContext(day,cfg.universe,Decimal(registration['initial_cash']),Decimal(registration['initial_cash']),(),
        history,{a:tuple(b.session for b in rows) for a,rows in history.items()},
        tuple(a for a in actions if isinstance(a,Split)),tuple(a for a in actions if isinstance(a,Dividend)))
    strategy=RuleStrategy(cfg,dates,tuple(registry[a] for a in cfg.universe),dates[0],ExecutionProfile(registration['slippage_bps']))
    return primitive(strategy.orders(context).decisions)


def record_signal(output,snapshot_path,day):
    status=verify_journal(output);registration=status['registration'];recorded=now()
    if source_hashes()!=registration['source_hashes']:raise ValueError('Live source changed; use the frozen runtime or register a new journal version')
    sessions=calendar_sessions(json.loads((output/'calendar.json').read_text()))
    execution_day,closing=validate_window(registration,sessions,day,recorded)
    if status['latest_signal'] is not None and day<=date.fromisoformat(status['latest_signal']):
        raise ValueError('Duplicate or out-of-order signal session')
    data=load_snapshot(snapshot_path)
    if not closing<=data.metadata.retrieved_at<=recorded:
        raise ValueError('Snapshot retrieval must follow close and precede recording')
    decisions=signal_decisions(data,registration,sessions,day)
    row=primitive(dict(schema_version=1,sequence=status['signal_records']+1,previous_hash=status['chain_head'],
        recorded_at=recorded,signal_session=day,signal_close=closing,eligible_execution_session=execution_day,
        dataset_hash=data.dataset_hash,snapshot_file_hash=digest(snapshot_path),snapshot_path=str(snapshot_path.resolve()),
        configuration_hash=content_hash(registration['configuration']),decisions=decisions,
        limitations=data.metadata.limitations,actions_complete=data.metadata.actions_complete,qualified=False,
        broker_orders_sent=False,account_policy=registration['account_policy']))
    row['record_hash']=content_hash(row);publish(output/'records'/f'{row["sequence"]:06d}.json',row)
    return row


def capture_records(bars,events,calendar,universe,retrieved_at,hashes):
    """Fresh Alpaca SPY reference; unknown cash dates stay modeled receivables."""
    spy_events=member_events(events,'SPY'); actions=[]; missing=0
    for kind,rows in spy_events.items():
        if rows and kind not in ('cash_dividends','forward_splits','reverse_splits'):
            raise ValueError('Unsupported SPY action requires review')
        for row in rows:
            day=date.fromisoformat(row['ex_date'])
            if not calendar[0]<=day<=calendar[-1]:continue
            if kind=='cash_dividends':
                if not row.get('payable_date'):missing+=1
                payment=date.fromisoformat(row['payable_date']) if row.get('payable_date') else calendar[-1]+timedelta(days=366)
                actions.append(Dividend('SPY',day,row['rate'],payment))
            else:actions.append(Split('SPY',day,Decimal(str(row['new_rate']))/Decimal(str(row['old_rate']))))
    parsed=[]
    for row in bars.get('SPY',[]):
        day=datetime.fromisoformat(row['t'].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date()
        if calendar[0]<=day<=calendar[-1]:parsed.append(Bar('SPY',day,row['o'],row['h'],row['l'],row['c'],row['v']))
    spy=Snapshot(calendar,tuple(parsed),DataMetadata('alpaca_sip',retrieved_at,'fixed_forward_reference',False,'pinned_alpaca_calendar',
        limitations=('Unqualified Alpaca action coverage; unknown SPY payment dates withheld through snapshot',)),
        (Security('SPY','SPY','UNQUALIFIED_EXCHANGE'),),tuple(actions))
    filtered={kind:[row for row in rows if any(a in [v for k,v in row.items() if 'symbol' in k] for a in universe)]
              for kind,rows in events.items()}
    data,readiness=normalize_records({'bars':{a:bars.get(a,[]) for a in universe}}, {'corporate_actions':filtered},
        calendar,spy,universe,hashes,retrieved_at,True)
    from dataclasses import replace
    data=replace(data,metadata=replace(data.metadata,source='alpaca_sip_forward_signal_research',
        universe_policy='frozen_22_stock_prospective_signal_panel',limitations=(
            'Prospective signal journal uses no live brokerage account and no continuous portfolio',
            'All prices and SPY actions freshly collected from Alpaca; no issuer-reference completeness claim',
            f'{missing} SPY unknown payment dates withheld through snapshot',
            'Fixed retrospective original ticker identities and incomplete actions remain unqualified')))
    readiness.update(dataset_hash=data.dataset_hash,spy_unknown_payable_dates=missing)
    return data,readiness


def capture_signal(journal,output,day,env_file):
    status=verify_journal(journal);registration=status['registration'];recorded=now()
    if source_hashes()!=registration['source_hashes']:raise ValueError('Frozen source changed')
    sessions=calendar_sessions(json.loads((journal/'calendar.json').read_text()))
    _,closing=validate_window(registration,sessions,day,recorded)
    if status['latest_signal'] is not None and day.isoformat()<=status['latest_signal']:raise ValueError('Signal already recorded')
    calendar=tuple(d for d,_,_ in sessions if date(2016,1,4)<=d<=day)
    cfg=StrategyConfig(**registration['configuration']);symbols=tuple(sorted(cfg.universe+('SPY',)))
    plan=primitive(dict(registration_hash=digest(journal/'REGISTRATION.json'),signal_session=day,calendar_hash=registration['calendar_hash'],
        symbols=symbols,http_budget=40,feed='sip',adjustment='raw',qualified=False,
        bars=dict(symbols=','.join(symbols),start=calendar[0].isoformat(),end=closing.isoformat(),
                  timeframe='1Day',limit=10000,feed='sip',adjustment='raw',asof=(day+timedelta(days=1)).isoformat(),sort='asc'),
        actions=dict(symbols=','.join(symbols),start='2015-01-01',end=(day+timedelta(days=366)).isoformat(),limit=1000,data_quality='all')))
    output.mkdir(parents=True,exist_ok=True)
    plan_path=output/'CAPTURE_PLAN.json'
    if plan_path.exists():
        if json.loads(plan_path.read_text())!=plan:raise ValueError('Capture registration changed')
    else:publish(plan_path,plan)
    headers=credentials(env_file);bars={};events={}
    for name,endpoint,params,target,key in (
        ('signal_bars','https://data.alpaca.markets/v2/stocks/bars',plan['bars'],bars,'bars'),
        ('signal_actions','https://data.alpaca.markets/v1/corporate-actions',plan['actions'],events,'corporate_actions')):
        for payload in request_pages(output,name,endpoint,params,headers,plan['http_budget']):
            for asset,rows in payload[key].items():target.setdefault(asset,[]).extend(rows)
    files=tuple(sorted((output/'raw').glob('*.json')))
    retrievals=[datetime.fromisoformat(json.loads(p.read_text())['retrieved_at']) for p in files if p.name.endswith('.request.json')]
    hashes=tuple((p.name,digest(p)) for p in files)+(('CAPTURE_PLAN.json',digest(plan_path)),)
    data,readiness=capture_records(bars,events,calendar,cfg.universe,max(retrievals),hashes)
    path=output/'signal.snapshot.json';save_snapshot(data,path);publish(output/'DATA_READINESS.json',readiness)
    return record_signal(journal,path,day)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('register','append','capture','verify'))
    parser.add_argument('--journal',type=Path,required=True)
    parser.add_argument('--calendar',type=Path)
    parser.add_argument('--frozen-plan',type=Path,default=Path('local/stock-campaign-2026-10-03-finalized/EXPERIMENT_PLAN.json'))
    parser.add_argument('--snapshot',type=Path);parser.add_argument('--signal-session',type=date.fromisoformat)
    parser.add_argument('--output',type=Path);parser.add_argument('--env-file',type=Path,default=Path('.env'))
    args=parser.parse_args()
    if args.command=='register':
        if args.calendar is None:parser.error('--calendar is required')
        plan=json.loads(args.frozen_plan.read_text())
        entry=next(e for e in plan['entries'] if e['role']=='parent' and e['configuration']['name']=='stock_trend_sma200')
        register_journal(args.journal,StrategyConfig(**entry['configuration']),args.calendar)
        print(json.dumps(dict(status='registered',signal_records=0,qualified=False)))
    elif args.command in ('append','capture'):
        if args.command=='capture':
            if args.output is None or args.signal_session is None:parser.error('--output and --signal-session are required')
            row=capture_signal(args.journal,args.output,args.signal_session,args.env_file)
            print(json.dumps(dict(sequence=row['sequence'],signal_session=row['signal_session'],record_hash=row['record_hash'])))
            return
        if args.snapshot is None or args.signal_session is None:parser.error('--snapshot and --signal-session are required')
        row=record_signal(args.journal,args.snapshot,args.signal_session)
        print(json.dumps(dict(sequence=row['sequence'],signal_session=row['signal_session'],record_hash=row['record_hash'])))
    else:
        status=verify_journal(args.journal);status.pop('registration');print(json.dumps(status))


if __name__=='__main__':main()
