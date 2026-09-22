"""Public Sialia link index. Python standard library only; no AI or credentials."""
import argparse
import json
import re
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE = 'https://digest-test.sialia.com/'
GROUPS = {
    'SouthBayBirds': 'South Bay',
    'peninsula-birding': 'Peninsula',
    'SFBirds': 'San Francisco',
    'EBB-Sightings': 'East Bay',
    'northbaybirds': 'North Bay',
}


class IndexParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.cells = None
        self.cell = None
        self.href = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr':
            self.cells = [] if attrs.get('class') == 'regular-text' else None
            self.href = None
        elif tag == 'td' and self.cells is not None:
            self.cell = []
        elif tag == 'a' and self.cells is not None:
            href = attrs.get('href', '')
            if re.fullmatch(r'/\?rm=message;id=\d+', href):
                self.href = href

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            if self.cells is not None:
                self.cells.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr':
            if self.cells is not None and self.href:
                self.rows.append((self.cells, self.href))
            self.cells = None
            self.cell = None


def parse_index(html, expected_date):
    heading = re.search(r'<strong>\s*<font[^>]*>([^<]+)</font>\s*</strong>', html)
    if not heading or 'region_menu' not in html or 'Received' not in html or 'Subject' not in html:
        raise ValueError('Unrecognized Sialia index layout')
    if datetime.strptime(heading[1].strip(), '%B %d, %Y').date().isoformat() != expected_date:
        raise ValueError('Index date does not match requested day')
    parser = IndexParser()
    parser.feed(html)
    items = []
    # Detect a format change that would otherwise turn a populated page into zero rows.
    if 'rm=message;id=' in html and not parser.rows:
        raise ValueError('Message links present but no report rows parsed')
    for cells, href in parser.rows:
        if len(cells) != 4:
            raise ValueError('Unexpected message row layout')
        received, group, _author, subject = cells
        if group not in GROUPS:
            continue
        reported = datetime.strptime(received, '%m/%d/%y %I:%M %p')
        reply = bool(re.match(r'^(re|fwd?)\s*:', subject, flags=re.I))
        title = re.sub(r'^(?:(?:re|fwd?)\s*:\s*|\[[^\]]+\]\s*)+', '', subject, flags=re.I).strip()
        if not title:
            raise ValueError('Empty message title')
        items.append({
            'id': 'sialia:' + href.rsplit('=', 1)[1],
            'title': title,
            'source': 'sialia',
            'list': group,
            'area': GROUPS[group],
            'source_url': BASE.rstrip('/') + href,
            # Wall time as displayed by Sialia. Its timezone is not documented.
            'reported_at': reported.isoformat(),
            'reported_at_display': received,
            'kind': 'reply' if reply else 'post',
        })
    return items


def merge_items(previous, incoming, now):
    by_id = {item['id']: item for item in previous}
    for item in incoming:
        first_seen = by_id.get(item['id'], {}).get('first_seen_at', now.isoformat())
        by_id[item['id']] = dict(item, first_seen_at=first_seen)
    cutoff = (now.astimezone(ZoneInfo('America/Los_Angeles')).date() - timedelta(days=30)).isoformat()
    return sorted((item for item in by_id.values() if item['reported_at'][:10] >= cutoff),
                  key=lambda item: (item['reported_at'], item['id']), reverse=True)


def fetch_html(url):
    request = Request(url, headers={'User-Agent': 'birding-link-index/1.0 (+https://github.com/lincleejun/birding)'})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return response.read(4_000_000).decode('utf-8')
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))


def collect(previous, now, fetch=fetch_html, days=2):
    incoming, errors, fetched_days = [], [], []
    today = now.astimezone(ZoneInfo('America/Los_Angeles')).date()
    for days_ago in range(days):
        day = (today - timedelta(days=days_ago)).isoformat()
        try:
            incoming.extend(parse_index(fetch(f'{BASE}?rm=index;days_ago={days_ago};region=2'), day))
            fetched_days.append(day)
        except (OSError, ValueError) as exc:
            errors.append({'date': day, 'error': f'{type(exc).__name__}: {exc}'[:250]})
    old_source = previous.get('sources', {}).get('sialia', {})
    status = 'ok' if not errors else ('partial' if fetched_days else 'error')
    items = merge_items(previous.get('items', []), incoming, now)
    old_ids = {item['id'] for item in previous.get('items', [])}
    return {
        'schema_version': 1,
        'generated_at': now.isoformat(),
        'retention_days': 30,
        'order': 'reported_at descending; source wall time, timezone unspecified',
        'sources': {
            'sialia': {
                'status': status,
                'last_attempt_at': now.isoformat(),
                'last_success_at': now.isoformat() if status == 'ok' else old_source.get('last_success_at'),
                'fetched_days': fetched_days,
                'errors': errors,
                'lists': list(GROUPS),
            },
            'ebird': {'status': 'not_configured', 'reason': 'Access and public redistribution scope pending verification',
                      'url': 'https://ebird.org/alert/summary?sid=SN36076'},
        },
        'stats': {'total': len(items), 'new_this_run': sum(item['id'] not in old_ids for item in items)},
        'items': items,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='data/feed.json')
    parser.add_argument('--days', type=int, help='Initial backfill defaults to 7 days; subsequent runs fetch 2 days')
    args = parser.parse_args()
    output = Path(args.output)
    previous = json.loads(output.read_text()) if output.exists() else {}
    days = args.days if args.days is not None else (2 if previous.get('items') else 7)
    if not 1 <= days <= 30:
        parser.error('--days must be between 1 and 30')
    result = collect(previous, datetime.now(timezone.utc), days=days)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(output)
    print(json.dumps({'stats': result['stats'], 'source': result['sources']['sialia']}, ensure_ascii=False))
    # Workflow publishes failure status as well as retained data before turning red.
    return 0 if result['sources']['sialia']['status'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
