FROM python:3.11-slim

WORKDIR /app

# 安装 ipmitool
RUN apt-get update && \
    apt-get install -y --no-install-recommends ipmitool && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/config

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "60", "app:app"]

