FROM python:3.12-slim

WORKDIR /app

# System dependencies Playwright's Chromium needs to actually run
# headless (not just be installed) -- Railway's default builder doesn't
# include these, so without this step scrapes would fail in production
# even though everything works locally.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Downloads the actual Chromium binary + its remaining OS-level deps in
# one step -- this is the production equivalent of the
# `python -m playwright install chromium` you ran locally.
RUN python -m playwright install --with-deps chromium

COPY . .

# Railway injects $PORT at runtime; must bind 0.0.0.0, not 127.0.0.1,
# or Railway's router can't reach the container.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]