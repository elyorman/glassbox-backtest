"""Treasury par-yield CSV parsing and caching; rows are copied from published U.S. Treasury files."""

from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from quant_core.data.treasury import SERIES, SOURCE, TreasuryClient, TreasuryResponse, cash_rate_series, parse_year

Y2008 = (b'Date,"1 Mo","3 Mo","6 Mo","1 Yr","2 Yr","3 Yr","5 Yr","7 Yr","10 Yr","20 Yr","30 Yr"\n'
         b'12/31/2008,0.11,0.11,0.27,0.37,0.76,1.00,1.55,1.87,2.25,3.05,2.69\n'
         b'12/24/2008,0.00,,0.23,0.40,0.90,1.14,1.54,1.83,2.20,2.94,2.63\n'
         b'12/23/2008,0.01,0.02,0.24,0.39,0.86,1.10,1.53,1.83,2.17,2.92,2.59')
Y2010 = (b'Date,"1 Mo","3 Mo","6 Mo","1 Yr","2 Yr","3 Yr","5 Yr","7 Yr","10 Yr","20 Yr","30 Yr"\n'
         b'10/12/2010,0.12,0.13,0.18,0.24,0.39,0.61,1.16,1.76,2.42,3.29,3.75\n'
         b'10/11/2010,,,,,,,,,,,\n'
         b'10/08/2010,0.11,0.13,0.18,0.23,0.37,0.60,1.11,1.71,2.38,3.25,3.71')
Y2026 = (b'Date,"1 Mo","1.5 Month","2 Mo","3 Mo","4 Mo","6 Mo","1 Yr","2 Yr","3 Yr","5 Yr","7 Yr","10 Yr","20 Yr","30 Yr"\n'
         b'01/02/2026,3.72,3.71,3.66,3.65,3.62,3.58,3.47,3.47,3.55,3.74,3.95,4.19,4.81,4.86')
AT = datetime(2026, 10, 10, tzinfo=timezone.utc)


class ParseTests(unittest.TestCase):
    def test_three_month_column_is_read_by_name_as_ascending_fractions(self):
        self.assertEqual(parse_year(Y2008, 2008), ((date(2008, 12, 23), Decimal("0.0002")),
                                                   (date(2008, 12, 31), Decimal("0.0011"))))
        self.assertEqual(parse_year(Y2026, 2026), ((date(2026, 1, 2), Decimal("0.0365")),))

    def test_blank_cells_mean_no_observation(self):
        self.assertEqual([day for day, _ in parse_year(Y2010, 2010)], [date(2010, 10, 8), date(2010, 10, 12)])

    def test_malformed_files_are_refused(self):
        header = b'Date,"3 Mo"\n'
        cases = [(b'Date,"6 Mo"\n01/02/2008,1.0', "lacks"), (header + b'2008-01-02,1.0', "line 2"),
                 (header + b'01/02/2008,abc', "line 2"), (header + b'01/02/2007,1.0', "dated 2007-01-02"),
                 (header + b'01/02/2008,1.0\n01/02/2008,1.1', "repeats"), (b'\xff\xfe', "not a CSV")]
        for raw, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                parse_year(raw, 2008)

    def test_years_combine_into_one_series(self):
        later = datetime(2026, 10, 11, tzinfo=timezone.utc)
        rates = cash_rate_series([TreasuryResponse(2010, Y2010, later), TreasuryResponse(2008, Y2008, AT)])
        self.assertEqual((rates.source, rates.series, rates.retrieved_at), (SOURCE, SERIES, later))
        self.assertEqual(rates.observations[0], (date(2008, 12, 23), Decimal("0.0002")))
        self.assertEqual(len(rates.observations), 4)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            cash_rate_series([TreasuryResponse(2008, Y2008, AT), TreasuryResponse(2008, Y2008, AT)])
        with self.assertRaises(ValueError):
            cash_rate_series([])


class ClientTests(unittest.TestCase):
    def download(self, client, year, raw, now=AT):
        with patch("quant_core.data.treasury._now", return_value=now), \
                patch("quant_core.data.remote.build_opener") as opener:
            opener.return_value.open.return_value = BytesIO(raw)
            response = client.year(year)
        return response, opener.return_value.open.call_count

    def test_completed_years_are_cached_and_not_downloaded_again(self):
        with TemporaryDirectory() as directory:
            client = TreasuryClient(Path(directory))
            first, calls = self.download(client, 2008, Y2008)
            self.assertEqual((first.raw, calls), (Y2008, 1))
            second, calls = self.download(client, 2008, b"unused")
            self.assertEqual((second, calls), (first, 0))

    def test_the_current_year_is_downloaded_each_time_and_kept(self):
        with TemporaryDirectory() as directory:
            client = TreasuryClient(Path(directory))
            self.download(client, 2026, Y2026)
            _, calls = self.download(client, 2026, Y2026)
            self.assertEqual(calls, 1)
            self.assertEqual(len(list(Path(directory).glob("*.csv"))), 1)
            self.assertEqual(list(Path(directory).glob("*.request.json")), [])
            # Early January: the previous year may still receive its last rows.
            _, calls = self.download(client, 2026, Y2026, datetime(2027, 1, 5, tzinfo=timezone.utc))
            self.assertEqual(calls, 1)
            self.assertEqual(list(Path(directory).glob("*.request.json")), [])

    def test_invalid_years_and_responses_are_not_cached(self):
        with TemporaryDirectory() as directory:
            client = TreasuryClient(Path(directory))
            for year in (1989, 2027, "2008"):
                with self.subTest(year=year), self.assertRaisesRegex(ValueError, "Treasury year"):
                    self.download(client, year, Y2008)
            with self.assertRaisesRegex(ValueError, "lacks"):
                self.download(client, 2008, b"<html>maintenance</html>")
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
