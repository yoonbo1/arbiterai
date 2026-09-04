# Two stages: PyRuSH, quicksectx, pysimstring and medspacy_unqlite (pulled in by medspacy) ship no
# linux/aarch64 wheels, so they are compiled once in a builder image with build-essential and the
# runtime image installs everything from the resulting wheel directory, offline.
FROM python:3.12-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt requirements-clinical.txt ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt -r requirements-clinical.txt
# NER models, no deps: med7 is built for spaCy 3.8; bc5cdr's metadata pins spacy<3.8 and would
# otherwise downgrade the pinned spaCy.
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels \
      https://huggingface.co/kormilitzin/en_core_med7_lg/resolve/main/en_core_med7_lg-1.1.0-py3-none-any.whl \
      https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_ner_bc5cdr_md-0.5.4.tar.gz

FROM python:3.12-slim
# tesseract-ocr pulls in the English traineddata (tesseract-ocr-eng).
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-clinical.txt ./
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links /wheels -r requirements.txt -r requirements-clinical.txt \
 && pip install --no-cache-dir --no-index --no-deps --find-links /wheels en_core_med7_lg en_ner_bc5cdr_md
# en_ner_bc5cdr_md 0.5.4 was packaged for spaCy 3.7; spaCy 3.8's config parser rejects the quoted
# booleans in its config.cfg. Patch in place (the model weights are unchanged).
RUN sed -i -e 's/^include_static_vectors = "True"/include_static_vectors = true/' \
           -e 's/^include_static_vectors = "False"/include_static_vectors = false/' \
    "$(python -c 'import en_ner_bc5cdr_md,os;print(os.path.dirname(en_ner_bc5cdr_md.__file__))')/en_ner_bc5cdr_md-0.5.4/config.cfg" \
 && python -c "import spacy; spacy.load('en_ner_bc5cdr_md', exclude=['tagger','attribute_ruler','lemmatizer','parser']); spacy.load('en_core_med7_lg'); print('clinical models ok')"
# Presidio's default configuration expects en_core_web_lg (~560 MB). A dev build can pass
# --build-arg SPACY_MODEL=en_core_web_sm; the worker's SPACY_MODEL env must then match.
ARG SPACY_MODEL=en_core_web_lg
# spacy download runs pip without --no-cache-dir; drop the ~500 MB cache it leaves in this layer.
RUN python -m spacy download ${SPACY_MODEL} && rm -rf /root/.cache/pip
ENV SPACY_MODEL=${SPACY_MODEL}
COPY . ./worker
STOPSIGNAL SIGTERM
CMD ["python", "-m", "worker.main"]
