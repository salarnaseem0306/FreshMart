# Concurrency: two tills, one shelf

Two cashiers pay for the last carton of milk at the same moment. Without care both
see "1 in stock" and both succeed. FreshMart prevents this in three layers.

## How `pay_sale()` stays correct

`pay_sale()` runs in one `transaction.atomic()`:

1. Lock the sale row and make sure it is still open.
2. Compute the total from the lines and check the cash (needs no product rows).
3. Lock the product rows **in id order**.
4. Check every line, so the cashier hears about every short product at once.
5. Call `change_stock` for each line, then mark the sale paid.

The three layers:
- **Row locks** (`select_for_update`, in id order): the second till waits, then sees fresh stock.
- **`change_stock()` with a conditional `UPDATE ... WHERE stock_quantity >= n` using `F()`**:
  the database itself refuses to go below zero, even if the lock were missing.
- **`CHECK (stock_quantity >= 0)`** on the table as the last safety net.

Invalid state changes return **409 Conflict**. Short stock returns **400** naming every
short product.

## Tests (PostgreSQL, inside docker compose)

`docker compose exec web python manage.py test sales -v 2`

1. Three-line sale, third line short: 400, all three products keep their old stock,
   no StockMovement written, sale still open.
2. Cash too low: `PaymentError`, nothing changes (no product rows locked, no stock moved).
3. Two tills, one carton left (two threads, `TransactionTestCase`): exactly one pays,
   the other gets a clean "short".
4. Refund puts stock back via refund movements; stock equals the sum of movements;
   refunding twice returns 409.

### Run 1: with `select_for_update()` (normal)
All sales tests pass.

### Run 2: `select_for_update()` removed from `pay_sale` (plus a 0.3s sleep to widen the race window)
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

## Questions and answers
- **Why lock product rows in id order?** Two sales with the same two products added in opposite
  orders would each hold one lock and wait for the other (deadlock). One global order
  makes a cycle impossible.
- **Why would the concurrency test prove little on SQLite?** SQLite lets one writer at a time
  for the whole file and ignores `select_for_update`, so the race never really happens.
- **Why 409 and not 400 for "pay a cancelled sale"?** The request is valid; the sale's current
  state does not allow it.