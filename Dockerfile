FROM python:3.11-slim

WORKDIR /app

# git is needed only to fetch the pinned rp2 dependency at install time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists

COPY pyproject.toml README.md ./
COPY utxoproof/ utxoproof/
RUN pip install --no-cache-dir .

ENTRYPOINT ["utxoproof"]
CMD ["--help"]
