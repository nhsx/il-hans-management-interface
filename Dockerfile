FROM python:3.10-slim-bullseye

EXPOSE 8000

ENV PIP_DISABLE_PIP_VERSION_CHECK 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN pip install --no-cache-dir --upgrade pip
RUN pip install gunicorn==20.1.0

COPY requirements.txt /
RUN pip install --no-cache-dir -r /requirements.txt

WORKDIR /app
COPY management_interface /app/
