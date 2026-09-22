import unittest
from datetime import datetime, timezone

from scripts.collect import parse_index, merge_items, collect


def page(rows):
    return ('<select name="region_menu"><option selected>California</option></select>'
            '<strong><font>September 21, 2026</font></strong>'
            '<table><tr><td>Received</td><td>List</td><td>From</td><td>Subject</td></tr>'
            + rows + '</table>')


def row(id='123', title='[southbaybirds] American Redstart', group='SouthBayBirds', time='9/21/26 12:22 pm'):
    return (f'<tr class="regular-text"><td>{time}</td><td>{group}</td>'
            f'<td>Author &lt;private@example.com&gt;</td><td>'
            f'<a href="/?rm=message;id={id}">{title}</a></td></tr>')


class CollectorTests(unittest.TestCase):
    def test_extracts_metadata_without_author_or_body(self):
        items = parse_index(page(row()), '2026-09-21')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], 'American Redstart')
        self.assertEqual(items[0]['reported_at'], '2026-09-21T12:22:00')
        self.assertEqual(items[0]['source_url'], 'https://digest-test.sialia.com/?rm=message;id=123')
        self.assertNotIn('private', str(items))

    def test_filters_outside_bay_lists_and_marks_replies_without_claiming_sighting(self):
        items = parse_index(page(row(title='Re: [southbaybirds] American Redstart') + row('124', group='MBBIRDS')), '2026-09-21')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['kind'], 'reply')

    def test_rejects_homepage_and_wrong_day_instead_of_silent_empty(self):
        for html in ['<html>Welcome</html>', page(row()).replace('September 21', 'September 20')]:
            with self.assertRaises(ValueError):
                parse_index(html, '2026-09-21')

    def test_bad_row_fails_instead_of_dropping_a_report(self):
        with self.assertRaises(ValueError):
            parse_index(page(row(time='yesterday')), '2026-09-21')

    def test_deduplicates_and_retains_first_seen_and_sorts_by_report_time(self):
        old = dict(parse_index(page(row()), '2026-09-21')[0], first_seen_at='2026-09-21T20:00:00+00:00')
        incoming = parse_index(page(row() + row('124', time='9/21/26 1:22 pm')), '2026-09-21')
        merged = merge_items([old], incoming + incoming, datetime(2026, 9, 22, tzinfo=timezone.utc))
        self.assertEqual([x['id'] for x in merged], ['sialia:124', 'sialia:123'])
        self.assertEqual(merged[1]['first_seen_at'], old['first_seen_at'])

    def test_failure_preserves_data_and_last_success(self):
        old = dict(parse_index(page(row()), '2026-09-21')[0], first_seen_at='2026-09-21T20:00:00+00:00')
        previous = {'items': [old], 'sources': {'sialia': {'last_success_at': '2026-09-21T20:00:00+00:00'}}}
        def failed(url):
            raise OSError('offline')
        result = collect(previous, datetime(2026, 9, 22, tzinfo=timezone.utc), fetch=failed, days=2)
        self.assertEqual(result['items'], [old])
        self.assertEqual(result['sources']['sialia']['status'], 'error')
        self.assertEqual(result['sources']['sialia']['last_success_at'], previous['sources']['sialia']['last_success_at'])

    def test_empty_valid_index_is_success(self):
        self.assertEqual(parse_index(page(''), '2026-09-21'), [])

    def test_partial_fetch_reports_error_but_saves_successful_day(self):
        def fetch(url):
            if 'days_ago=0;' in url:
                return page(row())
            raise OSError('offline')
        result = collect({}, datetime(2026, 9, 22, tzinfo=timezone.utc), fetch=fetch, days=2)
        self.assertEqual(result['sources']['sialia']['status'], 'partial')
        self.assertEqual(len(result['items']), 1)
        self.assertIsNone(result['sources']['sialia']['last_success_at'])

    def test_expires_records_after_retention_window(self):
        item = parse_index(page(row()), '2026-09-21')[0]
        self.assertEqual(merge_items([item], [], datetime(2026, 11, 1, tzinfo=timezone.utc)), [])


if __name__ == '__main__':
    unittest.main()
