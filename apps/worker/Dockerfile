FROM python:3.12-slim

WORKDIR /app/apps/worker

# Install API dependencies (shared models/services)
COPY apps/api/requirements.txt /tmp/api-requirements.txt
RUN pip install --no-cache-dir -r /tmp/api-requirements.txt

# Copy API source (models, services, config)
COPY apps/api /app/apps/api

# Copy worker entry point
COPY apps/worker/main.py /app/apps/worker/main.py

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
