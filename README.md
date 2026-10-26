# FreshMart

Backend API for a small supermarket's tills and back office (Django + DRF + PostgreSQL).

## Quick start (Day 1)

    cp .env.example .env        # then edit SECRET_KEY and POSTGRES_PASSWORD
    docker compose up -d --build
    docker compose exec web python manage.py migrate
    docker compose exec web python manage.py seed_demo

Admin: http://localhost:8000/admin/

The app refuses to start if `SECRET_KEY` is missing from `.env`.


## Day 3: Sales and checkout

### What this adds
- Sales: open a sale, add/change/remove items (by product id or barcode), receipt, list
  (cashier sees own sales, manager sees all, filter by date/cashier/status).
- `pay_sale()` in one `transaction.atomic()`: lock the sale row, lock product rows
  **in id order**, check every line, call `change_stock` for each line, compute the
  total from the lines, check cash, mark paid.
- `cancel_sale()` (no stock change) and `refund_sale()` (stock comes back through
  `refund` movements, manager only).
- Invalid state changes return **409 Conflict**. Short stock returns **400** naming
  every short product.
- The client never sends a price or a total; the server computes everything in `Decimal`.

### Sale status flow
Open -> Paid -> Refunded, and Open -> Cancelled. Only paying or refunding moves stock.

### Tests (PostgreSQL, inside docker compose)
`docker compose exec web python manage.py test sales -v 2`  ->  `Ran 8 tests ... OK`

1. Three-line sale, third line short: 400, all three products keep their old stock,
   no StockMovement written, sale still open.
2. Cash too low after stock was taken: `PaymentError`, everything rolled back.
3. Two tills, one carton left (two threads, `TransactionTestCase`): exactly one pays,
   the other gets a clean "short".
4. Refund puts stock back via refund movements; stock equals the sum of movements;
   refunding twice returns 409.

### Run 1: with `select_for_update()` (normal)
`Ran 8 tests in ...s  OK`

### Run 2: `select_for_update()` removed from `pay_sale` (+ a 0.3s sleep to widen the race window)
```
FAIL: test_exactly_one_till_gets_the_last_carton
AssertionError: Element counts were not equal:
First has 1, Second has 0:  'error: InsufficientStock("Not enough stock for 'Milk': 0 available, 1 requested.")'
First has 0, Second has 1:  'short'
```
Both tills passed the stock check on stale data. The loser failed deep inside
`change_stock` instead of getting the clean 400.
Stock never went negative, because `change_stock` updates with `WHERE stock >= n` and the
database has a `CHECK (stock_quantity >= 0)`. The lock is one of three layers.
The change was reverted afterwards (`git checkout -- sales/services.py`).

### What really oversells: the naive version
`NaiveOversellDemo` (not production code) reads the stock, checks it, then writes
`stock - 1` from Python. Both threads read 1, both write 0: two cartons sold, one existed.
`select_for_update` plus `F()` is what prevents this.

### Review questions
- Why lock product rows in id order? Two sales with the same two products added in opposite
  orders would each hold one lock and wait for the other (deadlock). One global order
  makes a cycle impossible.
- Why would the concurrency test prove little on SQLite? SQLite lets one writer at a time
  for the whole file and ignores `select_for_update`, so the race never really happens.
- Why 409 and not 400 for "pay a cancelled sale"? The request is valid; the sale's current
  state does not allow it.