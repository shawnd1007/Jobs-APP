"""Preview or import confirmed application history from a CSV export."""
import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import json

import app


def import_history(path, *, apply=False):
    if not app.DB.is_file():
        raise ValueError('Start the Jobs workspace before importing history.')
    with open(path, newline='', encoding='utf-8-sig') as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or ())
        if 'status' not in columns or not ('url' in columns or {'employer', 'requisition'} <= columns):
            raise ValueError('Use a status column and either url or employer and requisition columns.')
        entries = list(enumerate(reader, start=2))

    if apply:
        app.backup()
    with app.connect() as connection:
        connection.execute('BEGIN IMMEDIATE' if apply else 'BEGIN')
        jobs = connection.execute('''
            SELECT jobs.id, jobs.identity, jobs.listing, tracking.status, tracking.version,
                   tracking.application_date, tracking.follow_up, tracking.notes
            FROM jobs JOIN tracking ON jobs.id = tracking.job_id
        ''').fetchall()
        by_url = defaultdict(set)
        by_requisition = defaultdict(set)
        for job in jobs:
            listing = json.loads(job['listing'])
            by_url[job['identity']].add(job['id'])
            by_url[app.identity(listing['url'])].add(job['id'])
            requisition = str(listing.get('requisition') or '').strip().casefold()
            if requisition:
                by_requisition[app.norm(listing.get('employer', '')), requisition].add(job['id'])
        by_id = {job['id']: job for job in jobs}
        ready = []
        report = []
        for number, row in entries:
            url = (row.get('url') or '').strip()
            employer = app.norm(row.get('employer') or '')
            requisition = (row.get('requisition') or '').strip().casefold()
            status = (row.get('status') or '').strip()
            dates = [(row.get(key) or '').strip() for key in ('application_date', 'follow_up')]
            note = (row.get('notes') or '').strip()
            try:
                dates = [dt.date.fromisoformat(value).isoformat() if value else '' for value in dates]
                if status not in app.STATUSES:
                    raise ValueError()
                ids = by_url[app.identity(url)] if url else by_requisition[employer, requisition]
                if url and employer and requisition:
                    ids = ids & by_requisition[employer, requisition]
            except ValueError:
                report.append({'row': number, 'result': 'invalid status, date, or URL'})
                continue
            if len(ids) != 1:
                report.append({'row': number, 'result': 'no unique requisition match'})
                continue
            job = by_id[next(iter(ids))]
            ready.append((number, job, status, dates, note))

        repetitions = Counter(job['id'] for _, job, _, _, _ in ready)
        for number, job, status, dates, note in ready:
            if repetitions[job['id']] > 1:
                result = 'duplicate input for the same requisition'
            elif job['version'] or job['status'] != 'Needs Verification' or any(
                job[key] for key in ('application_date', 'follow_up', 'notes')
            ):
                result = 'existing tracking preserved'
            elif apply:
                stamp = app.now()
                connection.execute('''
                    UPDATE tracking SET status=?, application_date=?, follow_up=?, notes=?,
                    updated=?, version=version+1 WHERE job_id=?
                ''', (status, *dates, note[:10000], stamp, job['id']))
                connection.execute('INSERT INTO events(job_id,at,detail) VALUES(?,?,?)',
                                   (job['id'], stamp, json.dumps({'action': 'history_import', 'row': number})))
                result = 'imported'
            else:
                result = 'ready to import'
            report.append({'row': number, 'job_id': job['id'], 'result': result})
    return sorted(report, key=lambda item: item['row'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_path')
    parser.add_argument('--apply', action='store_true', help='Back up and import the eligible rows')
    args = parser.parse_args()
    try:
        print(json.dumps(import_history(args.csv_path, apply=args.apply), indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, f'{exc}\n')
