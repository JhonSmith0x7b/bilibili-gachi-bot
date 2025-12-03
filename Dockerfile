# FROM python:3.13-slim
FROM python:3.12-bullseye

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY ./app /app/
RUN playwright install-deps
RUN playwright install
RUN chmod -R 777 /root
RUN chmod -R 777 /app

EXPOSE 7860
CMD ["python", "main.py"]