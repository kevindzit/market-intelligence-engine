# Database tests

## News writers

These tests cover `rss_aggregator.store_articles()` and
`newsapi_reader.fetch_and_store_news()`.

Both writers use a savepoint around each insert. A rejected article is rolled
back on its own, and the remaining articles can still be saved. Duplicate URLs
are skipped and do not increase the added count.

The RSS function returns its count after a successful commit, or zero after a
database failure. NewsAPI logs its final added count after a successful commit.
It does not return a count. Its debug messages say an article is queued while
the transaction is still pending.

## Run the tests

Use Python 3.12 and a disposable PostgreSQL database. The database user needs
permission to create schemas, tables, functions, and triggers in that database.

```bash
python -m pip install psycopg2-binary==2.9.11
export TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/market_tests"
python -m unittest discover -s tests -p "test_news_saves.py" -v
```

In PowerShell, set the connection string with:

```powershell
$env:TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/market_tests"
```

The tests create a separate schema for each test and drop it during cleanup.
Table columns come from the committed `data/pjx_database_schema.sql`, including
`title TEXT` and `source VARCHAR(100)`. A 101 character source causes a real
insert error. A separate test confirms that 300 character titles are preserved.
A deferred trigger forces a failure at commit time.

The tests read saved rows through a new connection after the writer closes its
connection. Only feed/API access, logging capture, and local `.env` loading are
stubbed. SQL execution, commits, rollbacks, and connection closing use psycopg2.
No feed or NewsAPI credentials are needed.

GitHub Actions runs these tests against PostgreSQL 16. This workflow has its own
filename and can run alongside the Binance database workflow.

## FRED and EDGAR writers

`test_fundamentals_saves.py` covers `fetch_and_store_fred_data()` and
`fetch_and_store_sec_filings()`.

Both writers use a savepoint for each insert. A rejected indicator or filing
is rolled back on its own, so valid rows before and after it can still be saved.
Neither function returns a count. Their final log messages report new rows
only after the transaction commits. Duplicate records do not increase the count.
Messages inside the transaction say a record is queued, since it is not saved yet.

FRED logs fetch or data reading errors separately from database insert errors.
It continues with the next indicator in either case. Failed commits roll back
the batch and do not produce a success summary. EDGAR also skips its heartbeat
when the database batch fails.

The tests create the two tables from `data/pjx_database_schema.sql`. They use
the real column limits: `indicator_code VARCHAR(20)` and
`company_name VARCHAR(255)`. Overlong values cause insert errors without
changing the schema or truncating any data. Values at the limits are preserved.
A deferred trigger causes a real commit failure.

Coverage includes rejected records at the start, middle, and end of a batch,
duplicates, repeated runs, empty runs, failed commits, missing or invalid FRED
data, and EDGAR's existing form filter and title parsing. Saved rows are checked
through a new connection after the writer closes its connection.

FRED and feed responses, sleep calls, logging capture, local `.env` loading,
and heartbeat writes are stubbed. SQL execution, connections, savepoints,
commits, and rollbacks use psycopg2. No FRED key or SEC request is needed.

Run just these tests with the same disposable database:

```bash
python -m unittest discover -s tests -p "test_fundamentals_saves.py" -v
```

Run the combined Binance, news, FRED, and EDGAR suite from the repository root:

```bash
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

The existing `.github/workflows/tests.yml` discovers all of these tests and
runs them against PostgreSQL 16. No new workflow or dependency is needed.
