FROM python:3.8

WORKDIR /app
RUN pip install poetry

COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false
RUN poetry install --no-dev

COPY . .
RUN mkdir logs
CMD ["python", "docker-launcher.py"]
