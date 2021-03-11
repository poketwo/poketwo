FROM python:3.8

WORKDIR /app
COPY pyproject.toml poetry.lock ./

RUN pip install poetry
RUN poetry config virtualenvs.create false
RUN poetry install --no-dev

COPY . .
RUN mkdir logs
CMD ["python", "docker-launcher.py"]
