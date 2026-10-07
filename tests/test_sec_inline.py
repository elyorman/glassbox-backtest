"""Bounded original-inline numeric evidence, independent of SEC extraction."""
from decimal import Decimal as D
import unittest

from research.sec_inline import parse_inline, crosscheck


HEADER='''<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:xbrli="http://www.xbrl.org/2003/instance"
xmlns:us-gaap="http://fasb.org/us-gaap/2020-01-31" xmlns:iso="http://www.xbrl.org/2003/iso4217"
xmlns:ixt="http://www.xbrl.org/inlineXBRL/transformation/2020-02-12">
<ix:header><ix:resources><xbrli:context id="balance"><xbrli:entity>
<xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:instant>2020-12-31</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:unit id="usd"><xbrli:measure>iso:USD</xbrli:measure></xbrli:unit>
</ix:resources></ix:header><body>'''


def inline(value,attributes=''):
    return (HEADER+'<ix:nonFraction name="us-gaap:Assets" contextRef="balance" unitRef="usd" decimals="-3" '+attributes+'>'+value+'</ix:nonFraction></body></html>').encode()


class InlineEvidenceTests(unittest.TestCase):
    def test_original_scale_sign_exclusion_and_html_entities(self):
        rows=parse_inline(inline('1,234<ix:exclude>note 99</ix:exclude>&nbsp;',
            'format="ixt:num-dot-decimal" scale="3" sign="-"'))
        self.assertEqual(rows[0]['value'],D('-1234000'))
        self.assertEqual(rows[0]['cik'],1)
        self.assertEqual(rows[0]['units'],'USD')

    def test_unsupported_transform_invalid_grouping_and_continuation_fail_closed(self):
        for value,attrs in [('1,23','format="ixt:num-dot-decimal"'),('123','format="ixt:unknown"'),
                            ('123','continuedAt="other"'),('123','sign="plus"')]:
            with self.assertRaises(ValueError):parse_inline(inline(value,attrs))

    def test_foreign_format_namespace_cannot_masquerade_as_standard_transform(self):
        body=inline('1,234','format="ixt:num-dot-decimal"').replace(b'http://www.xbrl.org/inlineXBRL/transformation/2020-02-12',b'http://example.com/transforms')
        with self.assertRaises(ValueError):parse_inline(body)

    def test_inline_is_checked_against_extracted_instance_and_disagreement_is_unavailable(self):
        rows=parse_inline(inline('1,234','format="ixt:num-dot-decimal" scale="3"'))
        self.assertEqual(crosscheck(rows,rows)[0]['value'],D(1234000))
        wrong=[{**rows[0],'value':D(123)}]
        with self.assertRaises(ValueError):crosscheck(rows,wrong)
        with self.assertRaises(ValueError):crosscheck(rows,[])

    def test_numeric_nil_is_missing_instead_of_zero(self):
        body=inline('', 'xsi:nil="true"').replace(b'<html ',b'<html xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ')
        self.assertEqual(parse_inline(body),())

    def test_nested_numbers_keep_independent_contexts_sign_and_scale(self):
        header=HEADER.replace('<xbrli:unit id="usd">',
            '<xbrli:context id="prior"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity>'
            '<xbrli:period><xbrli:instant>2019-12-31</xbrli:instant></xbrli:period></xbrli:context><xbrli:unit id="usd">')
        body=(header+'<ix:nonFraction name="us-gaap:StockholdersEquity" contextRef="balance" unitRef="usd" decimals="-6" sign="-" scale="6">'
            '<ix:nonFraction name="us-gaap:StockholdersEquity" contextRef="prior" unitRef="usd" decimals="-3" scale="3">136</ix:nonFraction>'
            '</ix:nonFraction></body></html>').encode()
        rows=parse_inline(body)
        self.assertEqual({(str(r['end']),r['value']) for r in rows},
            {('2020-12-31',D('-136000000')),('2019-12-31',D('136000'))})

    def test_sec_word_zero_is_explicit_evidence_and_other_words_fail_closed(self):
        body=inline('no','format="sec:numwordsen"').replace(b'<html ',
            b'<html xmlns:sec="http://www.sec.gov/inlineXBRL/transformation/2015-08-31" ')
        self.assertEqual(parse_inline(body)[0]['value'],D(0))
        self.assertEqual(parse_inline(body.replace(b'>no<',b'>None<'))[0]['value'],D(0))
        with self.assertRaises(ValueError):parse_inline(body.replace(b'>no<',b'>unknown<'))

    def test_registered_fixed_zero_maps_text_but_untransformed_text_is_not_zero(self):
        self.assertEqual(parse_inline(inline('none','format="ixt:fixed-zero"'))[0]['value'],D(0))
        with self.assertRaises(ValueError):parse_inline(inline('none'))


if __name__=='__main__':unittest.main()
