FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./

# Dev image: includes pytest + alembic so tests, migrations and the eval harness run in the container.
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]