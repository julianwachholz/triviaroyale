FROM python:3.7-alpine

WORKDIR /app

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

RUN apk --no-cache add \
    bash \
    build-base \
    linux-headers \
    postgresql-dev

COPY requirements.txt /app/
RUN pip install -r requirements.txt

COPY . /app

CMD python app.py
