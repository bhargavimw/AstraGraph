FROM python:3.11-slim

WORKDIR /app

# System dependencies (Pillow needs libjpeg, zlib, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo zlib1g libfreetype6 liblcms2 libtiff5 libwebp7 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Application code and data
COPY src/ ./src/
COPY api/ ./api/
COPY data/ ./data/
COPY config.yaml ./config.yaml
COPY outputs/ ./outputs/

# DE421 ephemeris is downloaded by Skyfield at runtime via skyfield-data.
# It is NOT bundled here to keep the image small; it will be cached on first use.

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
