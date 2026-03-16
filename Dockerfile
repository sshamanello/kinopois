FROM python:3.11-slim

WORKDIR /app

# System deps for Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev libpng-dev libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source and install package
COPY pyproject.toml .
COPY kinopois/ kinopois/
RUN pip install --no-cache-dir -e .

# Runtime directories (overridden by volume mounts in production)
RUN mkdir -p data/posters data/collages data/cache credentials

ENTRYPOINT ["kinopois"]
CMD ["--help"]
