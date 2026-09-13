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

## Yahoo profiles and whale tweets

`test_profile_whale_saves.py` covers the Yahoo Finance profile writer and
`WhaleTracker.save_to_db()`.

The profile writer uses a savepoint for each company upsert. Rejected profiles
do not discard valid inserts or updates from earlier in the run. Fetch errors
are logged separately from database errors. The final total counts successful
upserts, including updates to existing companies, after the batch commits.
The function still returns no value.

The whale writer uses a savepoint for each `(tweet_id, token)` record. If one
token fails, other tokens from the same tweet can still be saved. Its return
value counts newly inserted database records, so one tweet can add more than
one record. Console totals now say tweet/token records. Duplicate pairs are
skipped. The high signal summary counts distinct tweets with at least one
newly inserted token record, and is printed only after the commit succeeds.

On a failed commit, the profile writer skips its success summary and the whale
writer returns zero without printing a saved total. The whale writer closes
its cursor and returns the connection to the pool on both success and failure.

Tests use the committed `company_profiles` and `twitter_sentiment` schemas,
including the 255 character company name limit, the 20 character token limit,
and the sentiment check constraints. A deferred trigger tests commit failure.
They also cover preserved updates, unavailable Yahoo data, duplicates, partial
token failures, high signal totals, empty inputs, missing connections, and
connection reuse after rollback.

Yahoo responses, Twitter setup, sentiment helper outputs, and pool handoff
calls are stubbed. The pool hands out a real psycopg2 connection. The connection
subclass only records cursors so the tests can check cleanup; it does not mock
SQL execution. Saved rows are read through a separate database connection.
No Yahoo, Twitter, model, or local credential setup is needed for these tests.

Run this group with the same disposable database:

```bash
python -m unittest discover -s tests -p "test_profile_whale_saves.py" -v
```

The existing full suite command and PostgreSQL 16 workflow also run this group.
