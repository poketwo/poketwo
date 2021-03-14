FROM python:3.8-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libjemalloc2 git && rm -rf /var/lib/apt/lists/*
ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2

RUN pip install poetry
RUN poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-dev

COPY . .
CMD ["python", "docker_launcher.py"]
