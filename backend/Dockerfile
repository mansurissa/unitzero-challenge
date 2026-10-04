FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dev requirements are included so the same image can run the test suite (`docker compose run --rm api pytest`).
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY . .

RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000
CMD ["./start.sh"]
