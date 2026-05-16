FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir redis

COPY src /app/src
COPY src/bot-container/bot_redis.py /app/
COPY src/bot-container/bot_worker.py /app/

CMD ["python", "bot_worker.py"]