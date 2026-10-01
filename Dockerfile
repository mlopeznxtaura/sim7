FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY simulation_backend.py .
COPY static ./static

ENV PORT=8080
EXPOSE 8080

CMD ["python", "simulation_backend.py"]
