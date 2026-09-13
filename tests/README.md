# News database tests

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
