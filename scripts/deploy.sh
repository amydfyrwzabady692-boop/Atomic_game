#!/usr/bin/env bash
# به‌روزرسانی امن روی سرور (Docker Compose):
#   ۱. پشتیبان دیتابیس در پوشه‌ی backups/   ۲. گرفتن آخرین کد شاخه   ۳. ساخت و اجرای دوباره   ۴. بررسی سلامت
# استفاده:  ./scripts/deploy.sh            (همان شاخه‌ی فعلی)
#           ./scripts/deploy.sh main       (یا هر شاخه‌ی دیگر)
# هیچ volume یا داده‌ای پاک نمی‌شود؛ اگر هر مرحله خطا بدهد اسکریپت همان‌جا می‌ایستد.
set -euo pipefail

cd "$(dirname "$0")/.."
BRANCH="${1:-$(git rev-parse --abbrev-ref HEAD)}"

if [ ! -f .env ]; then
  echo "فایل .env پیدا نشد؛ اول از روی .env.example بسازید و پر کنید." >&2
  exit 1
fi

mkdir -p backups
STAMP="$(date +%Y%m%d-%H%M%S)"
if docker compose ps --status running --services 2>/dev/null | grep -qx db; then
  echo "» پشتیبان دیتابیس: backups/db-$STAMP.sql.gz"
  docker compose exec -T db pg_dump -U gamebot -d gamebot | gzip > "backups/db-$STAMP.sql.gz"
else
  echo "» سرویس db در حال اجرا نیست؛ پشتیبان گرفته نشد (اولین نصب؟)"
fi

echo "» گرفتن کد شاخه‌ی $BRANCH"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo "» ساخت و اجرای دوباره‌ی سرویس‌ها (migrate خودکار در سرویس web اجرا می‌شود)"
docker compose up -d --build

echo "» منتظر سالم شدن سرویس web"
for _ in $(seq 1 90); do
  if docker compose exec -T web python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" >/dev/null 2>&1; then
    echo "  web سالم است ✓"
    break
  fi
  sleep 2
done

docker compose ps
echo "» آخرین لاگ ربات:"
docker compose logs --tail=40 bot
