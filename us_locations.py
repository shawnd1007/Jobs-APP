"""Read published U.S. work locations without inferring eligibility from pay."""
import re


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
COUNTRY_NAME = re.compile(r'\bUnited States(?: of America)?\b|\busa\b', re.I)
COUNTRY_EXCLUDED = re.compile(
    r'\b(?:outside|excluding|except(?: for)?|not in|not eligible in)\s+(?:the\s+)?'
    r'(?:United States\b|U\.?S\.?A?\b)', re.I
)
FOREIGN_SCOPE = re.compile(
    r'\b(?:Canada|Brazil|United Kingdom|UK|Mexico|Europe|European Union|EMEA|APAC|'
    r'Latin America|LATAM|India|Australia|Germany|France|Japan|Tbilisi|global|worldwide)\b', re.I
)


def state_code(value):
    name = re.sub(r'[^a-z ]', '', value.casefold()).strip()
    return STATE_NAMES.get(name) or (name.upper() if name.upper() in STATES else None)


def location_states(location):
    clean = COUNTRY_NAME.sub('', location)
    # An isolated abbreviation such as CA or GA can also name a country.
    # A city, state pair or a U.S. country label gives it context.
    states = set()
    for segment in re.split(r'[,;/|]', clean):
        part = re.sub(r'\b(?:fully|remote|hybrid|on[- ]?site)\b', '', segment, flags=re.I).strip(' –—-()')
        # Keep the country Georgia ambiguous unless the posting gives U.S. context.
        if part.casefold() == 'georgia' and not (has_country(location) or ',' in clean.strip(' ,')):
            continue
        code = state_code(part)
        if code and (part.casefold() in STATE_NAMES or ',' in location or has_country(location)):
            states.add(code)
    return states


def has_country(text):
    return bool(COUNTRY.search(text) or COUNTRY_NAME.search(text))


def is_us_location(location):
    return not COUNTRY_EXCLUDED.search(location) and (
        has_country(location) or (not FOREIGN_SCOPE.search(location) and bool(location_states(location)))
    )


def remote_eligibility(location, description, target):
    """Return a verdict for a U.S. remote preference, or None for other preferences."""
    target_states = location_states(target)
    if not target_states and not has_country(target):
        return None
    if COUNTRY_EXCLUDED.search(location):
        return 'avoid', 'The published remote location excludes the United States.'
    if not is_us_location(location):
        if FOREIGN_SCOPE.search(location) and not re.search(r'\b(?:global|worldwide)\b', location, re.I):
            return 'avoid', 'The published remote location is outside the United States.'
        return 'review', 'Confirm the employer can hire in ' + target + '.'

    # Only location and residency clauses can narrow the geographic scope.
    # General wording such as "only shortlisted candidates will be contacted" does not.
    text = location + '\n' + description
    excluded = re.findall(
        r'(?:\bexclud(?:es|ing)|\bexcept(?: for)?|\bnot eligible in|\bcannot hire in)\s+([^.!?;\n]+)',
        text, re.I,
    )
    restricted = re.findall(
        r'(?:\b(?:must|required to)\s+(?:reside|live|be based|be located)\s+(?:in|within)|'
        r'\b(?:remote|hiring)\s+(?:only|restricted)\s+(?:in|to)|'
        r'\b(?:eligible|approved)\s+states\s*(?:are\s+|:\s*))\s*([^.!?;\n]+)',
        text, re.I,
    )
    for clause in excluded:
        areas = re.sub(r'\s+(?:and|or)\s+', ', ', clause, flags=re.I)
        if has_country(clause) or target_states & location_states(areas + ', United States'):
            return 'avoid', 'The employer excludes your remote work region.'
    for clause in restricted:
        if has_country(clause):
            continue
        places = re.sub(r'^(?:the )?states? of ', '', clause, flags=re.I)
        allowed = location_states(re.sub(r'\s+(?:and|or)\s+', ', ', places, flags=re.I) + ', United States')
        if allowed and target_states:
            if not target_states & allowed:
                return 'avoid', 'The employer limits remote work to other states.'
        else:
            return 'review', 'Confirm the employer’s remote hiring restrictions.'
    states = location_states(location)
    if states:
        if target_states and not target_states & states:
            return 'avoid', 'The published remote location is outside your state.'
        if not target_states:
            return 'review', 'Check which states the employer can hire in.'
    return 'pass', 'Published remote location includes your region.'
