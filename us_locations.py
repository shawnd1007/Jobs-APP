"""Read published U.S. work locations without inferring eligibility from pay."""
import re
import unicodedata


STATES = dict(zip(
    ('AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO '
     'MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY').split(),
    ('Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|District of Columbia|'
     'Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|'
     'Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|'
     'New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|'
     'Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|'
     'West Virginia|Wisconsin|Wyoming').split('|'),
    strict=True,
))
STATE_NAMES = {name.casefold(): code for code, name in STATES.items()}
STATE_NAMES['washington dc'] = 'DC'
COUNTRY = re.compile(r'\b(?:United States(?: of America)?|U\.?S\.?A\.?)\b|(?<!\w)U\.?S\.?(?!\w)', re.I)
COUNTRY_EXCLUDED = re.compile(
    r'\b(?:outside|excluding|except(?: for)?|not in|not eligible in)\s+(?:the\s+)?'
    r'(?:United States\b|U\.?S\.?A?\b)', re.I
)
FOREIGN_SCOPE = re.compile(
    r'\b(?:Canada|Brazil|United Kingdom|UK|(?<!New )Mexico(?!, [A-Z]{2}\b)|Europe|European Union|EMEA|APAC|'
    r'Latin America|LATAM|India|Australia|Germany|France|Japan|Colombia|Argentina|Chile|'
    r'Peru|Costa Rica|Spain|Portugal|Ireland|Philippines|Singapore|China|Taiwan|'
    r'New Zealand|South Africa|Poland|Romania|Nigeria|Pakistan|Ukraine|Tbilisi)\b', re.I
)


def state_code(value):
    name = re.sub(r'[^a-z ]', '', value.casefold()).strip()
    return STATE_NAMES.get(name) or (name.upper() if name.upper() in STATES else None)


WORK_LABEL = re.compile(r'\b(?:fully|remote|hybrid|on[- ]?site|only)\b', re.I)
FOREIGN_CITY = re.compile(r'^\s*(?:(?:bogota(?:\s+d\.?c\.?)?|medellin|cartagena)(?:,\s*[^,]+)?\s*,\s*co|(?:toronto|vancouver|montreal)\s*,\s*ca)\b', re.I)
BAY_AREA = re.compile(r'\b(?:san francisco(?: bay area)?|bay area)\b', re.I)
RESTRICTION = re.compile(
    r'(?:\b(?:must|required to)\s+(?:reside|live|be based|be located)\s+(?:in|within)|'
    r'\b(?:remote|hiring)\s+(?:only|restricted)\s+(?:in|to)|'
    r'\b(?:eligible|approved|hiring)\s+states\s*(?:are\s+|:\s*)|'
    r'\b(?:we|employer)\s+(?:can )?only hires?\s+(?:candidates )?(?:in|from|based in)|'
    r'^\s*(?:this\s+)?(?:role|position|job)\s+(?:is|will be)\s+'
    r'(?:(?:fully\s+)?remote\s*,?\s+and\s+)?(?:based|located)\s+in)\s*(.+)', re.I
)
EXCLUSION = re.compile(
    r'(?:\bexclud(?:es|ing)|\bexcept(?: for)?|\bnot eligible in|\bcannot hire in)\s+(.+)', re.I
)


def has_country(text):
    return bool(COUNTRY.search(text))


def foreign_location(location):
    plain = ''.join(c for c in unicodedata.normalize('NFKD', location) if not unicodedata.combining(c))
    plain = WORK_LABEL.sub('', plain).strip(' –—-()')
    return bool(FOREIGN_SCOPE.search(plain) or FOREIGN_CITY.search(plain)
                or re.search(r'\b(?:outside|excluding|except(?: for)?|not in) (?:the )?(?:usa?|united states)\b', plain, re.I))


def location_states(location):
    if foreign_location(location):
        return set()
    clean = COUNTRY.sub('', location)
    states = set()
    for segment in re.split(r'[,;/|()]', clean):
        part = WORK_LABEL.sub('', segment).strip(' –—-()')
        part = re.sub(r'\s+\d{5}(?:-\d{4})?$', '', part)
        if part.casefold() == 'georgia' and not (has_country(location) or ',' in clean.strip(' ,')):
            continue
        code = state_code(part)
        if code and (part.casefold() in STATE_NAMES or ',' in clean.strip(' ,') or has_country(location)):
            states.add(code)
        if BAY_AREA.fullmatch(part):
            states.add('CA')
    return states


def office_locations(location):
    """Return normalized city/state pairs for published U.S. office locations."""
    if not is_us_location(location):
        return set()
    offices = set()
    for part in re.split(r'[;|/]', COUNTRY.sub('', location)):
        parts = [item.strip(' –—-()') for item in WORK_LABEL.sub('', part).split(',') if item.strip(' –—-()')]
        if len(parts) >= 2:
            city, region = parts[:2]
            region = re.sub(r'\s+\d{5}(?:-\d{4})?$', '', region)
            if (code := state_code(region)) and (not state_code(city) or code == 'DC'):
                normalized = unicodedata.normalize('NFKC', city).casefold()
                offices.add((' '.join(re.findall(r'[^\W_]+', normalized)), code))
    return offices


def location_clauses(description):
    """Read hiring terms before compensation and avoid matching pay-location tiers."""
    for line in description.splitlines():
        for sentence in re.split(r'[!?;]|\.(?=\s+[A-Z])', line):
            sentence = sentence.strip().rstrip('.')
            if re.search(r'\b(?:salary|compensation|benefits|pay range)\b', sentence, re.I):
                continue
            if match := RESTRICTION.search(sentence):
                yield 'only', match[1]
            if (match := EXCLUSION.search(sentence)) and (has_country(match[1]) or restriction_states(match[1])
                    or re.search(r'\b(?:hire|hiring|resident|reside|remote|eligible|location|state)\b', sentence, re.I)):
                yield 'excludes', match[1]


def is_us_location(location, description='', *, remote=False):
    if COUNTRY_EXCLUDED.search(location):
        return False
    if any(not foreign_location(part) and (has_country(part) or location_states(part))
           for part in re.split(r'[;|/]', location)):
        return True
    if remote and not foreign_location(location):
        return any(kind == 'only' and not foreign_location(place) and
                   (has_country(place) or location_states(place))
                   for kind, place in location_clauses(description))
    return False


def remote_restrictions(location, description):
    header = re.split(r'\bexclud(?:es|ing)\b|\bexcept(?: for)?\b', location, maxsplit=1, flags=re.I)[0]
    country = has_country(header)
    if not country or not re.search(r'(?:\bor\b|[;|/])\s*remote\s*[, -]*\s*(?:usa?|united states)\b', header, re.I):
        if states := location_states(header):
            yield 'header', header, states
    if match := EXCLUSION.search(location):
        yield 'excludes', match[1], restriction_states(match[1])
    for kind, place in location_clauses(description):
        yield kind, place, restriction_states(place)


def restriction_states(place):
    areas = re.sub(r'\s+(?:and|or)\s+', ', ', place, flags=re.I)
    areas = re.sub(r'^(?:(?:the )?states? of |the )|\s+only$', '', areas, flags=re.I)
    return location_states(areas if foreign_location(areas) else areas + ', United States')


def remote_eligibility(location, description, target):
    """Return a verdict for a U.S. remote preference, or None for other preferences."""
    target_states = restriction_states(target) if target else set()
    if not target_states and not has_country(target):
        return None
    if COUNTRY_EXCLUDED.search(location) or (foreign_location(location) and not is_us_location(location)):
        return 'avoid', 'The published remote location is outside the United States.'
    if not is_us_location(location, description, remote=True):
        return 'review', 'Confirm the employer can hire in ' + target + '.'

    review_reason = None
    for kind, place, states in remote_restrictions(location, description):
        if kind == 'excludes':
            if target_states & states or (has_country(place) and not states):
                return 'avoid', 'The employer excludes your remote work region.'
            if not target_states or not states:
                review_reason = 'Confirm the employer’s remote hiring exclusions.'
            continue
        if foreign_location(place) or (states and target_states and not target_states & states):
            return 'avoid', 'The employer limits this role to ' + place.strip() + '.'
        if BAY_AREA.search(place) and not BAY_AREA.search(target):
            review_reason = 'The employer requires a Bay Area base. Confirm you can work there.'
        elif kind == 'only' and (offices := office_locations(place)) and not (offices & office_locations(target)):
            review_reason = 'Confirm that you can work from the employer’s required city.'
        elif (states and not target_states) or (not states and not has_country(place)):
            review_reason = 'Confirm the employer’s remote hiring restrictions.'
    if review_reason:
        return 'review', review_reason
    return 'pass', 'Published remote location includes your region.'
