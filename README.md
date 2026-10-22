# FreshMart

Backend API for a small supermarket's tills and back office (Django + DRF + PostgreSQL).

## Quick start (Day 1)

    cp .env.example .env        # then edit SECRET_KEY and POSTGRES_PASSWORD
    docker compose up -d --build
    docker compose exec web python manage.py migrate
    docker compose exec web python manage.py seed_demo

Admin: http://localhost:8000/admin/

The app refuses to start if `SECRET_KEY` is missing from `.env`.