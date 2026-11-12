"""Evidence-only advice. No provider calls or inferred candidate qualifications."""
import datetime as dt
import re


def contains(text, term):
    return bool(term.strip() and re.search(r'(?<![\w+#])' + re.escape(term.strip()) + r'(?![\w+#])', text, re.I))


def explain(job, cfg, stamp=None):
    text = job.get('title', '') + ' ' + job.get('description', '')
    evidence = cfg.get('resume_evidence', {})
    selected = cfg.get('preferred_skills', [])
    supported = [s for s in selected if s in evidence and contains(evidence[s], s)]
    matched = [s for s in supported if contains(text, s)]
    unknown = []
    if not job.get('location'): unknown.append('Location is not published; confirm before applying.')
    if not job.get('salary_max'): unknown.append('Comparable annual base salary is unknown.')
    checks = [f"Minimum annual USD base: {cfg['salary_floor']:,}",
              'Location eligibility: ' + job.get('location_eligibility', 'Review')]
    verified = job.get('application_verified')
    state = 'unverified'
    if job.get('availability') == 'Closed': state = 'unavailable'
    elif verified and job.get('verification_provenance'):
        try:
            age = ((stamp or dt.datetime.now(dt.timezone.utc)) - dt.datetime.fromisoformat(verified)).total_seconds()
            state = 'verified' if 0 <= age <= cfg.get('verification_valid_hours', 24) * 3600 else 'stale'
        except (ValueError, TypeError): state = 'unverified'
    return dict(
        resume_matches=matched,
        selected_without_evidence=[s for s in selected if s not in supported],
        preparation=[f'Consider emphasizing “{s}”: {evidence[s]}' for s in matched],
        unknowns=unknown,
        hard_requirements=checks,
        preferences=['Target roles: ' + ', '.join(cfg['categories']), 'Skills are preferences, not hiring requirements.'],
        link_status=state,
        checked_at=verified or '',
        advice_method='Rules using user-reviewed résumé excerpts; no AI inference. Fit is not a hiring probability.',
    )
