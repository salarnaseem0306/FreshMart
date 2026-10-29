# FreshMart

A small supermarket back end: products, stock, sales and manager reports, as a REST API.
Cashiers ring up sales; managers receive stock, refund sales and read reports.
Stock can never go negative, and a payment either fully succeeds or changes nothing.

Built with Python, Django 5.2 LTS, Django REST Framework and PostgreSQL 16 (in Docker).

## What it does
- **Catalog:** categories, suppliers and products (SKU, optional barcode, price, reorder level).
- **Inventory:** stock is received, adjusted and sold only through one function,
  `change_stock()`. Every change is written to a stock-movement log.
- **Sales:** open a sale, add/change/remove items (by product id or barcode), get a receipt.
  Cashiers see their own sales, managers see all (filter by date/cashier/status).
- **Payment:** `pay_sale()` is all-or-nothing. The client never sends a price or total;
  the server computes everything in `Decimal`.
- **Reports (manager only):** daily revenue, top products, low stock.
- **Status flow:** Open -> Paid -> Refunded, and Open -> Cancelled. Only paying or refunding
  moves stock. Invalid changes return 409; short stock returns 400 naming each product.

## 1. Setup (from a fresh clone)

You need Docker Desktop and Git.

```bash
git clone https://github.com/salarnaseem0306/FreshMart.git
cd FreshMart
cp .env.example .env        # Windows PowerShell: copy .env.example .env
```
Open `.env` and set a long random `SECRET_KEY` and a `POSTGRES_PASSWORD`.
The app refuses to start without a `SECRET_KEY`. Never commit `.env`.

```bash
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo
```
Check it is alive: <http://localhost:8000/api/health/> should answer OK.
Admin site: <http://localhost:8000/admin/>.

## 2. Demo users

`seed_demo` creates these (password for all: `freshmart123`). Running it twice is safe.

| Username   | Role    | Can do                                  |
|------------|---------|-----------------------------------------|
| `manager1` | manager | everything, including stock and reports |
| `cashier1` | cashier | sales; read-only catalog                |

## 3. Walkthrough: login to a paid sale with a receipt

The examples use `curl` (macOS/Linux/Git Bash). On Windows PowerShell use `curl.exe`
or `Invoke-RestMethod`.

```bash
# 1. Log in as the cashier; copy the "access" value
curl -s -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"cashier1","password":"freshmart123"}'
TOKEN=<paste access token here>

# 2. Find a product (note its "id")
curl -s "http://localhost:8000/api/products/?search=rice" -H "Authorization: Bearer $TOKEN"

# 3. Open a sale (note its "id")
curl -s -X POST http://localhost:8000/api/sales/ -H "Authorization: Bearer $TOKEN"

# 4. Add 2 units (replace the sale id 1 and product id 1 with yours)
curl -s -X POST http://localhost:8000/api/sales/1/items/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"product":1,"quantity":2}'

# 5. Pay in cash
curl -s -X POST http://localhost:8000/api/sales/1/pay/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"payment_method":"cash","amount_received":"20.00"}'

# 6. The receipt
curl -s http://localhost:8000/api/sales/1/ -H "Authorization: Bearer $TOKEN"
```
Access tokens last 15 minutes; if you get 401, log in again (refresh tokens last 1 day).
Managers (log in as `manager1`) can also receive stock, refund and read reports.

## 4. Run the tests

```bash
docker compose exec web ruff check .
docker compose exec web python manage.py test
```
Tests run against real PostgreSQL. If Django asks to delete `test_freshmart`, answer yes
(it is a temporary database; your real data is in `freshmart`).
CI (GitHub Actions) runs ruff, a missing-migration check, the API schema check and all tests
on every push and pull request.

## 5. API documentation

Log in first, then open <http://localhost:8000/api/docs/> (Swagger UI).
The raw schema is at `/api/schema/`.

---

## 6. Endpoints

| Area | Endpoint | Who |
|------|----------|-----|
| Health | `GET /api/health/` | anyone |
| Auth | `POST /api/auth/login/`, `POST /api/auth/refresh/`, `GET /api/auth/me/` | login open; me needs a token |
| Catalog | `/api/categories/`, `/api/suppliers/`, `/api/products/` (+ `GET /api/products/{id}/`, `GET /api/products/barcode/{code}/`) | staff read, manager write |
| Inventory | `POST /api/inventory/receive/`, `POST /api/inventory/adjust/`, `GET /api/inventory/movements/` | manager |
| Sales | `/api/sales/`, `POST /api/sales/{id}/items/`, `PATCH/DELETE /api/sales/{id}/items/{item_id}/`, `POST .../pay/`, `.../cancel/`, `.../refund/` (manager) | cashier or manager |
| Reports | `GET /api/reports/daily/`, `/top-products/`, `/low-stock/` | manager |

All list endpoints are paginated. Limits: at most 999 units per line and a sale total up to
99,999,999.99, otherwise the API answers 400 with a field error.

## 7. Roles

- **manager:** everything. A superuser created with `createsuperuser` is a manager too.
- **cashier:** can read the catalog and handle sales; cannot receive stock, refund or read reports.
- Not logged in: 401. Logged in but not allowed: 403 (tested for every endpoint group).

## 8. Rules the code protects

1. **Money is `Decimal`**, never float; the API shows it as a string such as `"18.00"`.
2. **Stock never goes negative:** `change_stock()` uses a conditional update, and the
   database also has a `CHECK` constraint.
3. **Stock equals the sum of movements:** every change writes a `StockMovement` in the
   same transaction.
4. **Price is copied onto the sale line** when it is added, so later price changes never
   rewrite old receipts.
5. **Products are never deleted, only marked inactive** (history uses `PROTECT`). Inactive
   products disappear from lists and the scanner, but can still be fetched by id.
6. **Payment is all-or-nothing:** one transaction; either every line and the sale update
   succeed, or nothing changes.

How rules 2 and 6 hold up with two tills at once: [docs/concurrency.md](docs/concurrency.md).

## 9. Project layout

| Folder | Purpose |
|--------|---------|
| `config/` | settings, root URLs |
| `accounts/` | custom `User` with a role (manager/cashier), login and `me` |
| `catalog/` | categories, suppliers, products |
| `inventory/` | `StockMovement`, `change_stock()`, receive/adjust/movements |
| `sales/` | `Sale`, `SaleItem`, services (`add_item`, `pay_sale`, `cancel_sale`, `refund_sale`) |
| `reports/` | report queries and endpoints |
| `core/` | shared permissions, pagination, health, demo seeding |
| `docs/` | extra write-ups |

Views stay thin; business rules live in `services.py` files so they can be tested and reused.

## 10. Dependencies

Exact versions are pinned in `requirements.txt`. Development tools (ruff) live in
`requirements-dev.txt`, which the Dockerfile and CI install.

## 11. More

- Concurrency write-up: [docs/concurrency.md](docs/concurrency.md)