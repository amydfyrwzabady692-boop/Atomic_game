FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# فونت فارسی Vazirmatn برای تصویر «مسابقه‌ی تایپ» (با DejaVu به‌عنوان جایگزین)
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-vazirmatn fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN SECRET_KEY=build python manage.py collectstatic --noinput

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "8", "--worker-class", "gthread", "--timeout", "30", "--keep-alive", "5"]
