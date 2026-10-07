"""Bounded reader of original inline numeric inputs, not a general iXBRL engine."""
from decimal import Decimal
from html.parser import HTMLParser
import re
from xml.etree import ElementTree as ET

from research.sec_reconcile import parse_instance, XBRLI, XSI, COMPONENTS

NEEDED=COMPONENTS
INLINE={'http://www.xbrl.org/2013/inlineXBRL','http://www.xbrl.org/2008/inlineXBRL'}
TRANSFORMS={'http://www.xbrl.org/inlineXBRL/transformation/'+d for d in
            ('2010-04-20','2011-07-31','2015-02-26','2020-02-12','2022-02-16')}
SEC_TRANSFORM='http://www.sec.gov/inlineXBRL/transformation/2015-08-31'
CASES={'startdate':'startDate','enddate':'endDate','contextref':'contextRef','unitref':'unitRef'}


class Reader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ns={};self.root=ET.Element('{'+XBRLI+'}xbrl');self.header=[]
        self.numeric=[]

    def qname(self,name):
        if ':' not in name:raise ValueError('Unqualified inline QName')
        prefix,local=name.split(':',1)
        if prefix not in self.ns:raise ValueError('Unknown inline namespace')
        return self.ns[prefix],local

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        for key,value in attrs.items():
            if key.startswith('xmlns:'):
                prefix=key.split(':',1)[1]
                if prefix in self.ns and self.ns[prefix]!=value:raise ValueError('Rebound inline namespace')
                self.ns[prefix]=value
        uri,local=self.qname(tag) if ':' in tag else ('',tag)
        if self.header or (uri==XBRLI and local in ('context','unit')):
            attributes={CASES.get(k,k):v for k,v in attrs.items() if not k.startswith('xmlns')}
            element=ET.Element('{'+uri+'}'+CASES.get(local,local),attributes)
            if self.header:self.header[-1].append(element)
            else:self.root.append(element)
            self.header.append(element)
        else:
            for fact in self.numeric:
                fact['depth']+=1
                if uri in INLINE and local=='exclude':fact['excluding']+=1
            if uri in INLINE and local=='nonfraction':
                concept=self.qname(attrs['name'])
                if concept[1] in NEEDED:
                    self.numeric.append(dict(attrs=attrs,concept=concept,text=[],depth=1,excluding=0))

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs);self.handle_endtag(tag)

    def handle_endtag(self,tag):
        uri,local=self.qname(tag) if ':' in tag else ('',tag)
        if self.header:
            self.header.pop()
        else:
            for fact in self.numeric:
                if uri in INLINE and local=='exclude':fact['excluding']-=1
                fact['depth']-=1
            while self.numeric and self.numeric[-1]['depth']==0:
                self.finish_numeric(self.numeric.pop())

    def handle_data(self,data):
        if self.header:
            element=self.header[-1];element.text=(element.text or '')+data
        else:
            for fact in self.numeric:
                if not fact['excluding']:fact['text'].append(data)

    def finish_numeric(self,fact):
        attrs=fact['attrs'];text=''.join(fact['text']).strip()
        if attrs.get('xsi:nil') in ('true','1'):return
        if attrs.get('continuedat'):raise ValueError('Selected inline continuation unsupported')
        if attrs.get('sign') not in (None,'-'):raise ValueError('Unknown inline sign')
        fmt=attrs.get('format')
        if fmt:
            uri,local=self.qname(fmt)
            # EDGAR Filer Manual section 5.2.5.12: "no" and "None" map to 0.
            # Other word-number transformations remain deliberately unsupported.
            if uri==SEC_TRANSFORM and local=='numwordsen' and text.lower() in ('no','none'):text='0'
            elif uri not in TRANSFORMS:raise ValueError('Unreviewed inline transformation namespace')
            elif local in ('num-dot-decimal','numdotdecimal','numcommadot'):
                if not re.fullmatch(r'(?:\d+(?:\.\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?)',text):
                    raise ValueError('Invalid inline decimal grouping')
                text=text.replace(',','')
            elif local=='fixed-zero':text='0'  # Registry 4: any explicitly transformed string.
            elif local in ('numdash','zerodash') and text in ('-','–','—'):text='0'
            else:raise ValueError('Unsupported selected inline transformation')
        try:value=Decimal(text)
        except ArithmeticError as exc:raise ValueError('Invalid original inline number') from exc
        if not value.is_finite():raise ValueError('Nonfinite inline value')
        value*=Decimal(10)**int(attrs.get('scale','0'))
        if attrs.get('sign')=='-':value=-value
        uri,tag=fact['concept']
        element=ET.SubElement(self.root,'{'+uri+'}'+tag,
            {'contextRef':attrs['contextref'],'unitRef':attrs['unitref'],'decimals':attrs.get('decimals','INF')})
        element.text=str(value)


def parse_inline(body):
    reader=Reader();reader.feed(body.decode('utf-8-sig'));reader.close()
    if reader.header or reader.numeric:raise ValueError('Incomplete selected inline input')
    # Units contain lexical QNames; retain their original prefix declarations.
    for prefix,uri in reader.ns.items():reader.root.set('xmlns:'+prefix,uri)
    return parse_instance(ET.tostring(reader.root,encoding='utf-8'))


def crosscheck(inline,extracted):
    def values(rows):
        return {(r['taxonomy'],r['tag'],r['cik'],r['start'],r['end'],r['units']):r['value']
                for r in rows if r['tag'] in NEEDED and not r['dimensional']}
    if values(inline)!=values(extracted):raise ValueError('Original inline facts disagree with archived extracted instance')
    return inline
