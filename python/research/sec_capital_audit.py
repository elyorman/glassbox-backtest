"""Immutable, offline capital-evidence extension of a verified original SEC audit."""
import argparse
from datetime import date
from decimal import Decimal
import hashlib
from html import escape
import json
from pathlib import Path

from quant_core.data import Split
from quant_core.data.storage import load_snapshot
from quant_core.provenance import content_hash, primitive
from research.market_backtest import publish
from research import sec_reconcile
from research.sec_scoped import parse_scoped, parse_scoped_inline, crosscheck_scoped
from research.sec_capital import (find, interval, agrees, costco_profit, issued_less_treasury,
    preferred_deduction, check_amendment, check_note, share_basis)

ROOT=Path(__file__).resolve().parents[2]
RULES=ROOT/'docs/fundamental_capital_rules.json'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    return {**sec_reconcile.sources(),**{'research/'+n:digest(Path(__file__).with_name(n))
        for n in ('sec_scoped.py','sec_capital.py','sec_capital_audit.py')}}


def load(path):return json.loads(path.read_text())


def manifest(parent):
    names=set(load(parent/'AUDIT_PLAN.json')['input_files'])
    names.update(('AUDIT_PLAN.json','INPUT_HASHES.json','REPORT_HASHES.json','RECONCILIATION.json','REPORT.html'))
    return {n:digest(parent/n) for n in sorted(names)}


def registration(parent,rules):
    plan=load(parent/'INPUT_PLAN.json')
    if rules['common_panel']!=plan['common_panel'] or rules['formations']!=plan['formations'] or rules['minimum_eligible']!=10:
        raise ValueError('Capital review cannot change registered panel/calendar/floor')
    return dict(schema_version=1,parent=str(parent.resolve()),parent_files=manifest(parent),sources=sources(),
        market_snapshot=plan['market_snapshot'],market_snapshot_sha256=digest(Path(plan['market_snapshot'])),
        market_dataset_hash=plan['market_dataset_hash'],rules_hash=content_hash(rules),
        common_panel=plan['common_panel'],formations=plan['formations'],minimum_eligible=10,
        performance_evaluated=False,qualified=False)


def plan_audit(output,parent):
    sec_reconcile.verify(parent)
    rules=load(RULES);registered=registration(parent,rules)
    output.mkdir(parents=True,exist_ok=True)
    publish(output/'RULES.json',rules)
    publish(output/'AUDIT_PLAN.json',registered)
    return dict(documents=len(load(parent/'INPUT_PLAN.json')['documents']),raw_reused=True,
                performance_evaluated=False)


def checked_inputs(output):
    registered=load(output/'AUDIT_PLAN.json');parent=Path(registered['parent']);rules=load(output/'RULES.json')
    if registered!=registration(parent,rules) or rules!=load(RULES):raise ValueError('Capital sources/inputs/review registration changed')
    sec_reconcile.verify(parent)
    plan=load(parent/'INPUT_PLAN.json');baseline=load(parent/'RECONCILIATION.json')
    snapshot=load_snapshot(Path(plan['market_snapshot']))
    if snapshot.dataset_hash!=registered['market_dataset_hash']:raise ValueError('Capital snapshot changed')
    collection=load(parent/'COLLECTION.json')['documents'];instances={};errors={};reviews={};pairs=0
    for key,d in plan['documents'].items():
        record=collection[key];directory=parent/'raw'/key
        if record['instance_name'] is None:
            instances[key]=();errors[key]='No original instance; exact amendment review required';continue
        try:
            rows=parse_scoped((directory/'instance.xml').read_bytes())
            if record['instance_name'].endswith('_htm.xml'):
                rows=crosscheck_scoped(parse_scoped_inline((directory/'primary.html').read_bytes()),rows);pairs+=1
            instances[key]=rows
        except (ValueError,ArithmeticError) as exc:instances[key]=();errors[key]=str(exc)
    for review in rules['amendments']:
        key=review['amendment'];original=review['original']
        reviews[key]=check_amendment(key,plan['documents'],(parent/'raw'/key/'primary.html').read_bytes(),
                                    (parent/'raw'/original/'instance.xml').read_bytes(),review)
        if original in errors:raise ValueError('Reviewed amendment original failed scoped validation')
        instances[key]=instances[original];errors.pop(key,None)
    note_reviews={key:check_note((parent/'raw'/key/'primary.html').read_bytes(),plan['documents'][key],review)
                  for key,review in rules['preferred_notes'].items()}
    splits=primitive([a for a in snapshot.actions if isinstance(a,Split)])
    return registered,plan,baseline,instances,rules,note_reviews,splits,snapshot.metadata.actions_complete,errors,reviews,pairs


def dated_component(component):
    if component is None:return None
    result=dict(component)
    for key in ('start','end','filed'):
        if result.get(key) is not None:result[key]=date.fromisoformat(result[key]) if isinstance(result[key],str) else result[key]
    if 'value' in result:result['value']=Decimal(result['value'])
    if 'components' in result:
        result['components']=[dict(r,value=Decimal(r['value'])) for r in result['components']]
    return result


def pg_candidate(rows,cik,end):
    classes=[]
    axis='DefinedBenefitPlansDisclosuresDefinedBenefitPlansAxis' if end.year<=2017 else 'RetirementPlanTypeAxis'
    for series,plan in (('SeriesAPreferredStockMember','PensionPlansDefinedBenefitMember'),
                        ('SeriesBPreferredStockMember','OtherPostretirementBenefitPlansDefinedBenefitMember')):
        scope=((('us-gaap','StatementClassOfStockAxis'),('us-gaap',series)),)
        amount=tuple(sorted(scope+((('us-gaap',axis),('us-gaap',plan)),)))
        classes.append(dict(shares_concept=['us-gaap','EmployeeStockOwnershipPlanESOPSharesInESOP'],shares_scope=scope,
            amount_concept=['us-gaap','PreferredStockLiquidationPreference'],amount_scope=amount))
    return preferred_deduction(rows,cik,end,dict(basis='liquidation',classes=classes,as_candidate_only=True))


def select(candidates,first=False,fields=('value',)):
    if not candidates:return None
    filed=(min if first else max)(r['filed'] for r in candidates)
    same=[r for r in candidates if r['filed']==filed]
    if len({tuple(r[k] for k in fields) for r in same})>1:raise ValueError('Conflicting same-day original vintages')
    return min(same,key=lambda r:r['document'])


def derive(plan,baseline,instances,rules,note_reviews,splits,actions_complete,parse_errors,amendments=None):
    rows=[];amendments=amendments or {};mappings=plan.get('mappings')
    for old in baseline['rows']:
        symbol=old['symbol'];cutoff=date.fromisoformat(old['formation']);end=date(cutoff.year-1,12,31);cik=plan['ciks'][symbol]
        profit=old.get('profitability');share=dated_component(old.get('december_shares'));parent=old.get('parent_equity')
        errors=[];capital=[];newshares=[];newprofits=[];preferred_candidates=[]
        applicable=[(key,d) for key,d in plan['documents'].items() if d['symbol']==symbol and any(u[0]==old['formation'] for u in d['uses'])]
        for key,d in applicable:
            filed=date.fromisoformat(d['filed'])
            if filed>=cutoff:raise ValueError('Unavailable original filing at formation')
            if key in parse_errors:
                errors.append(dict(document=key,component='original_parse',error=parse_errors[key]));continue
            records=instances[key];actual_key=amendments.get(key,{}).get('original',key)
            actual_document=plan['documents'][actual_key]
            actual_filed=date.fromisoformat(actual_document['filed'])
            try:
                if d['form'] in ('10-K','10-K/A'):
                    fiscal=date.fromisoformat(d['report_date']) if d.get('report_date') else None
                    if fiscal is not None and fiscal.year==cutoff.year-1:
                        candidate=pg_candidate(records,cik,fiscal) if symbol in rules.get('preferred_candidates',{}) else None
                        if candidate is not None:preferred_candidates.append(dict(candidate,document=actual_key,filed=actual_filed))
                        p=find(records,cik,('us-gaap','StockholdersEquity'),None,fiscal)
                        if p is not None:
                            pref=preferred_deduction(records,cik,fiscal,note_reviews.get(actual_key))
                            capital.append(dict(parent=p,preferred=pref,preferred_candidate=candidate,
                                document=actual_key,filed=actual_filed,end=fiscal,amendment_review=amendments.get(key)))
                        if symbol=='COST':
                            p=costco_profit(records,cik,fiscal,actual_filed,cutoff)
                            if p is not None:newprofits.append(dict(p,document=actual_key,filed=actual_filed))
                        if key in amendments and mappings:
                            legacy=[dict(r,dimensional=bool(r['dimensions']) or r['opaque_context']) for r in records]
                            p=sec_reconcile.profitability(legacy,mappings['profiles'][symbol],cik,cutoff,actual_filed)
                            if p is not None:newprofits.append(dict(p,document=actual_key,filed=actual_filed,amendment_review=amendments[key]))
                recipe=rules.get('share_recipes',{}).get(symbol)
                # Reviewed recipes apply only to an original current-period annual balance sheet at Dec31.
                if (recipe and d['form'] in ('10-K','10-K/A') and actual_document.get('report_date')==end.isoformat()
                    and date.fromisoformat(recipe['from'])<=end<=date.fromisoformat(recipe['through'])):
                    s=issued_less_treasury(records,cik,end,recipe['treasury_tags'],recipe['already_net'])
                    if s is not None:newshares.append(dict(s,document=actual_key,filed=actual_filed))
            except ValueError as exc:errors.append(dict(document=key,component='capital_context',error=str(exc)))
        try:
            if newprofits:
                newer=select(newprofits,fields=('gross_profit','assets'))
                if profit and (Decimal(profit['gross_profit']),Decimal(profit['assets']))!=(newer['gross_profit'],newer['assets']):
                    raise ValueError('Reviewed profitability disagrees with prior original components')
                profit=newer
            if share:
                selected=share['components'][0]
                for r in share['components'][1:]:selected=sec_reconcile.merge_duplicate(selected,r)
                share['lower'],share['upper']=interval(selected);share['numerically_exact']=share['lower']==share['upper']
            if newshares:
                derived=select(newshares,first=True)
                if share and not agrees((share['lower'],share['upper']),(derived['lower'],derived['upper'])):
                    raise ValueError('Direct and reviewed issued/treasury shares disagree')
                if share is None:share=derived
        except ValueError as exc:
            errors.append(dict(component='reconciliation',error=str(exc)));share=None;profit=None
        selected_capital=None
        try:
            if capital:
                latest_end=max(c['end'] for c in capital)
                selected_capital=select([c for c in capital if c['end']==latest_end],fields=())
                same=[c for c in capital if (c['end'],c['filed'])==(selected_capital['end'],selected_capital['filed'])]
                if len({content_hash({k:c[k] for k in ('parent','preferred','preferred_candidate')}) for c in same})>1:
                    raise ValueError('Conflicting original capital/preferred vintages')
                parent=dict(selected_capital['parent'],document=selected_capital['document'],filed=selected_capital['filed'])
        except ValueError as exc:errors.append(dict(component='capital_context',error=str(exc)));selected_capital=None;parent=None
        preferred_candidate=None
        try:preferred_candidate=select(preferred_candidates)
        except ValueError as exc:errors.append(dict(component='capital_context',error=str(exc)))
        if errors:share=None;profit=None;parent=None;selected_capital=None
        if errors:preferred_candidate=None
        pref=selected_capital['preferred'] if selected_capital else None
        book=None
        if parent and pref and pref['valuation_reviewed']:
            book=Decimal(parent['value'])-pref['value']
            if book<=0:book=None
        basis=None
        if share:
            recipe=rules.get('share_recipes',{}).get(symbol)
            basis=share_basis(share,plan['documents'][share['document']],symbol,splits,
                             class_reviewed=bool(recipe and recipe['class_reviewed']),actions_complete=actions_complete)
        rows.append(dict(symbol=symbol,formation=old['formation'],in_common_panel=old['in_common_panel'],
            profitability=profit,parent_equity=parent,december_shares=share,preferred_deduction=pref,
            preferred_candidate=preferred_candidate,
            common_book_equity_candidate=book,share_basis=basis,errors=errors,
            value_ready=False,production_qualified=False))
    coverage=[dict(formation=f,profitability_components=sum(r['in_common_panel'] and r['profitability'] is not None for r in rows if r['formation']==f),
        december_share_components=sum(r['in_common_panel'] and r['december_shares'] is not None for r in rows if r['formation']==f),
        positive_common_book_candidates=sum(r['in_common_panel'] and r['common_book_equity_candidate'] is not None for r in rows if r['formation']==f),
        minimum_eligible=plan['minimum_eligible']) for f in plan['formations']]
    profit_pass=all(c['profitability_components']>=c['minimum_eligible'] for c in coverage)
    share_pass=all(c['december_share_components']>=c['minimum_eligible'] for c in coverage)
    return primitive(dict(rows=rows,coverage=coverage,profitability_component_floor_passed=profit_pass,
        december_share_component_floor_passed=share_pass,component_floor_passed=profit_pass and share_pass,
        fixed_panel_infeasible=not (profit_pass and share_pass),value_ready=False,performance_evaluated=False,production_qualified=False,
        required=['Complete unchanged component coverage','Accounting/class/preferred comparability review',
                  'Complete qualified action/price history and independent-data retest','Untouched future validation']))


def render(result):
    columns=('formation','profitability_components','december_share_components','positive_common_book_candidates','minimum_eligible')
    coverage=''.join('<tr>'+''.join('<td>'+escape(str(c[k]))+'</td>' for k in columns)+'</tr>' for c in result['coverage'])
    rows=''.join('<tr><td>'+escape(r['symbol'])+'</td><td>'+r['formation']+'</td><td>'+str(bool(r['profitability']))+
        '</td><td>'+str(bool(r['december_shares']))+'</td><td>'+str(r['preferred_deduction']['basis'] if r['preferred_deduction'] else 'unresolved')+
        '</td><td>'+str(bool(r['share_basis'] and r['share_basis']['passed']))+'</td></tr>' for r in result['rows'])
    return '<!doctype html><meta charset="utf-8"><title>Accounting and capital audit</title><style>body{font:15px system-ui;margin:32px}td,th{padding:7px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}</style><h1>Accounting and capital evidence</h1><p>Research components only. No strategy backtest or production qualification. Membership fees, rounded shares, preferred hierarchy and original vintages remain explicit. Missing data never becomes zero.</p><p>Fixed panel infeasible: '+str(result['fixed_panel_infeasible'])+'. Ten-issuer floor unchanged. Value ready: False.</p><table><tr>'+''.join('<th>'+c+'</th>' for c in columns)+'</tr>'+coverage+'</table><h2>Original component status</h2><table><tr><th>Issuer</th><th>Formation</th><th>Profit components</th><th>Dec31 shares</th><th>Preferred basis</th><th>Share basis qualified</th></tr>'+rows+'</table><p>CAPITAL.json retains every context, declared accuracy, arithmetic, review and failure. AUDIT_PLAN.json binds the previous audit, original responses, processing sources, market snapshot and RULES.json.</p><pre>'+escape(json.dumps(result.get('required'),indent=2))+'</pre>'


def seal(output,result):
    publish(output/'CAPITAL.json',result)
    with (output/'REPORT.html').open('x') as stream:stream.write(render(result))
    publish(output/'REPORT_HASHES.json',{'files':{n:digest(output/n) for n in ('CAPITAL.json','REPORT.html')}})


def verify_report(output,result):
    expected={'CAPITAL.json','REPORT.html'};hashes=load(output/'REPORT_HASHES.json')['files']
    if set(hashes)!=expected or any(digest(output/n)!=h for n,h in hashes.items()):raise ValueError('Capital report manifest changed/incomplete')
    if load(output/'CAPITAL.json')!=result or (output/'REPORT.html').read_text()!=render(result):
        raise ValueError('Capital arithmetic/report disagrees with original evidence')
    return True


def compute(output):
    registered,plan,baseline,instances,rules,notes,splits,complete,errors,reviews,pairs=checked_inputs(output)
    plan=dict(plan,mappings=load(Path(registered['parent'])/'MAPPINGS.json'))
    result=derive(plan,baseline,instances,rules,notes,splits,complete,errors,reviews)
    result.update(audit_plan_hash=content_hash(registered),scoped_document_errors=errors,
                  amendment_reviews=reviews,scoped_inline_pairs=pairs,original_documents=len(instances))
    return result


def summary(result):
    return dict(issuer_years=len(result['rows']),original_documents=result['original_documents'],
        scoped_inline_pairs=result['scoped_inline_pairs'],profitability_components=sum(bool(r['profitability']) for r in result['rows']),
        december_share_components=sum(bool(r['december_shares']) for r in result['rows']),
        preferred_deductions=sum(bool(r['preferred_deduction']) for r in result['rows']),
        fixed_panel_infeasible=result['fixed_panel_infeasible'],value_ready=False,performance_evaluated=False)


def audit(output):
    result=compute(output);seal(output,result);return summary(result)


def verify(output):
    result=compute(output);verify_report(output,result);return summary(result)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('plan','collect','audit','verify'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--parent',type=Path)
    args=parser.parse_args()
    if args.command=='plan':
        if args.parent is None:parser.error('--parent required for plan')
        result=plan_audit(args.output,args.parent)
    elif args.command=='collect':
        # All registered responses are already local. No implicit network or scope expansion.
        checked_inputs(args.output);result={'raw_reused':True,'new_downloads':0}
    else:result=(audit if args.command=='audit' else verify)(args.output)
    print(json.dumps(result))


if __name__=='__main__':main()
