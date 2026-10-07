"""Bounded original financial inputs with explicit dimension/member identities."""
from datetime import date
from decimal import Decimal
from io import BytesIO
import re
from xml.etree import ElementTree as ET

from research.sec_reconcile import COMPONENTS, XBRLI, XSI, ISO, merge_duplicate
from research.sec_inline import Reader, INLINE

XBRLDI='http://xbrl.org/2006/xbrldi'
TAGS=COMPONENTS|{'CommonStockSharesIssued','TreasuryStockShares','TreasuryStockCommonShares',
    'PreferredStockSharesIssued','PreferredStockValueOutstanding','PreferredStockLiquidationPreference',
    'PreferredStockParOrStatedValuePerShare','EmployeeStockOwnershipPlanESOPSharesInESOP'}


def taxonomy(uri):
    match=re.fullmatch(r'https?://fasb\.org/(us-gaap|srt)/20\d{2}(?:-\d{2}-\d{2})?',uri)
    if match:return match[1]
    if re.fullmatch(r'https?://xbrl\.sec\.gov/dei/20\d{2}(?:-\d{2}-\d{2})?',uri):return 'dei'
    return uri


def parse_scoped(body):
    if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():raise ValueError('Unsupported original entity declaration')
    ns={}
    for _,(prefix,uri) in ET.iterparse(BytesIO(body),events=('start-ns',)):
        if prefix in ns and ns[prefix]!=uri:raise ValueError('Rebound original namespace')
        ns[prefix]=uri
    def qname(text):
        prefix,local=text.strip().split(':',1) if ':' in text else ('',text.strip())
        if prefix not in ns:raise ValueError('Unresolved original QName')
        return taxonomy(ns[prefix]),local
    root=ET.fromstring(body)
    if root.tag!='{'+XBRLI+'}xbrl':raise ValueError('Not an original instance')
    contexts={};units={}
    for c in root.findall('{'+XBRLI+'}context'):
        identifier=c.find('{'+XBRLI+'}entity/{'+XBRLI+'}identifier')
        if identifier is None or identifier.get('scheme') not in ('http://www.sec.gov/CIK','https://www.sec.gov/CIK'):
            raise ValueError('Unsupported original issuer identifier')
        period=c.find('{'+XBRLI+'}period')
        if period is None:raise ValueError('Missing original period')
        start=period.find('{'+XBRLI+'}startDate');end=period.find('{'+XBRLI+'}instant')
        if end is None:end=period.find('{'+XBRLI+'}endDate')
        if end is None:continue
        dimensions={};opaque=False
        containers=list(c.findall('{'+XBRLI+'}entity/{'+XBRLI+'}segment'))+list(c.findall('{'+XBRLI+'}scenario'))
        for container in containers:
            if (container.text or '').strip():opaque=True
            for node in container:
                if node.tag not in ('{'+XBRLDI+'}explicitMember','{'+XBRLDI+'}explicitmember'):
                    opaque=True;continue
                axis=qname(node.attrib['dimension']);member=qname(node.text or '')
                if axis in dimensions:raise ValueError('Duplicate original dimension axis')
                if len(node) or (node.tail or '').strip():opaque=True
                dimensions[axis]=member
        item=dict(cik=int(identifier.text.strip()),start=date.fromisoformat(start.text.strip()) if start is not None else None,
            end=date.fromisoformat(end.text.strip()),dimensions=tuple(sorted(dimensions.items())),opaque_context=opaque)
        key=c.attrib['id']
        if key in contexts and contexts[key]!=item:raise ValueError('Conflicting original context identity')
        contexts[key]=item
    def measures(node):
        return [qname(e.text or '') for e in node.findall('{'+XBRLI+'}measure')]
    for unit in root.findall('{'+XBRLI+'}unit'):
        values=measures(unit);label=None
        if len(unit)==1 and len(values)==1:
            uri,local=values[0]
            if uri==ISO and local in ('USD','EUR'):label=local
            elif uri==XBRLI and local=='shares':label='shares'
        divide=unit.find('{'+XBRLI+'}divide')
        if divide is not None and len(unit)==1 and len(divide)==2:
            numerator=divide.find('{'+XBRLI+'}unitNumerator');denominator=divide.find('{'+XBRLI+'}unitDenominator')
            if numerator is not None and denominator is not None and len(numerator)==len(denominator)==1:
                if measures(numerator)==[(ISO,'USD')] and measures(denominator)==[(XBRLI,'shares')]:label='USD/share'
        key=unit.attrib['id']
        if key in units and units[key]!=label:raise ValueError('Conflicting original unit identity')
        units[key]=label
    rows={}
    for e in root:
        if not e.tag.startswith('{'):continue
        uri,tag=e.tag[1:].split('}',1)
        if tag not in TAGS or e.get('contextRef') is None or e.get('{'+XSI+'}nil') in ('true','1'):continue
        ctx,unit=e.get('contextRef'),e.get('unitRef')
        if ctx not in contexts or unit not in units:raise ValueError('Unresolved original fact context/unit')
        try:value=Decimal((e.text or '').strip())
        except ArithmeticError as exc:raise ValueError('Invalid original number') from exc
        if not value.is_finite():raise ValueError('Nonfinite original number')
        item=dict(taxonomy=taxonomy(uri),tag=tag,value=value,units=units[unit],context_id=ctx,decimals=e.get('decimals'),**contexts[ctx])
        key=(item['taxonomy'],tag,item['cik'],item['start'],item['end'],item['units'],item['dimensions'],item['opaque_context'])
        if item['opaque_context']:key+=(ctx,)
        rows[key]=merge_duplicate(rows[key],item) if key in rows else item
    return tuple({k:v for k,v in r.items() if not k.startswith('_')} for r in rows.values())


class ScopedReader(Reader):
    """Extend the fact selector without mutating the previous audit reader."""
    def handle_starttag(self,tag,attrs):
        super().handle_starttag(tag,attrs)
        if self.header:return
        uri,local=self.qname(tag) if ':' in tag else ('',tag)
        if uri in INLINE and local=='nonfraction':
            attributes=dict(attrs);concept=self.qname(attributes['name'])
            if concept[1] in TAGS and concept[1] not in COMPONENTS:
                self.numeric.append(dict(attrs=attributes,concept=concept,text=[],depth=1,excluding=0))


def parse_scoped_inline(body):
    reader=ScopedReader();reader.feed(body.decode('utf-8-sig'));reader.close()
    if reader.header or reader.numeric:raise ValueError('Incomplete scoped inline evidence')
    # HTMLParser folds element names; preserve the XBRL divided-unit vocabulary.
    for element in reader.root.iter():
        for lower,proper in (('unitnumerator','unitNumerator'),('unitdenominator','unitDenominator')):
            if element.tag=='{'+XBRLI+'}'+lower:element.tag='{'+XBRLI+'}'+proper
    for prefix,uri in reader.ns.items():reader.root.set('xmlns:'+prefix,uri)
    return parse_scoped(ET.tostring(reader.root,encoding='utf-8'))


def crosscheck_scoped(primary,extracted):
    def values(rows):
        return {(r['taxonomy'],r['tag'],r['cik'],r['start'],r['end'],r['units'],r['dimensions'],r['opaque_context'],
                 r['context_id'] if r['opaque_context'] else None):
                (r['value'],r['decimals']) for r in rows}
    if values(primary)!=values(extracted):raise ValueError('Scoped primary facts disagree with original extracted XML')
    return primary
