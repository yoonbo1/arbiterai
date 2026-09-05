"""Custom Presidio recognizers for clinical documents.

Each module is self-contained: presidio-analyzer is its only dependency and nothing here
imports ``worker.*``, so a module can be lifted into Presidio's ``predefined_recognizers``
or into another project unchanged (the proposed upstream changes are described in
``platform/docs/UPSTREAM.md``). ``worker/deid.py`` registers the recognizers through
:func:`custom_recognizers` and applies the two result filters (``date_filter``,
``person_trim``) to the analyzer's output.

Modules
    mrn             labelled medical record numbers (entity MRN)
    phone           NANP phone numbers with country code and extension (PHONE_NUMBER)
    clinician_name  title- and label-anchored clinician / patient names (PERSON)
    address         labelled address lines, USPS street lines, City ST ZIP, ZIP (LOCATION)
    date_filter     keeps calendar dates, drops dosing frequencies and durations (DATE_TIME)
    person_trim     strips titles and field labels off PERSON spans
"""
from presidio_analyzer import EntityRecognizer

from .address import address_recognizer
from .clinician_name import clinician_name_recognizer
from .mrn import mrn_recognizer
from .phone import phone_recognizer

__all__ = ["custom_recognizers", "mrn_recognizer", "phone_recognizer",
           "clinician_name_recognizer", "address_recognizer"]


def custom_recognizers() -> list[EntityRecognizer]:
    """Fresh recognizer instances in registration order: MRN, phone, clinician name, address.

    The order is the one ``deid.py`` has always used. It only matters on an exact score tie
    between overlapping spans, where the Scrubber's overlap resolution keeps the first
    candidate seen; keeping the order keeps that tie-break stable."""
    return [mrn_recognizer(), phone_recognizer(), clinician_name_recognizer(), address_recognizer()]
