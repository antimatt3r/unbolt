# Run the container with:
# docker run -d -p 8000:8000 -v /path/to/local/data:/data unbolt

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libqpdf-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app /app/app

# Ensure the /data directory exists and has default files if none are mounted
RUN mkdir -p /data && \
    touch /data/primary_passwords.txt && \
    touch /data/user_passwords.txt

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
