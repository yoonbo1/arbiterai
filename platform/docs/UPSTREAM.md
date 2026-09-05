# Proposed upstream changes to microsoft/presidio

Four pull requests distilled from the de-identification work in this repo (TODO item 12).
**None has been opened and nothing has been forked**; this document is the plan, with the
source, target, tests and adaptation work for each so opening them is mechanical.

The source modules live under `platform/worker/recognizers/`. Each is self-contained
(presidio-analyzer is its only dependency, no `worker.*` imports; enforced by
`tests/test_recognizers.py::test_modules_depend_only_on_presidio`) so it can be copied into
Presidio's tree unchanged and then adapted in place. Written against presidio-analyzer
2.2.364, whose layout is:

```
presidio-analyzer/presidio_analyzer/
  predefined_recognizers/
    generic/                  date_recognizer.py, phone_recognizer.py, email_recognizer.py, ...
    country_specific/us/      us_ssn_recognizer.py, medical_license_recognizer.py, us_npi_recognizer.py, ...
    nlp_engine_recognizers/   spacy_recognizer.py, stanza_recognizer.py, transformers_recognizer.py
  conf/default_recognizers.yaml   registry: one entry per recognizer (name, supported_languages, type, country_code)
presidio-analyzer/tests/      test_<recognizer>.py, parametrised over (text, expected spans, scores)
```

Process for each PR (the same four steps): fork `microsoft/presidio`, branch, copy the module
to the target path and adapt it as listed, add the test file, run
`pytest presidio-analyzer/tests`, sign the CLA on the PR. Contributor guide:
https://github.com/microsoft/presidio/blob/main/CONTRIBUTING.md. Recognizer conventions:
https://microsoft.github.io/presidio/analyzer/adding_recognizers/.

## The numbers behind them (synthetic corpus, 20 discharge summaries, `eval/run_eval.py`)

| metric | before | after | driver |
|---|---|---|---|
| de-id recall, whole injected string | 0.967 (116/120) | 1.000 | PR 3 (all four survivors were `Dr. <surname>`) |
| de-id recall, strict per component | ~0.81 (by hand) | 1.000 | address recognizer (not one of the four; see the end) |
| answer accuracy, strict | 0.575 (23/40) | 0.95 (38/40) | PR 4 (11 of 12 medication-list misses were `daily`/`nightly` redacted as dates) plus a judge fix |
| MRNs scrubbed | 0 of 20 (scored 0.4 vs 0.5 threshold) | 20 of 20 | PR 1 |
| OCR corpus de-id recall | 0.992 (`MRN:` read as `MAN:`) | 1.000 expected | PR 1, OCR-tolerant label (added 2026-09-05; the OCR eval has not been re-run yet) |
| phone numbers with extensions | missed by `PhoneRecognizer` | caught | PR 2 |

Details and dates: `CHANGELOG.md`, 2026-09-03 "Eval harness" sections and 2026-09-04
"clinical NLP on ingestion".

---

## PR 1: labelled medical record number recognizer

**Title.** Add `UsMrnRecognizer`: medical record numbers anchored on their field label, tolerant of one OCR error

**Description.** Presidio has no recognizer for medical record numbers, the identifier that
appears on every page of a clinical chart. A bare 6-10 digit pattern cannot work on its own:
the same shape is a phone fragment, an account number or a lab value, and any score high
enough to catch MRNs redacts those too (this project's first attempt scored the bare run 0.4
against a 0.5 threshold and scrubbed zero of twenty MRNs). Charts, however, always label the
field, so the recognizer anchors on the label and puts it in a lookbehind: only the digits
are matched, and an anonymizer that replaces the span leaves `MRN: <MRN>` readable. With the
label anchored, every one of the twenty synthetic charts was scrubbed; the one survivor on
the scanned corpus (recall 0.992) was a page where Tesseract had read `MRN:` as `MAN:`.

The recognizer therefore matches three tiers: the exact label (`MRN`, with `:`, `#` or a
space) at 0.85; any edit-distance-1 variant of the label (one letter substituted or
deleted: `MAN`, `MRM`, `RN`) or spacing variant (`M R N`) at 0.7, generated from the label
list so the alternation never has to be hand-maintained; and, as a fallback for a label
mangled beyond one edit, a bare 6-10 digit run on a line that also carries a demographics
cue (`DOB`, `Patient`, `Name`, `Sex`, `Age`) at 0.5. A bare run anywhere scores 0.3 and only
clears the threshold through the context enhancer (`mrn`, `medical record`, `record
number`, `chart number`). The fallback cannot fire on formatted dates, phone numbers, ZIP
codes or five-digit lab values because none contains six consecutive digits.

**Source.** `platform/worker/recognizers/mrn.py` (`MrnRecognizer(PatternRecognizer)`,
`label_variants()`).

**Target.** `presidio-analyzer/presidio_analyzer/predefined_recognizers/country_specific/us/us_mrn_recognizer.py`,
next to `medical_license_recognizer.py`, `us_npi_recognizer.py` and `us_mbi_recognizer.py`;
export from `country_specific/us/__init__.py` and `predefined_recognizers/__init__.py`. Entity
name is the maintainers' call: `US_MRN` follows `US_SSN`; `MEDICAL_RECORD_NUMBER` is more
honest since MRNs are not US-specific (only the English label is).

**Tests.** `presidio-analyzer/tests/test_us_mrn_recognizer.py`, parametrised like
`test_us_ssn_recognizer.py`:
- the six labelled forms `MRN: 1234567`, `MRN:1234567`, `MRN 1234567`, `MRN# 1234567`,
  `MRN#1234567`, `MRN: 1234567890` each give one span over the digits only, score 0.85;
- `MAN: 1234567`, `MRM 1234567`, `M R N: 1234567` give the same span at 0.7;
- `Patient: John Doe   1234567   DOB 01/02/1960` gives `1234567` at 0.5; the cue must be on
  the same line (`Patient: John Doe\nAccount 1234567` gives only the 0.3 bare hit);
- no result at all for `Patient: John Doe   DOB 03/05/2024`, `... Phone 555-0100`,
  `... Kingland, TX 75001`, `... WBC 11000`, `... HbA1c 9.0`;
- `label_variants("MRN")` has 75 substitutions, 3 deletions, 3 spacings, no insertions and
  not the label itself;
- with the analyzer engine: `medical record 1234567` clears the threshold through context.

**Still to adapt.** Registry entry in `conf/default_recognizers.yaml` (`type: predefined`,
`country_code: us`, `supported_languages: [en]`). `supported_language` and a per-language
label list (`MRN` is English; German charts use `Fallnummer`/`Patienten-ID`). Context words
merged with Presidio's conventions (lower-case, lemmatised by the enhancer). The
demographics-line fallback is opinionated about US chart layout: propose it as a constructor
flag off by default (`demographics_line_fallback=False`) so the default recognizer is a pure
`PatternRecognizer`. Presidio compiles patterns with the `regex` module, which supports
variable-width lookbehind, so the width-grouped alternation could be collapsed to one
lookbehind per separator. Documentation row in `docs/supported_entities.md`. Score levels
(0.85 / 0.7 / 0.5 / 0.3) are this project's; maintainers may want the labelled tier at the
`PatternRecognizer` norm of 0.5 plus context.

---

## PR 2: NANP phone numbers with extensions

**Title.** Catch NANP phone numbers with extensions and unformatted ten-digit numbers that `PhoneRecognizer` misses

**Description.** `PhoneRecognizer` wraps `phonenumbers.PhoneNumberMatcher` at leniency 1
(VALID) for eight regions. On the first end-to-end run of this project it left
`+1-921-899-3518x19093` and `(555) 201-8842 ext. 12` in the index, both ordinary contact-line
formats in US charts, and a bare ten-digit number after `Tel:` was only removed because the
NER model had mislabelled it as a date (the moment a date filter was added, it would have
survived). The fix here is a regex backstop that runs alongside `PhoneRecognizer`: a
formatted NANP pattern with optional `+1`/`1` prefix, parenthesised or dashed area code,
`-`/`.`/space separators and an optional `x`/`ext.`/`extension` suffix of 1-6 digits at 0.6;
and an unformatted ten-digit run of valid NANP shape (`[2-9]\d{2}[2-9]\d{6}`) at 0.35, which
only clears the threshold through the context enhancer (`phone`, `tel`, `telephone`, `cell`,
`mobile`, `fax`, `call`). Overlaps with `PhoneRecognizer`'s own hits resolve in the engine's
deduplication (higher score, then longer span), so the two do not fight.

The PR needs one piece of diagnosis first: whether the extension forms fail in
`phonenumbers` itself (the `555-01xx` exchange is a reserved fictional range that VALID
leniency may reject, and `x19093` is a five-digit extension), or in `PhoneRecognizer`'s use
of it (leniency, `supported_regions`, or its 0.4 score against a 0.5 default threshold with
`number`/`phone` not always within the context window). Depending on the answer the PR is
either a leniency/score change to `PhoneRecognizer` plus the regex fallback, or the regex
recognizer alone. Either way the five test forms below are the acceptance criterion.

**Source.** `platform/worker/recognizers/phone.py` (`phone_recognizer()`, name
`phone_regex`).

**Target.** Either a regex fallback pass inside
`predefined_recognizers/generic/phone_recognizer.py` gated on `"US"` or `"CA"` being in
`supported_regions`, or a new `predefined_recognizers/country_specific/us/us_phone_recognizer.py`
(`PatternRecognizer`, entity `PHONE_NUMBER`). The second keeps `PhoneRecognizer`'s library
semantics untouched and is the easier review.

**Tests.** `presidio-analyzer/tests/test_us_phone_recognizer.py` (or additions to
`test_phone_recognizer.py`):
- `+1-921-899-3518x19093`, `(555) 201-8842 ext. 12`, `555.201.8842`,
  `921-899-3518 extension 7`, `+1 921 899 3518` are each one span that includes the
  extension, score 0.6;
- `Tel: 9218993518` gives `9218993518` at 0.35 alone and above 0.5 with the analyzer engine
  (context lift); `WBC 11000` and `MRN 1234567` give nothing;
- `Call 555-201-8842 ext. 12 or MRN: 5552018842` with both this and `PhoneRecognizer`
  registered yields one PHONE_NUMBER span per number after deduplication.

**Still to adapt.** Registry entry (`country_code: us`). Context words merged with
`PhoneRecognizer.CONTEXT` (`phone`, `number`, `telephone`, `cell`, `cellphone`, `mobile`,
`call`; this adds `tel` and `fax`). Region gating so the pattern does not run for texts
analysed with non-NANP regions. Score conventions (`PhoneRecognizer.SCORE` is 0.4; a 0.6
regex above it changes which recognizer wins on overlap, and maintainers may prefer 0.4 plus
context). Language: the extension words are English.

---

## PR 3: title-anchored clinician and patient names

**Title.** Add `TitleAnchoredNameRecognizer`: PERSON spans after honorifics and chart field labels

**Description.** NER models miss `Dr. <common-word surname>` at a rate that matters for
de-identification: on this project's first eval run, all four PHI strings that survived
were `Dr. Fields`, `Dr. Lewis`, `Dr. Young` and `Dr. Holder`, and they alone put whole-string
recall at 0.967 against a 0.99 gate. Clinical text is unusually rich in anchors that need no
model: honorifics (`Dr.`, `Doctor`, `MD`) and field labels (`Attending:`, `Physician:`,
`Provider:`, `Patient:`, `Patient Name:`, `Name:`). The recognizer is a `PatternRecognizer`
with one fixed-width lookbehind per anchor and a name pattern of one to three capitalised
words (apostrophes and hyphens allowed), scoring 0.7. The anchor stays out of the span, so an
anonymizer yields `Attending: Dr. <PERSON>` and the reader still knows who the token is.
With it, whole-string recall went to 1.000 on the same corpus.

Two details matter for review. Presidio compiles every pattern with IGNORECASE, which makes a
capitalised-word pattern swallow the following lowercase word (`Priya Raghunathan-Okafor
reviewed`); a scoped `(?-i:...)` group, which the `regex` module supports, makes the name part
case-sensitive so the span stops at the first lowercase word. And when the NER model does
tag the name, the engine's deduplication keeps the higher-scoring NER span (0.85 over 0.7),
so this recognizer only ever adds hits the model missed. A companion problem it does not
solve is the model tagging a bare `Dr` as a PERSON; this project trims titles and trailing
field labels off PERSON spans in a post-filter (`person_trim.py`), which could be a follow-up
PR on `SpacyRecognizer`.

**Source.** `platform/worker/recognizers/clinician_name.py` (`clinician_name_recognizer()`,
name `title_name_regex`, anchors in `ANCHORS`); companion `person_trim.py`.

**Target.** `presidio-analyzer/presidio_analyzer/predefined_recognizers/generic/title_name_recognizer.py`
(the anchors are language-specific, not country-specific), `supported_language="en"`,
anchors as a constructor argument so other languages can supply their own.

**Tests.** `presidio-analyzer/tests/test_title_name_recognizer.py`:
- `Dr. Priya Raghunathan-Okafor reviewed the chart.` gives exactly `Priya
  Raghunathan-Okafor` at 0.7 (the lowercase `reviewed` is excluded);
- `Attending: Dr. Young    Date of service: 2026-04-02` gives `Dr` (after `Attending: `) and
  `Young` (after `Dr. `); the test documents that the bare-title hit is expected and is the
  post-filter's job;
- `the doctor said` gives nothing (lowercase name part);
- with the analyzer engine and spaCy: `Attending: Priya Raghunathan-Okafor.` is a PERSON span
  even when the NER model misses it, and `Patient: John Smith.` yields one span, not two.

**Still to adapt.** Registry entry. Language handling: an anchor table per language (`Dr`,
`Herr Dr.`, `Dott.`), and the capitalisation rule does not hold for scripts without case.
Context words: none today; `attending`, `physician`, `md` would let a 0.7 hit be lifted when
the anchor is on the previous line. Interaction with `SpacyRecognizer` on partial overlaps
(`Dr. Young` tagged as a whole by NER and `Young` by this recognizer): Presidio keeps both
unless one contains the other with a higher score, and the anonymizer then handles the
overlap; document it. The `(?-i:...)` construct should be noted in the docstring since
readers assume `re`.

---

## PR 4: dosing-frequency date filter

**Title.** `SpacyRecognizer`: option to keep only calendar-like DATE_TIME spans

**Description.** spaCy's DATE label covers frequencies and durations as well as dates:
`daily`, `nightly`, `tonight`, `in 2 weeks`, `48 hours`. For de-identification that is the
wrong boundary. Safe Harbor dates are dates tied to a person (birth, admission, discharge,
death); a dosing frequency identifies no one, and redacting it destroys the clinical meaning
of the text. On this project's first eval run, `sertraline 50 mg <DATE_TIME_2>` in the index
caused 11 of the 12 medication-list misses and held answer accuracy at 0.575; with the filter
(and an unrelated judge fix) accuracy went to 0.95, and the only remaining misses were OCR
misreads. The filter keeps a DATE_TIME span only if it contains something calendar-like: a
month name or abbreviation, a numeric date (`3/5/2024`, `03-05-24`), an ISO date, a four-digit
year 1900-2099, or an ordinal day (`5th`). Fourteen unit cases pin the boundary
(`1985-03-12`, `March 9, 2024`, `Sept. 5`, `the 5th`, `2024` kept; `daily`, `nightly`,
`2 weeks`, `48 hours`, `2 weeks later`, `tonight` dropped).

Presidio has no hook for narrowing an NER recognizer's output, so this project applies the
filter after `AnalyzerEngine.analyze`. Upstream the natural home is a constructor option on
`SpacyRecognizer`, which `StanzaRecognizer` and `TransformersRecognizer` inherit, e.g.
`calendar_dates_only: bool = False`, applied in `analyze()` to spans mapped to DATE_TIME;
the regex-based `DateRecognizer` already matches only numeric dates and needs no change.
An alternative with wider reach is a generic post-filter hook on `AnalyzerEngine` (a list of
`Callable[[RecognizerResult, str], bool]`), which would also host the title/label trim from
PR 3's companion; the recognizer option is the smaller review.

**Source.** `platform/worker/recognizers/date_filter.py` (`DATE_LIKE`,
`is_identifying_date()`).

**Target.** `presidio-analyzer/presidio_analyzer/predefined_recognizers/nlp_engine_recognizers/spacy_recognizer.py`
(option and filter), with the regex as a module-level constant that subclasses can override.

**Tests.** Additions to `presidio-analyzer/tests/test_spacy_recognizer.py`:
- the fourteen `is_identifying_date` cases above;
- with the option on, `Medications: sertraline 50 mg daily; atorvastatin 40 mg nightly.
  Follow up in 2 weeks.` yields no DATE_TIME result and `DOB: 1985-03-12. Admitted 03/05/2024
  and discharged March 9, 2024.` yields three;
- with the option off (default), behaviour is unchanged (the existing tests pass).

**Still to adapt.** Language handling: month names are English; either a per-language table
or a `calendar_regex` constructor parameter with the English default. The year rule
(`19xx`/`20xx`) and ordinal suffixes are English-centric too. Where the option is surfaced:
`SpacyRecognizer.__init__`, or `ner_model_configuration` in `conf/*.yaml` alongside
`labels_to_ignore`, which is where NER-shaping options already live. Documentation of the
Safe Harbor rationale so the option is not mistaken for a precision tweak. Context: none
needed.

---

## Not proposed (yet)

- **US street-address recognizer** (`address.py`: labelled `Address:` lines, USPS-suffix
  street lines, `City, ST ZIP`, context-lifted ZIP). It moved strict per-component recall from
  about 0.81 to 1.000 and is the largest single win, but it is US-only, heuristic (a 200-word
  suffix list, a 0.35 bare-ZIP score chosen because `WBC 11000` was being scrubbed), and
  depends on the caller merging overlapping spans into their union. Worth a fifth PR once the
  first four have landed and the maintainers' appetite for US-specific heuristics is known.
- **Title and label trim for PERSON spans** (`person_trim.py`): folded into PR 3's
  description as a follow-up; it belongs with the post-filter hook discussed under PR 4.
