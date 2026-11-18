"""Credentialed U.S. Office of Personnel Management public job search."""
import json
import math
import re
from urllib.parse import urlencode
from urllib.request import Request


SOURCE = 'USAJOBS'
ENDPOINT = 'https://data.usajobs.gov/api/Search'
POSTING = re.compile(r'https://www\.usajobs\.gov/(?:job|GetJob/ViewDetails)/(?P<id>[0-9]+)/?', re.I)


def search(read_response, *, email, key, title, remote, location=''):
    query = dict(Keyword=title, HiringPath='public', ResultsPerPage=15,
                 RemoteIndicator=str(remote).lower(), Fields='Full')
    if location and not remote:
        query.update(LocationName=location, Radius=25)
    request = Request(ENDPOINT + '?' + urlencode(query))
    # These headers belong to the API host and must not follow redirects.
    request.add_unredirected_header('User-Agent', email)
    request.add_unredirected_header('Authorization-Key', key)
    raw, _ = read_response(request, max_bytes=2_000_000)
    items = json.loads(raw)['SearchResult']['SearchResultItems']
    for item in items[:15]:
        record = item.get('MatchedObjectDescriptor') or {}
        match = POSTING.fullmatch(record.get('PositionURI') or '')
        if not match or not record.get('PositionTitle') or not record.get('OrganizationName'):
            continue
        url = 'https://www.usajobs.gov/job/' + match['id']
        published_locations = [
            ', '.join(dict.fromkeys(value for value in (place.get('LocationName'), place.get('CountryCode')) if value))
            for place in (record.get('PositionLocation') or []) if isinstance(place, dict)
        ]
        location_text = '; '.join(place for place in published_locations if place)
        location_text = location_text or record.get('PositionLocationDisplay') or ''
        # The official remote query establishes remote work. Use the actual
        # published duty locations to decide whether the posting is U.S.-based.
        locations = ('Remote — ' if remote else '') + location_text
        details = (record.get('UserArea') or {}).get('Details') or {}
        description = '\n\n'.join(
            value for value in (details.get('JobSummary'), record.get('QualificationSummary'))
            if isinstance(value, str) and value
        )
        job = {
            'title': record['PositionTitle'], 'employer': record['OrganizationName'], 'url': url,
            'location': locations, 'remote': remote, 'description': description,
            'posted': (record.get('PublicationStartDate') or '')[:10], 'source': SOURCE,
            'availability': 'Needs Verification', 'salary_text': 'Check pay in the USAJOBS announcement',
            'application_evidence': 'Public USAJOBS announcement. Check the official posting for requirements.',
        }
        remuneration = record.get('PositionRemuneration') or []
        if isinstance(remuneration, list) and len(remuneration) == 1 and isinstance(remuneration[0], dict):
            pay = remuneration[0]
            interval = {'pa': 'year', 'per year': 'year', 'per hour': 'hour'}.get(
                str(pay.get('RateIntervalCode', '')).lower()
            )
            try:
                low, high = float(pay['MinimumRange']), float(pay['MaximumRange'])
            except (KeyError, ValueError, TypeError):
                pass
            else:
                if interval and math.isfinite(low) and math.isfinite(high) and 0 < low <= high:
                    job.update(salary_text=f'${low:,.2f} to ${high:,.2f} per {interval}',
                               salary_min=low, salary_max=high, salary_currency='USD',
                               salary_type='base', salary_period=interval)
        yield job
