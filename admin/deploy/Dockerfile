FROM python:3.12-slim

WORKDIR /app
COPY challenge/common.py challenge/instance.json /app/
COPY deploy/server.py /app/server.py

ENV PYTHONUNBUFFERED=1
ENV CHALLENGE_DIR=/app
EXPOSE 5007
CMD ["python3", "server.py"]
