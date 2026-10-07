"""Original member, class and unit scope must survive numeric extraction."""
from decimal import Decimal as D
import unittest

from research.sec_scoped import parse_scoped, parse_scoped_inline, crosscheck_scoped


def context(name='annual',dimensions='',instant=False):
    period='<i:instant>2020-12-31</i:instant>' if instant else '<i:startDate>2020-01-01</i:startDate><i:endDate>2020-12-31</i:endDate>'
    return '<i:context id="'+name+'"><i:entity><i:identifier scheme="http://www.sec.gov/CIK">1</i:identifier>'+dimensions+'</i:entity><i:period>'+period+'</i:period></i:context>'


def dimension(member='ProductMember',axis='s:ProductOrServiceAxis'):
    return '<i:segment><d:explicitMember dimension="'+axis+'">g:'+member+'</d:explicitMember></i:segment>'


def fact(tag,value,ctx='annual',unit='usd',decimals='0'):
    return '<g:'+tag+' contextRef="'+ctx+'" unitRef="'+unit+'" decimals="'+decimals+'">'+str(value)+'</g:'+tag+'>'


def document(facts,contexts=None):
    return ('''<i:xbrl xmlns:i="http://www.xbrl.org/2003/instance" xmlns:g="http://fasb.org/us-gaap/2020-01-31"
      xmlns:s="http://fasb.org/srt/2020-01-31" xmlns:d="http://xbrl.org/2006/xbrldi"
      xmlns:iso="http://www.xbrl.org/2003/iso4217">'''+(contexts or context()+context('balance',instant=True))+
      '''<i:unit id="usd"><i:measure>iso:USD</i:measure></i:unit>
      <i:unit id="shares"><i:measure>i:shares</i:measure></i:unit>
      <i:unit id="perShare"><i:divide><i:unitNumerator><i:measure>iso:USD</i:measure></i:unitNumerator>
      <i:unitDenominator><i:measure>i:shares</i:measure></i:unitDenominator></i:divide></i:unit>'''+facts+'</i:xbrl>').encode()


class ScopedTests(unittest.TestCase):
    def test_expanded_axis_members_are_preserved_and_not_collapsed(self):
        body=document(fact('Revenues',100,'product')+fact('Revenues',5,'membership'),
            context('product',dimension())+context('membership',dimension('MembershipMember')))
        rows=parse_scoped(body)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['dimensions'],((('srt','ProductOrServiceAxis'),('us-gaap','ProductMember')),))
        self.assertEqual(rows[1]['value'],D(5))

    def test_foreign_taxonomy_does_not_masquerade_as_standard_member(self):
        rows=parse_scoped(document(fact('Revenues',100),context(dimensions=dimension())).replace(
            b'http://fasb.org/us-gaap/2020-01-31',b'http://example.com/us-gaap'))
        self.assertEqual(rows[0]['taxonomy'],'http://example.com/us-gaap')
        self.assertEqual(rows[0]['dimensions'][0][1][0],'http://example.com/us-gaap')

    def test_typed_and_non_dimension_segments_remain_opaque(self):
        for content in ('<d:typedMember dimension="s:ProductOrServiceAxis"><g:Name>product</g:Name></d:typedMember>',
                        '<g:Business>consolidated</g:Business>'):
            rows=parse_scoped(document(fact('Revenues',100),context(dimensions='<i:segment>'+content+'</i:segment>')))
            self.assertTrue(rows[0]['opaque_context'])

    def test_new_capital_tags_keep_shares_and_per_share_units_distinct(self):
        rows=parse_scoped(document(fact('CommonStockSharesIssued',20,'balance','shares')+
            fact('PreferredStockLiquidationPreference','6.82','balance','perShare','2')))
        self.assertEqual([(r['value'],r['units']) for r in rows],[(D(20),'shares'),(D('6.82'),'USD/share')])

    def test_scope_collision_and_nonfinite_duplicates_fail_closed(self):
        for body in (document(fact('CommonStockSharesIssued',20,'balance','shares')+fact('CommonStockSharesIssued',21,'balance','shares')),
                     document(fact('CommonStockSharesIssued','NaN','balance','shares')),
                     document(fact('Revenues',10),context()+context(dimensions=dimension()))):
            with self.assertRaises(ValueError):parse_scoped(body)

    def test_inline_new_capital_numbers_crosscheck_scope_scale_and_sign(self):
        resources=document('',context('balance',dimension('CommonStockMember','g:StatementClassOfStockAxis'),True)).decode()
        attrs=resources[resources.index(' xmlns:'):resources.index('>')]
        header=resources[resources.index('>')+1:resources.rindex('</i:xbrl>')]
        body=('<html'+attrs+' xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:t="http://www.xbrl.org/inlineXBRL/transformation/2020-02-12">'
            '<ix:header><ix:resources>'+header+'</ix:resources></ix:header>'
            '<ix:nonFraction name="g:CommonStockSharesIssued" contextRef="balance" unitRef="shares" decimals="-3" scale="3" format="t:num-dot-decimal">1,234</ix:nonFraction></html>').encode()
        actual=parse_scoped_inline(body)
        extracted=parse_scoped(document(fact('CommonStockSharesIssued',1234000,'balance','shares','-3'),
            context('balance',dimension('CommonStockMember','g:StatementClassOfStockAxis'),True)))
        self.assertEqual(crosscheck_scoped(actual,extracted)[0]['value'],D(1234000))
        with self.assertRaises(ValueError):crosscheck_scoped(actual,[{**extracted[0],'dimensions':()}])

    def test_inline_divided_unit_retains_per_share_currency(self):
        xml=document(fact('PreferredStockParOrStatedValuePerShare',2,'balance','perShare','INF')).decode()
        attrs=xml[xml.index(' xmlns:'):xml.index('>')]
        header=xml[xml.index('>')+1:xml.index('<g:PreferredStock')]
        body=('<html'+attrs+' xmlns:ix="http://www.xbrl.org/2013/inlineXBRL">'+header+
            '<ix:nonFraction name="g:PreferredStockParOrStatedValuePerShare" contextRef="balance" unitRef="perShare" decimals="INF">2</ix:nonFraction></html>').encode()
        self.assertEqual(crosscheck_scoped(parse_scoped_inline(body),parse_scoped(xml.encode()))[0]['units'],'USD/share')


if __name__=='__main__':unittest.main()
