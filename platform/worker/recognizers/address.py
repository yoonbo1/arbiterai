"""US street addresses, ``City, ST ZIP`` lines and ZIP codes.

Problem. Presidio has no US street-address recognizer and spaCy tags the city at best. In
the first eval run only the city of each address was tokenized: street lines survived in
7 of 20 documents and ZIP codes in 14 of 20, unnoticed by the whole-string recall metric
(CHANGELOG 2026-09-03; strict per-component recall about 0.81 by hand, 0.9625 after the
labelled and street patterns, 1.000 after the ``City, ST ZIP`` pattern). The six remaining
strict-metric survivors were Faker-invented city names (``Blankenshipstad``,
``Hernandezview``, ``Kingland``, ``New Amber``) that no NER model knows, which is why the
``City, ST ZIP`` pattern needs no knowledge of city names.

Scores. ``address_labelled`` 0.85: everything after ``Address:`` or ``Addr:`` up to three
comma segments (``street, city, ST ZIP``), stopping at a run of two or more spaces, the
next ``Label:`` on the line, or end of line; a ``(?=\\S)`` guard keeps the span from starting
on the separator space. ``street_line`` 0.6: a house number, 1-4 words and a USPS street
suffix, with an optional unit. ``city_state_zip`` 0.6: ``Name, ST 12345[-6789]``. ``us_zip``
0.35: a bare 5-digit run, below the 0.5 threshold on its own because ``WBC 11000`` was being
scrubbed as a ZIP code (CHANGELOG 2026-09-04, 0.6 lowered to 0.35); only the context words
``address``, ``street``, ``zip``, ``apt``, ``suite``, ``resides``, ``lives at`` lift it.

The caller must merge overlapping spans into their union: spaCy tags only ``Kingland`` inside
``Kingland, TX 75001``, and keeping the shorter, higher-scoring city span leaves ``TX 75001``
behind.

Examples (tests/test_recognizers.py). ``Address: 609 Stacey Roads, New Brendaton, IN 06606``
followed by ``Attending: ...`` on the same line gives one LOCATION span over the address;
``Patient resides in Kingland, TX 75001 with family.`` removes the city and ZIP and keeps
``with family``.
"""
from presidio_analyzer import Pattern, PatternRecognizer

NAME = "street_address_regex"
CONTEXT = ["address", "street", "zip", "apt", "suite", "resides", "lives at"]

USPS_SUFFIX = (
    "Alley|Anex|Arcade|Avenue|Ave|Bayou|Beach|Bend|Bluff|Bluffs|Bottom|Boulevard|Blvd|Branch|Bridge|Brook|"
    "Brooks|Burg|Burgs|Bypass|Camp|Canyon|Cape|Causeway|Center|Centers|Circle|Circles|Cliff|Cliffs|Club|"
    "Common|Commons|Corner|Corners|Course|Court|Courts|Ct|Cove|Coves|Creek|Crescent|Crest|Crossing|Crossroad|"
    "Crossroads|Curve|Dale|Dam|Divide|Drive|Drives|Dr|Estate|Estates|Expressway|Extension|Extensions|Fall|"
    "Falls|Ferry|Field|Fields|Flat|Flats|Ford|Fords|Forest|Forge|Forges|Fork|Forks|Fort|Freeway|Garden|"
    "Gardens|Gateway|Glen|Glens|Green|Greens|Grove|Groves|Harbor|Harbors|Haven|Heights|Highway|Hwy|Hill|"
    "Hills|Hollow|Inlet|Island|Islands|Isle|Junction|Junctions|Key|Keys|Knoll|Knolls|Lake|Lakes|Land|"
    "Landing|Lane|Ln|Light|Lights|Loaf|Lock|Locks|Lodge|Loop|Mall|Manor|Manors|Meadow|Meadows|Mews|Mill|"
    "Mills|Mission|Motorway|Mount|Mountain|Mountains|Neck|Orchard|Oval|Overpass|Park|Parks|Parkway|Pkwy|"
    "Parkways|Pass|Passage|Path|Pike|Pine|Pines|Place|Pl|Plain|Plains|Plaza|Point|Points|Port|Ports|"
    "Prairie|Radial|Ramp|Ranch|Rapid|Rapids|Rest|Ridge|Ridges|River|Road|Rd|Roads|Route|Row|Rue|Run|Shoal|"
    "Shoals|Shore|Shores|Skyway|Spring|Springs|Spur|Spurs|Square|Sq|Squares|Station|Stravenue|Stream|"
    "Street|St|Streets|Summit|Terrace|Throughway|Trace|Track|Trafficway|Trail|Trl|Trailer|Tunnel|Turnpike|"
    "Underpass|Union|Unions|Valley|Valleys|Viaduct|View|Views|Village|Villages|Ville|Vista|Walk|Walks|Wall|"
    "Way|Ways|Well|Wells"
)
UNIT = r"(?:,? ?(?:Suite|Ste\.?|Apt\.?|Apartment|Unit|Bldg\.?|Floor|Fl\.?|#) ?[\w-]+)?"


def address_recognizer() -> PatternRecognizer:
    # Labelled: up to "street, city, ST ZIP" (three comma segments) after "Address:", stopping at
    # a run of spaces, the next "Label:" on the same line, or end of line.
    seg = r"(?:[^\n,]{2,60}, ){0,3}[^\n,]{2,40}?(?=\s{2,}|\s+[A-Za-z ]{2,20}:|\n|$)"
    labelled = (rf"(?<=\bAddress: ){seg}|(?<=\bAddress:)(?=\S){seg}"
                rf"|(?<=\bAddr: ){seg}|(?<=\bAddr:)(?=\S){seg}")
    street = rf"\b\d{{1,6}} (?:[A-Za-z][A-Za-z'\-]+ ){{1,4}}(?:{USPS_SUFFIX})\b\.?{UNIT}"
    # "City, ST 12345": spaCy misses invented or rare city names, this does not need to know them.
    city_state_zip = r"\b[A-Za-z][A-Za-z.'\- ]{1,40}, [A-Za-z]{2} \d{5}(?:-\d{4})?\b"
    return PatternRecognizer(supported_entity="LOCATION", name=NAME,
                             patterns=[Pattern("address_labelled", labelled, 0.85),
                                       Pattern("street_line", street, 0.6),
                                       Pattern("city_state_zip", city_state_zip, 0.6),
                                       # A bare 5-digit run is a lab value at least as often as a ZIP
                                       # (WBC 11000, a platelet count); 0.35 alone is below the 0.5 threshold
                                       # and only the address context words above lift it.
                                       Pattern("us_zip", r"\b\d{5}(?:-\d{4})?\b", 0.35)],
                             context=CONTEXT)
