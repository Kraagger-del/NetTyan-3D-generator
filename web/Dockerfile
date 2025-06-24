FROM python:3.8-slim

WORKDIR /app
COPY web/ /app

RUN pip install --no-cache-dir flask numpy nbtlib

EXPOSE 5000
CMD ["python", "inference.py"]