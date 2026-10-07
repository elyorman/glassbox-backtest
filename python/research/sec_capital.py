"""Reviewed component arithmetic; never a strategy or provider qualification."""
from datetime import date
from decimal import Decimal
import hashlib
from html.parser import HTMLParser

from research.sec_reconcile import merge_duplicate

PRODUCT=((('srt','ProductOrServiceAxis'),('us-gaap','ProductMember')),)
MEMBERSHIP=((('srt','ProductOrServiceAxis'),('us-gaap','MembershipMember')),)


def find(rows,cik,concept,start,end,units='USD',dimensions=()):
    found=[r for r in rows if (r['taxonomy'],r['tag'])==tuple(concept) and r['cik']==int(cik)
        and r['start']==start and r['end']==end and r['units']==units and
        r['dimensions']==dimensions and not r['opaque_context']]
    if not found:return None
    selected=found[0]
    for r in found[1:]:selected=merge_duplicate(selected,r)
    return {k:v for k,v in selected.items() if not k.startswith('_')}


def interval(row):
    decimals=row.get('decimals')
    if decimals is None:raise ValueError('Original declared accuracy missing')
    try:half=Decimal(0) if decimals=='INF' else Decimal(10)**(-int(decimals))/2
    except (ValueError,ArithmeticError) as exc:raise ValueError('Invalid original accuracy') from exc
    return row['value']-half,row['value']+half


def agrees(first,second):
    lo,hi=max(first[0],second[0]),min(first[1],second[1])
    return lo<hi or (lo==hi and (first[0]==first[1] or second[0]==second[1]))


def costco_profit(rows,cik,end,filed,cutoff):
    if filed>=cutoff or end.year!=cutoff.year-1 or not 2018<=end.year<=2025:return None
    revenue=('us-gaap','RevenueFromContractWithCustomerExcludingAssessedTax')
    candidates=[]
    for row in rows:
        start=row['start']
        if row['end']!=end or start is None or not 330<=(end-start).days<=380:continue
        product=find(rows,cik,revenue,start,end,dimensions=PRODUCT)
        membership=find(rows,cik,revenue,start,end,dimensions=MEMBERSHIP)
        total=find(rows,cik,revenue,start,end)
        cost=find(rows,cik,('us-gaap','CostOfGoodsAndServicesSold'),start,end)
        assets=find(rows,cik,('us-gaap','Assets'),None,end)
        if any(r is None for r in (product,membership,total,cost,assets)):continue
        if min(product['value'],membership['value'],cost['value'])<0:raise ValueError('Negative reviewed Costco component')
        if interval(assets)[0]<=0:raise ValueError('Nonpositive or uncertain assets')
        p,m,t,c,a=(interval(r) for r in (product,membership,total,cost,assets))
        if not agrees((p[0]+m[0],p[1]+m[1]),t):raise ValueError('Product plus membership disagrees with consolidated revenue')
        gp=product['value']-cost['value'];lo,hi=p[0]-c[1],p[1]-c[0]
        direct=find(rows,cik,('us-gaap','GrossProfit'),start,end)
        if direct is not None and not agrees((lo,hi),interval(direct)):raise ValueError('Reviewed merchandise profit disagrees with direct original profit')
        components=[product,membership,total,cost,assets]+([direct] if direct is not None else [])
        candidates.append(dict(start=start,end=end,gross_profit=gp,assets=assets['value'],score=gp/assets['value'],
            gross_profit_lower=lo,gross_profit_upper=hi,membership=membership['value'],components=components,
            method='reviewed_product_member_merchandise_margin',accounting_comparability_qualified=False))
    if not candidates:return None
    if len({(r['start'],r['gross_profit'],r['assets']) for r in candidates})>1:raise ValueError('Conflicting reviewed annual periods')
    return candidates[0]


def issued_less_treasury(rows,cik,end,treasury_tags,already_net=False):
    issued=find(rows,cik,('us-gaap','CommonStockSharesIssued'),None,end,'shares')
    if issued is None:return None
    if issued['value']<=0:raise ValueError('Nonpositive common shares issued')
    components=[issued];lo,hi=interval(issued);value=issued['value']
    if not already_net:
        treasury=[r for tag in treasury_tags for r in [find(rows,cik,('us-gaap',tag),None,end,'shares')] if r is not None]
        if not treasury:return None  # Missing treasury is never zero.
        selected=treasury[0]
        for r in treasury[1:]:selected=merge_duplicate(selected,r)
        if selected['value']<0:raise ValueError('Negative common treasury count')
        tlo,thi=interval(selected);value-=selected['value'];lo,hi=lo-thi,hi-tlo;components+=treasury
    if lo<=0 or value<=0:raise ValueError('Issued less treasury is nonpositive or uncertain')
    return dict(end=end,value=value,lower=lo,upper=hi,numerically_exact=lo==hi,components=components,
        method='reviewed_net_issued' if already_net else 'reviewed_issued_less_common_treasury',share_basis_reviewed=False)


def preferred_deduction(rows,cik,end,review=None):
    zero=[]
    counts=[r for tag in ('PreferredStockSharesOutstanding','PreferredStockSharesIssued')
            for r in [find(rows,cik,('us-gaap',tag),None,end,'shares')] if r is not None]
    values=[r for tag in ('PreferredStockRedemptionValue','PreferredStockLiquidationValue','PreferredStockCarryingValue','PreferredStockValue','PreferredStockValueOutstanding')
            for r in [find(rows,cik,('us-gaap',tag),None,end)] if r is not None]
    if any(r['value']<0 for r in counts+values):raise ValueError('Negative issuer preferred component')
    for r in counts:
        if r['value']==0 and r.get('decimals') is not None and (r['decimals']=='INF' or int(r['decimals'])>=0):zero.append(r)
    note_zero=bool(review and review.get('note_zero_validated') and
                   int(review['cik'])==int(cik) and review['report_date']==end.isoformat())
    if zero or note_zero:
        obligations=[r for r in rows if r['taxonomy']=='us-gaap' and r['cik']==int(cik) and
            r['start'] is None and r['end']==end and not r['opaque_context'] and
            ((r['tag'] in ('PreferredStockSharesOutstanding','PreferredStockSharesIssued') and r['units']=='shares') or
             (r['tag'] in ('PreferredStockRedemptionValue','PreferredStockLiquidationValue','PreferredStockCarryingValue','PreferredStockValue','PreferredStockValueOutstanding') and r['units']=='USD'))]
        if any(r['value']>0 for r in obligations):raise ValueError('Zero preferred shares conflicts with positive issuer obligations')
        return dict(value=Decimal(0),basis='affirmative_note_zero' if note_zero else 'affirmative_zero_issuer_shares',components=zero,
                    note_review=review if note_zero else None,
                    valuation_reviewed=True)
    if review is None:return None
    if review.get('classes'):
        if review.get('basis')!='liquidation' or review.get('as_candidate_only') is not True:
            raise ValueError('Class liquidation arithmetic is a candidate, not a hierarchy review')
        components=[];value=lo=hi=Decimal(0);scopes=set()
        for recipe in review['classes']:
            scope=tuple((tuple(a),tuple(m)) for a,m in recipe['shares_scope'])
            amount_scope=tuple((tuple(a),tuple(m)) for a,m in recipe['amount_scope'])
            if scope in scopes:raise ValueError('Duplicate preferred class')
            scopes.add(scope)
            count=find(rows,cik,recipe['shares_concept'],None,end,'shares',scope)
            amount=find(rows,cik,recipe['amount_concept'],None,end,'USD/share',amount_scope)
            if count is None or amount is None:return None
            cl,ch=interval(count);al,ah=interval(amount)
            if min(cl,al)<0:raise ValueError('Negative or uncertain preferred class amount')
            value+=count['value']*amount['value'];lo+=cl*al;hi+=ch*ah
            components.extend((count,amount))
        return dict(value=value,lower=lo,upper=hi,basis='liquidation_class_candidate',
                    components=components,valuation_reviewed=False)
    concepts={'redemption':['us-gaap','PreferredStockRedemptionValue'],
              'liquidation':['us-gaap','PreferredStockLiquidationValue'],
              'par':['us-gaap','PreferredStockParOrStatedValuePerShare']}
    higher={'redemption':[],'liquidation':['redemption'],'par':['redemption','liquidation']}
    basis=review.get('basis')
    if basis not in concepts or review.get('concept')!=concepts[basis] or review.get('higher_priority_absent')!=higher[basis]:
        raise ValueError('Preferred valuation concept/hierarchy not explicitly supported')
    for earlier in higher[basis]:
        if find(rows,cik,concepts[earlier],None,end) is not None:
            raise ValueError('Available higher-priority preferred amount cannot be bypassed')
    component=find(rows,cik,concepts[basis],None,end,'USD/share' if basis=='par' else 'USD')
    if component is None:return None
    if basis=='par':
        if review.get('all_issuer_classes_reviewed') is not True:raise ValueError('Par needs all issuer classes reviewed')
        count=find(rows,cik,('us-gaap','PreferredStockSharesOutstanding'),None,end,'shares')
        if count is None:return None
        cl,ch=interval(count);al,ah=interval(component)
        if min(cl,al)<0:raise ValueError('Negative or uncertain preferred par amount')
        return dict(value=count['value']*component['value'],lower=cl*al,upper=ch*ah,
                    basis=basis,components=[count,component],valuation_reviewed=True)
    return dict(value=component['value'],basis=basis,components=[component],valuation_reviewed=True)


class FilingText(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden-=1
    def handle_data(self,text):
        if not self.hidden:self.parts.append(text)


def filing_text(body):
    reader=FilingText();reader.feed(body.decode('utf-8-sig'));reader.close()
    return ' '.join(' '.join(reader.parts).split())


def check_note(body,document,review):
    if (review.get('basis')!='affirmative_note_zero' or
        int(document['cik'])!=int(review['cik']) or document.get('report_date')!=review['report_date'] or
        hashlib.sha256(body).hexdigest()!=review['sha256']):
        raise ValueError('Reviewed preferred note body/issuer/period changed')
    text=filing_text(body)
    if not review.get('anchors') or not all(anchor in text for anchor in review['anchors']):
        raise ValueError('Reviewed affirmative preferred note absent')
    return dict(review,note_zero_validated=True)


def check_amendment(key,documents,primary,original,review):
    if review.get('amendment')!=key or review.get('original') not in documents:raise ValueError('Unreviewed amendment/original pair')
    amendment=documents[key];base=documents[review['original']]
    if (amendment['form']!='10-K/A' or base['form']!='10-K' or
        amendment['cik']!=base['cik'] or amendment['report_date']!=base['report_date'] or
        date.fromisoformat(base['filed'])>date.fromisoformat(amendment['filed'])):
        raise ValueError('Amendment metadata/issuer/period mismatch')
    if hashlib.sha256(primary).hexdigest()!=review['amendment_sha256'] or hashlib.sha256(original).hexdigest()!=review['original_sha256']:
        raise ValueError('Reviewed amendment/original bodies changed')
    text=filing_text(primary)
    if not review.get('anchors') or not all(anchor in text for anchor in review['anchors']):raise ValueError('Reviewed explanatory note absent')
    return dict(amendment=key,original=review['original'],financial_components_unchanged=True,
                amendment_sha256=review['amendment_sha256'],original_sha256=review['original_sha256'])


def share_basis(share,document,security,splits,*,class_reviewed,actions_complete):
    end=share['end'];filed=date.fromisoformat(document['filed'])
    between=[s for s in splits if s['security_id']==security and end<date.fromisoformat(s['session'])<=filed]
    current=bool(document.get('report_date')) and date.fromisoformat(document['report_date'])==end
    return dict(current_period_original=current,class_reviewed=class_reviewed,
        supplied_actions_complete=actions_complete,intervening_splits=between,
        passed=current and class_reviewed and actions_complete and not between,
        reason='Original current-period counts and supplied action checks; incomplete feed or class/vintage ambiguity cannot prove raw-price basis')
