"""Metro area definitions for location grouping.

Each metro is: (slug, display_name, state, [city_patterns])
City patterns are lowercase prefixes/names that match against the normalized city.
"""

from __future__ import annotations

METROS = [
    # Texas
    ("dallas-fort-worth", "Dallas-Fort Worth", "TX", ["dallas", "fort worth", "arlington", "plano", "irving", "frisco", "mckinney", "denton", "garland", "grand prairie", "mesquite", "carrollton", "lewisville", "richardson", "allen"]),
    ("houston", "Houston", "TX", ["houston", "sugar land", "pasadena", "pearland", "league city", "baytown", "conroe", "the woodlands", "katy", "missouri city", "spring"]),
    ("san-antonio", "San Antonio", "TX", ["san antonio", "new braunfels", "san marcos"]),
    ("austin", "Austin", "TX", ["austin", "round rock", "cedar park", "georgetown", "pflugerville", "san marcos"]),

    # California
    ("los-angeles", "Los Angeles", "CA", ["los angeles", "beverly hills", "santa monica", "glendale", "burbank", "pasadena", "long beach", "torrance", "inglewood", "west hollywood", "culver city", "downey", "el monte", "pomona", "compton", "hawthorne"]),
    ("san-francisco-bay-area", "San Francisco Bay Area", "CA", ["san francisco", "oakland", "san jose", "berkeley", "fremont", "sunnyvale", "santa clara", "hayward", "mountain view", "palo alto", "redwood city", "walnut creek", "concord", "richmond", "daly city", "san mateo", "menlo park", "milpitas"]),
    ("san-diego", "San Diego", "CA", ["san diego", "chula vista", "carlsbad", "escondido", "oceanside", "el cajon", "la mesa"]),
    ("sacramento", "Sacramento", "CA", ["sacramento", "roseville", "elk grove", "folsom", "rancho cordova"]),

    # New York
    ("nyc-metro", "New York City Metro", "NY", ["new york", "brooklyn", "queens", "bronx", "manhattan", "staten island", "yonkers", "white plains", "new rochelle", "mount vernon"]),
    ("nyc-metro-nj", "NYC Metro", "NJ", ["newark", "jersey city", "hoboken", "elizabeth", "paterson", "clifton", "passaic", "east orange", "hackensack", "fort lee"]),

    # Illinois
    ("chicago", "Chicago", "IL", ["chicago", "evanston", "oak park", "cicero", "berwyn", "skokie", "des plaines", "arlington heights", "schaumburg", "naperville", "aurora", "joliet", "elgin", "waukegan", "oak brook", "hinsdale"]),

    # Florida
    ("miami", "Miami", "FL", ["miami", "fort lauderdale", "hollywood", "hialeah", "coral gables", "miami beach", "homestead", "boca raton", "pompano beach", "deerfield beach", "boynton beach", "delray beach", "west palm beach"]),
    ("orlando", "Orlando", "FL", ["orlando", "kissimmee", "sanford", "altamonte springs", "winter park"]),
    ("tampa-bay", "Tampa Bay", "FL", ["tampa", "st. petersburg", "clearwater", "brandon", "lakeland"]),
    ("jacksonville", "Jacksonville", "FL", ["jacksonville", "st. augustine", "orange park"]),

    # Georgia
    ("atlanta", "Atlanta", "GA", ["atlanta", "marietta", "decatur", "sandy springs", "roswell", "alpharetta", "duluth", "lawrenceville", "kennesaw"]),

    # Massachusetts
    ("boston", "Greater Boston", "MA", ["boston", "cambridge", "brookline", "somerville", "quincy", "brockton", "newton", "waltham", "medford", "malden", "revere", "chelsea", "framingham", "worcester", "leominster", "southbridge", "clinton", "webster"]),

    # Pennsylvania
    ("philadelphia", "Philadelphia", "PA", ["philadelphia", "chester", "norristown", "king of prussia", "bensalem", "upper darby"]),
    ("pittsburgh", "Pittsburgh", "PA", ["pittsburgh", "mckeesport", "bethel park", "cranberry township"]),

    # Ohio
    ("columbus", "Columbus", "OH", ["columbus", "dublin", "westerville", "grove city", "gahanna", "reynoldsburg"]),
    ("cleveland", "Cleveland", "OH", ["cleveland", "akron", "parma", "lakewood", "euclid", "mentor", "strongsville"]),
    ("cincinnati", "Cincinnati", "OH", ["cincinnati", "mason", "fairfield", "hamilton", "middletown", "west chester"]),

    # Michigan
    ("detroit", "Detroit", "MI", ["detroit", "dearborn", "livonia", "ann arbor", "troy", "sterling heights", "warren", "southfield", "royal oak", "farmington"]),

    # Tennessee
    ("nashville", "Nashville", "TN", ["nashville", "murfreesboro", "franklin", "clarksville", "hendersonville", "gallatin", "lebanon", "smyrna", "brentwood", "tullahoma"]),
    ("memphis", "Memphis", "TN", ["memphis", "germantown", "bartlett", "collierville"]),

    # North Carolina
    ("charlotte", "Charlotte", "NC", ["charlotte", "concord", "gastonia", "huntersville", "matthews", "mooresville", "cornelius"]),
    ("raleigh-durham", "Raleigh-Durham", "NC", ["raleigh", "durham", "chapel hill", "cary", "apex", "wake forest"]),

    # Virginia
    ("dc-metro", "Washington DC Metro", "VA", ["arlington", "alexandria", "fairfax", "reston", "tysons", "mclean", "vienna", "manassas", "falls church", "sterling", "leesburg", "ashburn"]),
    ("dc-metro-dc", "Washington DC Metro", "DC", ["washington"]),
    ("dc-metro-md", "Washington DC Metro", "MD", ["bethesda", "silver spring", "rockville", "gaithersburg", "columbia", "baltimore", "germantown", "bowie", "laurel", "college park"]),

    # Colorado
    ("denver", "Denver", "CO", ["denver", "aurora", "lakewood", "arvada", "westminster", "thornton", "centennial", "boulder", "broomfield", "littleton", "englewood", "golden"]),

    # Washington
    ("seattle", "Seattle", "WA", ["seattle", "bellevue", "tacoma", "redmond", "kirkland", "renton", "kent", "everett", "federal way", "auburn", "olympia"]),

    # Arizona
    ("phoenix", "Phoenix", "AZ", ["phoenix", "scottsdale", "mesa", "chandler", "tempe", "glendale", "gilbert", "peoria", "surprise"]),

    # Indiana
    ("indianapolis", "Indianapolis", "IN", ["indianapolis", "carmel", "fishers", "greenwood", "noblesville", "lawrence"]),

    # Missouri
    ("kansas-city", "Kansas City", "MO", ["kansas city", "independence", "lee's summit", "overland park", "olathe", "shawnee"]),
    ("st-louis", "St. Louis", "MO", ["st. louis", "saint louis", "florissant", "chesterfield", "maryland heights", "kirkwood", "creve coeur"]),

    # Nevada
    ("las-vegas", "Las Vegas", "NV", ["las vegas", "henderson", "north las vegas", "reno", "sparks"]),

    # Oregon
    ("portland", "Portland", "OR", ["portland", "beaverton", "hillsboro", "gresham", "lake oswego", "tigard"]),

    # Wisconsin
    ("milwaukee", "Milwaukee", "WI", ["milwaukee", "waukesha", "brookfield", "racine", "kenosha", "west allis"]),
    ("madison", "Madison", "WI", ["madison", "sun prairie", "fitchburg", "middleton"]),

    # Utah
    ("salt-lake-city", "Salt Lake City", "UT", ["salt lake city", "west valley city", "provo", "orem", "sandy", "ogden", "layton", "murray", "draper", "lehi"]),

    # Minnesota
    ("minneapolis", "Minneapolis-St. Paul", "MN", ["minneapolis", "st. paul", "saint paul", "bloomington", "brooklyn park", "plymouth", "maple grove", "eden prairie", "woodbury", "eagan"]),

    # Louisiana
    ("new-orleans", "New Orleans", "LA", ["new orleans", "metairie", "kenner", "harvey", "marrero"]),

    # Iowa
    ("iowa-city", "Iowa City", "IA", ["iowa city", "cedar rapids", "coralville", "north liberty"]),

    # Nebraska
    ("omaha", "Omaha", "NE", ["omaha", "lincoln", "bellevue", "papillion", "la vista"]),

    # Kansas
    ("wichita", "Wichita", "KS", ["wichita", "derby", "andover"]),

    # West Virginia
    ("morgantown", "Morgantown", "WV", ["morgantown", "fairmont", "clarksburg", "martinsburg"]),

    # New Jersey
    ("northern-nj", "Northern New Jersey", "NJ", ["morristown", "hackensack", "paramus", "wayne", "livingston", "summit", "montclair", "ridgewood", "edison", "new brunswick", "princeton", "woodbridge", "bridgewater"]),
]

# Build lookup: (lowercase_city, state) -> metro_slug
_METRO_LOOKUP: dict[tuple[str, str], str] = {}
_METRO_NAMES: dict[str, str] = {}
_METRO_STATES: dict[str, str] = {}

for slug, display, state, cities in METROS:
    _METRO_NAMES[slug] = display
    _METRO_STATES[slug] = state
    for city in cities:
        _METRO_LOOKUP[(city.lower(), state)] = slug


def get_metro(city: str | None, state: str | None) -> str | None:
    """Return metro slug for a city+state, or None."""
    if not city or not state:
        return None
    city_lower = city.lower().strip()
    return _METRO_LOOKUP.get((city_lower, state))


def get_metro_name(slug: str) -> str:
    return _METRO_NAMES.get(slug, slug)


def get_metro_state(slug: str) -> str:
    return _METRO_STATES.get(slug, "")
