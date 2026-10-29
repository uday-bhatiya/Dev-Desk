set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py ensure_admin

if [ "$DJANGO_DEMO_MODE" = "True" ]; then
  python manage.py seed_demo
  python manage.py seed_bulk
fi