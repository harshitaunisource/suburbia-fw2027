# Using Playwright's own official image instead of plain python:3.12-slim.
# Why: python:3.12-slim now resolves to Debian 13 ("trixie"), which is
# newer than Playwright 1.47.0 (pinned in requirements.txt) knows about.
# `playwright install --with-deps` doesn't recognize trixie and silently
# falls back to guessing Ubuntu 20.04's package list -- which references
# font packages (ttf-unifont, ttf-ubuntu-font-family) that don't exist in
# trixie's actual repos, so the build fails with "no installation
# candidate". Playwright's own image sidesteps this entirely: it's built
# and tested specifically for this exact Playwright version, with
# Chromium and every OS-level dependency already correctly installed.
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chromium's binary is already present in this base image (that's the
# whole point of using it) -- this just confirms it / fills in anything
# version-specific for this exact Python environment. No --with-deps
# needed here since the OS-level dependencies are already baked in.
RUN python -m playwright install chromium

COPY . .

# Railway injects $PORT at runtime; must bind 0.0.0.0, not 127.0.0.1,
# or Railway's router can't reach the container.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]