FROM python:3.11-slim

# Git is needed at runtime so the bot can clone/pull the workspace repo
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for layer caching
COPY bot/requirements.txt /app/bot/requirements.txt
RUN pip install --no-cache-dir -r /app/bot/requirements.txt

# Copy bot source (workspace itself is cloned at runtime from GitHub)
COPY bot/ /app/bot/

# Workspace will be cloned to /tmp/workspace at runtime
ENV WORKSPACE_DIR=/tmp/workspace

# Quieter Python output
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-m", "bot.main"]
