import asyncio
from collections import defaultdict, deque
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import logging
import os
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
import warnings

import psycopg2
from psycopg2 import extensions, sql


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Only external services and learning calculations are stubbed. SQL runs on PostgreSQL.
external_modules = {
    name: ModuleType(name)
    for name in ('requests', 'requests.exceptions', 'schedule', 'dotenv', 'twikit',
                 'monitors.health_monitor', 'nice_funcs.twitter_funcs',
                 'nice_funcs.wallet_labels', 'scraper_utils.heartbeat', 'numpy',
                 'sklearn', 'sklearn.preprocessing', 'sklearn.decomposition')
}
external_modules['dotenv'].load_dotenv = lambda **kwargs: None
external_modules['requests'].get = Mock(side_effect=AssertionError('Unexpected HTTP request'))
external_modules['requests.exceptions'].HTTPError = type('HTTPError', (Exception,), {})
external_modules['requests'].exceptions = external_modules['requests.exceptions']
external_modules['twikit'].TooManyRequests = type('TooManyRequests', (Exception,), {})
external_modules['monitors.health_monitor'].HealthMonitor = Mock(side_effect=lambda *a, **kw: Mock())
external_modules['nice_funcs.wallet_labels'].wallet_labels = Mock()
external_modules['scraper_utils.heartbeat'].touch_heartbeat = Mock()
external_modules['sklearn.preprocessing'].StandardScaler = Mock()
external_modules['sklearn.decomposition'].PCA = Mock()
twitter_helpers = external_modules['nice_funcs.twitter_funcs']
for name in ('setup_httpx_patching', 'init_vader_with_crypto_lexicon', 'get_pooled_client',
             'auto_refresh_cookies', 'get_db_connection', 'update_token_sentiment_history'):
    setattr(twitter_helpers, name, Mock())
twitter_helpers.analyze_sentiment = Mock(return_value=0.5)
twitter_helpers.calculate_bot_probability = Mock(return_value=0.0)
twitter_helpers.calculate_influence_weight = Mock(return_value=0.5)
twitter_helpers.detect_pump_pattern = Mock(return_value=0.0)
twitter_helpers.calculate_volume_spike = Mock(return_value=1.0)
twitter_helpers.calculate_token_velocity_metrics = Mock(return_value=None)
twitter_helpers.validate_sentiment_data = lambda **kwargs: kwargs
twitter_helpers.SPAM_KEYWORDS = []
with patch.dict(sys.modules, external_modules), warnings.catch_warnings():
    from fundamentals_data import fmp_fundamentals_reader as fmp
    from crypto_scrapers import exchange_flows, dex_liquidity_monitor, stablecoin_flow_scraper
    from crypto_scrapers import twitter_token_base
    from crypto_scrapers.twitter_ai import TwitterAI
    from crypto_scrapers.twitter_defi import TwitterDeFi
    from crypto_scrapers.twitter_emerging import TwitterEmerging
    from crypto_scrapers.twitter_largecaps import TwitterLargecaps
    from crypto_scrapers.twitter_layer1s import TwitterLayer1s
    from crypto_scrapers.twitter_layer2s import TwitterLayer2s
    from crypto_scrapers.twitter_memecoins import TwitterMemecoins
    from crypto_ai_trader.ai_optimizer import AIOptimizer
    from crypto_ai_trader.trade_learner import TradeLearner


class RecordingConnection(extensions.connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.opened_cursors = []

    def cursor(self, *args, **kwargs):
        cursor = super().cursor(*args, **kwargs)
        self.opened_cursors.append(cursor)
        return cursor


def profile(number):
    return {
        'symbol': f'TEST{number}', 'companyName': f'Company {number}',
        'exchangeShortName': 'NASDAQ', 'industry': 'Software', 'sector': 'Technology',
        'mktCap': 1000000, 'beta': 1.0, 'price': 40.0, 'eps': 2.0,
        'website': 'https://example.com',
    }


def tweet(number, token='BTC'):
    return {
        'tweet_id': str(number), 'token': token, 'text': 'Watching BTC',
        'username': 'test_author', 'bio': '', 'profile_image_custom': True,
        'followers': 10000, 'following': 100, 'retweets': 1, 'likes': 2,
        'replies': 0, 'quotes': 0,
        'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
        'timestamp': datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


def flow(number):
    return {
        'token': 'BTC', 'flow_type': 'inflow', 'amount': 1.0, 'usd_value': 60000.0,
        'exchange': 'test', 'transaction_hash': f'tx{number}',
        'timestamp': datetime(2026, 1, 1, tzinfo=timezone.utc), 'source': 'test',
    }


def dex_metric(number):
    return {
        'token': f'TOKEN{number}', 'dex_name': 'test',
        'timestamp': datetime(2026, 1, 1, tzinfo=timezone.utc),
        'liquidity_usd': 10000.0, 'volume_24h': 2000.0, 'price_usd': 1.0,
        'price_change_24h': 0.0, 'pool_count': 1, 'fdv': 100000.0,
        'market_cap': 50000.0, 'volume_to_liquidity_ratio': 0.2,
    }


def stablecoin_metric(number):
    return {
        'symbol': f'USD{number}', 'timestamp': datetime(2026, 1, 1, tzinfo=timezone.utc),
        'market_cap': 100000.0, 'total_volume_24h': 10000.0, 'circulating_supply': 100000.0,
        'velocity_ratio': 0.1, 'supply_change_24h': 100.0, 'supply_change_pct_24h': 0.1,
        'price_usd': 1.0, 'price_deviation_pct': 0.0, 'btc_price': 60000.0,
        'total_stablecoin_mcap': 200000.0, 'dominance_pct': 50.0,
    }


METRIC_WRITERS = (
    ('dex_liquidity', dex_liquidity_monitor.DEXLiquidityMonitor, dex_metric, 'token', 20),
    ('stablecoin_metrics', stablecoin_flow_scraper.StablecoinFlowScraper, stablecoin_metric, 'symbol', 10),
)


class RemainingSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.environ.get('TEST_DATABASE_URL')
        if not cls.database_url:
            raise RuntimeError('Set TEST_DATABASE_URL to a disposable PostgreSQL database.')

    def setUp(self):
        self.schema_name = 'test_remaining_saves_' + uuid4().hex
        self.addCleanup(self.drop_schema)
        schema = (ROOT / 'data/pjx_database_schema.sql').read_text(encoding='utf-8')
        conn = psycopg2.connect(self.database_url, connect_timeout=10)
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema_name)))
                cursor.execute(sql.SQL('SET search_path TO {}, pg_catalog').format(
                    sql.Identifier(self.schema_name)
                ))
                for table in ('company_profiles', 'twitter_sentiment', 'exchange_flows',
                              'dex_liquidity', 'stablecoin_metrics', 'model_performance',
                              'trade_experiences', 'pattern_memory', 'strategy_evolution',
                              'learning_metrics'):
                    match = re.search(r'CREATE TABLE public\.' + table + r' \((.*?)\n\);', schema, re.DOTALL)
                    self.assertIsNotNone(match)
                    cursor.execute(sql.SQL('CREATE TABLE {} ({})').format(
                        sql.Identifier(table), sql.SQL(match.group(1))
                    ))
                    if re.search(r'^\s+id ', match.group(1), re.MULTILINE):
                        cursor.execute(sql.SQL(
                            'ALTER TABLE {} ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY'
                        ).format(sql.Identifier(table)))
                        cursor.execute(sql.SQL('ALTER TABLE {} ADD PRIMARY KEY (id)').format(sql.Identifier(table)))
                cursor.execute('ALTER TABLE company_profiles ADD UNIQUE (symbol)')
                cursor.execute('ALTER TABLE twitter_sentiment ADD UNIQUE (tweet_id, token)')
                cursor.execute('ALTER TABLE dex_liquidity ADD UNIQUE (token, dex_name, timestamp)')
                cursor.execute('ALTER TABLE stablecoin_metrics ADD UNIQUE (symbol, timestamp)')
            conn.commit()
        finally:
            conn.close()

    def connect(self):
        conn = psycopg2.connect(
            self.database_url, connect_timeout=10, connection_factory=RecordingConnection
        )
        self.addCleanup(conn.close)
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL('SET search_path TO {}, pg_catalog').format(
                sql.Identifier(self.schema_name)
            ))
        conn.commit()
        return conn

    def query(self, statement):
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(statement)
                rows = cursor.fetchall() if cursor.description else None
            conn.commit()
            return rows
        finally:
            conn.close()

    def drop_schema(self):
        conn = psycopg2.connect(self.database_url, connect_timeout=10)
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(
                    sql.Identifier(self.schema_name)
                ))
            conn.commit()
        finally:
            conn.close()

    def reject_commit(self, table):
        self.query('''
            CREATE OR REPLACE FUNCTION reject_remaining_commit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'test commit failure';
            END;
            $$;
        ''')
        self.query(sql.SQL('''
            CREATE CONSTRAINT TRIGGER reject_remaining_commit
            AFTER INSERT OR UPDATE ON {} DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION reject_remaining_commit()
        ''').format(sql.Identifier(table)))

    def allow_commit(self, table):
        self.query(sql.SQL('DROP TRIGGER reject_remaining_commit ON {}').format(sql.Identifier(table)))

    def assert_ready(self, conn):
        self.assertFalse(conn.closed)
        self.assertEqual(conn.get_transaction_status(), extensions.TRANSACTION_STATUS_IDLE)
        self.assertTrue(all(cursor.closed for cursor in conn.opened_cursors))

    def call_quietly(self, method, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            result = method(*args)
        return result, output.getvalue()

    def store_profiles(self, records):
        by_symbol = {item['symbol']: item for item in records}

        def fetch(url, timeout):
            symbol = url.split('/profile/', 1)[1].split('?', 1)[0]
            item = by_symbol[symbol]
            if item.get('fetch_error'):
                raise fmp.requests.exceptions.HTTPError('test FMP fetch failure')
            return SimpleNamespace(raise_for_status=lambda: None,
                                   json=lambda: [] if item.get('empty') else [item])

        conn = self.connect()
        with patch.object(fmp, 'get_db_connection', return_value=conn), \
                patch.object(fmp, 'TICKERS_TO_MONITOR', list(by_symbol)), \
                patch.object(fmp.requests, 'get', side_effect=fetch), \
                patch.object(fmp.time, 'sleep'), \
                patch.object(logging, 'info') as info, patch.object(logging, 'error') as error:
            result = fmp.fetch_and_store_fundamentals()
        self.assertIsNone(result)
        self.assertTrue(conn.closed)
        return SimpleNamespace(messages=[c.args[0] for c in info.call_args_list],
                               errors=[c.args[0] for c in error.call_args_list])

    def assert_profile_count(self, count, report):
        self.assertIn(f'Fundamentals fetch complete. Upserted data for {count} companies.', report.messages)

    def test_fmp_rejected_profile_preserves_before_and_after_rows(self):
        for bad_index in (0, 2, 4):
            with self.subTest(bad_index=bad_index):
                self.query('TRUNCATE company_profiles')
                records = [profile(i) for i in range(1, 6)]
                records[bad_index]['companyName'] = 'x' * 256
                report = self.store_profiles(records)
                self.assertEqual(self.query('SELECT symbol FROM company_profiles ORDER BY symbol'),
                                 [(r['symbol'],) for i, r in enumerate(records) if i != bad_index])
                self.assert_profile_count(4, report)
                self.assertEqual(len(report.errors), 1)
                self.assertIn('Database upsert failed', report.errors[0])

    def test_fmp_update_survives_later_rejection(self):
        self.store_profiles([profile(1)])
        records = [profile(1), profile(2), profile(3)]
        records[0]['companyName'] = 'Updated'
        records[1]['companyName'] = 'x' * 256
        report = self.store_profiles(records)
        self.assertEqual(self.query('SELECT symbol, company_name FROM company_profiles ORDER BY symbol'),
                         [('TEST1', 'Updated'), ('TEST3', 'Company 3')])
        self.assert_profile_count(2, report)

    def test_fmp_fetch_failures_and_empty_responses_do_not_poison_batch(self):
        for field in ('fetch_error', 'empty'):
            with self.subTest(field=field):
                self.query('TRUNCATE company_profiles')
                records = [profile(1), profile(2), profile(3)]
                records[1][field] = True
                report = self.store_profiles(records)
                self.assertEqual(self.query('SELECT symbol FROM company_profiles ORDER BY symbol'),
                                 [('TEST1',), ('TEST3',)])
                self.assert_profile_count(2, report)

    def test_fmp_failed_commit_has_no_success_report(self):
        self.reject_commit('company_profiles')
        report = self.store_profiles([profile(1), profile(2)])
        self.assertEqual(self.query('SELECT COUNT(*) FROM company_profiles'), [(0,)])
        self.assertFalse(any('Successfully upserted' in m or 'Fundamentals fetch complete' in m
                             for m in report.messages), report.messages)
        self.assertTrue(any('test commit failure' in m for m in report.errors), report.errors)

    def make_twitter(self, cls=None):
        scraper = cls() if cls else twitter_token_base.TwitterTokenScraperBase(['BTC'], 'test')
        scraper.db_pool = SimpleNamespace(get_connection=Mock(return_value=self.connect()),
                                           return_connection=Mock())
        return scraper

    def store_tweets(self, scraper, records):
        result, output = self.call_quietly(scraper.save_to_db, records)
        if records:
            conn = scraper.db_pool.get_connection.return_value
            self.assertEqual(scraper.db_pool.get_connection.call_count,
                             scraper.db_pool.return_connection.call_count)
            scraper.db_pool.return_connection.assert_called_with(conn)
            self.assert_ready(conn)
        return result, output

    def test_token_tweets_preserve_rows_around_rejection(self):
        for bad_index in (0, 2, 4):
            with self.subTest(bad_index=bad_index):
                self.query('TRUNCATE twitter_sentiment')
                records = [tweet(i) for i in range(1, 6)]
                records[bad_index]['username'] = 'x' * 101
                count, output = self.store_tweets(self.make_twitter(), records)
                self.assertEqual(count, 4)
                self.assertEqual(self.query('SELECT tweet_id FROM twitter_sentiment ORDER BY tweet_id'),
                                 [(r['tweet_id'],) for i, r in enumerate(records) if i != bad_index])
                self.assertIn('[OK] Saved 4 new tweets', output)
                self.assertEqual(output.count('[WARNING] Failed to insert tweet'), 1)

    def test_all_seven_twitter_callers_keep_their_source_and_partial_save_count(self):
        for cls in (TwitterAI, TwitterDeFi, TwitterEmerging, TwitterLargecaps,
                    TwitterLayer1s, TwitterLayer2s, TwitterMemecoins):
            with self.subTest(scraper=cls.__name__):
                self.query('TRUNCATE twitter_sentiment')
                scraper = self.make_twitter(cls)
                records = [tweet(i, scraper.tokens[0]) for i in range(1, 4)]
                records[1]['username'] = 'x' * 101
                count, _ = self.store_tweets(scraper, records)
                self.assertEqual(count, 2)
                self.assertEqual(self.query('SELECT tweet_id, token, source FROM twitter_sentiment ORDER BY tweet_id'),
                                 [('1', scraper.tokens[0], scraper.source), ('3', scraper.tokens[0], scraper.source)])

    def test_token_tweet_duplicates_count_once_per_token(self):
        scraper = self.make_twitter()
        self.assertEqual(self.store_tweets(scraper, [tweet(1), tweet(1), tweet(1, 'ETH')])[0], 2)
        self.assertEqual(self.store_tweets(scraper, [tweet(1), tweet(1, 'ETH')])[0], 0)
        self.assertEqual(self.query('SELECT COUNT(*) FROM twitter_sentiment'), [(2,)])

    def test_token_tweet_failed_commit_returns_zero_and_pool_connection_is_reusable(self):
        self.reject_commit('twitter_sentiment')
        scraper = self.make_twitter()
        count, output = self.store_tweets(scraper, [tweet(1), tweet(2)])
        self.assertEqual(count, 0)
        self.assertNotIn('[OK] Saved', output)
        self.assertEqual(self.query('SELECT COUNT(*) FROM twitter_sentiment'), [(0,)])
        self.allow_commit('twitter_sentiment')
        self.assertEqual(self.store_tweets(scraper, [tweet(3)])[0], 1)
        self.assertEqual(self.query('SELECT tweet_id FROM twitter_sentiment'), [('3',)])

    def test_token_tweet_empty_input_does_not_borrow_connection(self):
        scraper = self.make_twitter()
        self.assertEqual(self.store_tweets(scraper, [])[0], 0)
        scraper.db_pool.get_connection.assert_not_called()
        scraper.db_pool.return_connection.assert_not_called()

    def test_token_cycle_health_uses_committed_count(self):
        scraper = self.make_twitter()
        records = [tweet(1), tweet(2), tweet(3)]
        records[1]['username'] = 'x' * 101
        scraper.get_tweets_for_token = AsyncMock(return_value=records)
        with redirect_stdout(io.StringIO()):
            asyncio.run(scraper.run_cycle())
        scraper.health.record_cycle.assert_called_once_with(2)
        self.assertEqual(self.query('SELECT tweet_id FROM twitter_sentiment ORDER BY tweet_id'), [('1',), ('3',)])

    def make_flows(self):
        scraper = exchange_flows.ExchangeFlowScraper.__new__(exchange_flows.ExchangeFlowScraper)
        scraper.db_conn = self.connect()
        return scraper

    def test_exchange_flows_preserve_rows_around_rejection(self):
        for bad_index in (0, 2, 4):
            with self.subTest(bad_index=bad_index):
                self.query('TRUNCATE exchange_flows')
                scraper = self.make_flows()
                records = [flow(i) for i in range(1, 6)]
                records[bad_index]['exchange'] = 'x' * 51
                count, output = self.call_quietly(scraper.save_to_db, records)
                self.assertEqual(count, 4)
                self.assertEqual(self.query('SELECT transaction_hash FROM exchange_flows ORDER BY transaction_hash'),
                                 [(r['transaction_hash'],) for i, r in enumerate(records) if i != bad_index])
                self.assertEqual(output.count('[WARNING] Failed to save flow'), 1)
                self.assert_ready(scraper.db_conn)

    def test_exchange_flow_duplicates_do_not_count_or_block_later_insert(self):
        scraper = self.make_flows()
        self.assertEqual(scraper.save_to_db([flow(1), flow(1), flow(2)]), 2)
        self.assertEqual(scraper.save_to_db([flow(1), flow(3)]), 1)
        self.assertEqual(self.query('SELECT transaction_hash FROM exchange_flows ORDER BY transaction_hash'),
                         [('tx1',), ('tx2',), ('tx3',)])
        self.assert_ready(scraper.db_conn)

    def test_exchange_flow_failed_commit_returns_zero_and_recovers(self):
        self.reject_commit('exchange_flows')
        scraper = self.make_flows()
        count, output = self.call_quietly(scraper.save_to_db, [flow(1), flow(2)])
        self.assertEqual(count, 0)
        self.assertIn('test commit failure', output)
        self.assertEqual(self.query('SELECT COUNT(*) FROM exchange_flows'), [(0,)])
        self.assert_ready(scraper.db_conn)
        self.allow_commit('exchange_flows')
        self.assertEqual(scraper.save_to_db([flow(3)]), 1)

    def test_exchange_index_failure_keeps_other_indexes(self):
        self.query('ALTER TABLE exchange_flows DROP COLUMN flow_type')
        scraper = self.make_flows()
        _, output = self.call_quietly(scraper.create_indexes)
        names = {r[0] for r in self.query('''
            SELECT indexname FROM pg_indexes
            WHERE schemaname = current_schema() AND indexname LIKE 'idx_flows_%'
        ''')}
        self.assertEqual(names, {'idx_flows_token', 'idx_flows_timestamp', 'idx_flows_value',
                                'idx_flows_smart_money', 'idx_flows_signal'})
        self.assertIn('Failed to create flow index', output)
        self.assert_ready(scraper.db_conn)

    def test_atomic_metric_batch_rejection_reports_zero_and_next_batch_works(self):
        for table, cls, make, key, limit in METRIC_WRITERS:
            for bad_index in (0, 1, 2):
                with self.subTest(table=table, bad_index=bad_index):
                    self.query(sql.SQL('TRUNCATE {}').format(sql.Identifier(table)))
                    scraper = cls.__new__(cls)
                    scraper.db_conn = self.connect()
                    records = [make(i) for i in range(1, 4)]
                    records[bad_index][key] = 'x' * (limit + 1)
                    count, _ = self.call_quietly(scraper.save_metrics, records)
                    self.assertEqual(count, 0)
                    self.assertEqual(self.query(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table))), [(0,)])
                    self.assert_ready(scraper.db_conn)
                    self.assertEqual(scraper.save_metrics([make(4)]), 1)
                    self.assertEqual(self.query(sql.SQL('SELECT {} FROM {}').format(
                        sql.Identifier(key), sql.Identifier(table))), [(make(4)[key],)])

    def test_atomic_metric_commit_failure_reports_zero_and_recovers(self):
        for table, cls, make, key, limit in METRIC_WRITERS:
            with self.subTest(table=table):
                self.reject_commit(table)
                scraper = cls.__new__(cls)
                scraper.db_conn = self.connect()
                count, output = self.call_quietly(scraper.save_metrics, [make(1), make(2)])
                self.assertEqual(count, 0)
                self.assertIn('test commit failure', output)
                self.assertEqual(self.query(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table))), [(0,)])
                self.assert_ready(scraper.db_conn)
                self.allow_commit(table)
                self.assertEqual(scraper.save_metrics([make(3)]), 1)

    def test_atomic_metric_success_duplicates_and_empty_input(self):
        for table, cls, make, key, limit in METRIC_WRITERS:
            with self.subTest(table=table):
                scraper = cls.__new__(cls)
                scraper.db_conn = self.connect()
                self.assertEqual(scraper.save_metrics([]), 0)
                self.assertEqual(scraper.save_metrics([make(1), make(2), make(1)]), 2)
                self.assertEqual(scraper.save_metrics([make(1), make(2)]), 0)
                self.assertEqual(self.query(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table))), [(2,)])
                self.assert_ready(scraper.db_conn)

    def test_dex_historical_changes_still_use_saved_metrics(self):
        scraper = dex_liquidity_monitor.DEXLiquidityMonitor.__new__(dex_liquidity_monitor.DEXLiquidityMonitor)
        scraper.db_conn = self.connect()
        first = dex_metric(1)
        second = dex_metric(1)
        second.update(timestamp=first['timestamp'] + timedelta(days=1),
                      liquidity_usd=12000.0, volume_24h=3000.0)
        self.assertEqual(scraper.save_metrics([first, second]), 2)
        values = self.query('SELECT liquidity_change_24h, volume_change_24h FROM dex_liquidity ORDER BY timestamp')
        self.assertEqual(values, [(0, 0), (20, 50)])

    def make_optimizer(self):
        optimizer = AIOptimizer.__new__(AIOptimizer)
        optimizer.conn = self.connect()
        optimizer.model_performance = defaultdict(lambda: {
            'trades': 0, 'wins': 0, 'total_pnl': 0, 'last_30_days': [],
        })
        return optimizer

    def record_decision(self, optimizer, token='BTC'):
        return self.call_quietly(optimizer.track_decision, 'test_model', token,
                                 {'action': 'BUY', 'confidence': 0.7, 'position_size': 100,
                                  'scenario': 'test'}, {'pnl': 10.0, 'profitable': True})

    def test_optimizer_rejected_decision_does_not_poison_next_save(self):
        optimizer = self.make_optimizer()
        _, output = self.record_decision(optimizer, 'x' * 21)
        self.assertIn('Failed to track decision', output)
        self.assert_ready(optimizer.conn)
        self.assertEqual(dict(optimizer.model_performance), {})
        self.record_decision(optimizer)
        self.assertEqual(self.query('SELECT token FROM model_performance'), [('BTC',)])
        self.assertEqual(optimizer.model_performance['test_model']['trades'], 1)

    def test_optimizer_failed_commit_does_not_update_memory_and_recovers(self):
        self.reject_commit('model_performance')
        optimizer = self.make_optimizer()
        _, output = self.record_decision(optimizer)
        self.assertIn('test commit failure', output)
        self.assert_ready(optimizer.conn)
        self.assertEqual(dict(optimizer.model_performance), {})
        self.assertEqual(self.query('SELECT COUNT(*) FROM model_performance'), [(0,)])
        self.allow_commit('model_performance')
        self.record_decision(optimizer)
        self.assertEqual(self.query('SELECT token FROM model_performance'), [('BTC',)])

    def test_optimizer_load_query_failure_recovers_connection(self):
        self.query('ALTER TABLE model_performance RENAME COLUMN profitable TO old_profitable')
        optimizer = self.make_optimizer()
        _, output = self.call_quietly(optimizer.load_model_performance)
        self.assertIn('Failed to load model performance', output)
        self.assert_ready(optimizer.conn)
        self.query('ALTER TABLE model_performance RENAME COLUMN old_profitable TO profitable')
        self.record_decision(optimizer)
        self.call_quietly(optimizer.load_model_performance)
        self.assertEqual(optimizer.model_performance['test_model']['trades'], 1)
        optimizer.conn.rollback()
        self.assertEqual(self.query('SELECT token FROM model_performance'), [('BTC',)])

    def test_optimizer_read_errors_allow_later_writes(self):
        calls = (('get_best_model_for_scenario', ('test',)),
                 ('get_token_performance', ('BTC',)), ('get_recent_performance', ()))
        for name, args in calls:
            with self.subTest(method=name):
                self.query('TRUNCATE model_performance')
                self.query('ALTER TABLE model_performance RENAME TO missing_model_performance')
                optimizer = self.make_optimizer()
                result, output = self.call_quietly(getattr(optimizer, name), *args)
                self.assertIsNone(result)
                self.assertIn('[ERROR]', output)
                try:
                    self.assert_ready(optimizer.conn)
                finally:
                    optimizer.conn.rollback()
                    self.query('ALTER TABLE missing_model_performance RENAME TO model_performance')
                self.record_decision(optimizer)
                self.assertEqual(self.query('SELECT token FROM model_performance'), [('BTC',)])

    def make_learner(self):
        learner = TradeLearner.__new__(TradeLearner)
        learner.conn = self.connect()
        learner.experience_buffer = deque(maxlen=10000)
        learner.strategy_evolution = {'current_generation': 0}
        learner.performance_metrics = {}
        learner.strategy_params = {}
        learner.feature_importance = {}
        learner._calculate_actual_reward = Mock(return_value=1.0)
        learner._predict_reward = Mock(return_value=0.5)
        learner._extract_pattern_hash = Mock(return_value='test_pattern')
        learner._update_pattern_memory = Mock()
        learner._learn_from_experience = Mock()
        learner._update_feature_importance = Mock()
        return learner

    def record_experience(self, learner, token='BTC'):
        return self.call_quietly(learner.record_trade_experience, token, {'regime': 'test'},
                                 {'action': 'BUY'}, {'pnl': 10.0})

    def test_learner_rejected_experience_is_not_buffered_and_next_save_works(self):
        learner = self.make_learner()
        _, output = self.record_experience(learner, 'x' * 21)
        self.assertIn('Failed to record experience', output)
        self.assert_ready(learner.conn)
        self.assertEqual(len(learner.experience_buffer), 0)
        learner._learn_from_experience.assert_not_called()
        self.record_experience(learner)
        self.assertEqual(self.query('SELECT token FROM trade_experiences'), [('BTC',)])
        self.assertEqual(len(learner.experience_buffer), 1)
        learner._learn_from_experience.assert_called_once()

    def test_learner_commit_failure_is_not_buffered_and_next_save_works(self):
        self.reject_commit('trade_experiences')
        learner = self.make_learner()
        _, output = self.record_experience(learner)
        self.assertIn('test commit failure', output)
        self.assert_ready(learner.conn)
        self.assertEqual(len(learner.experience_buffer), 0)
        learner._learn_from_experience.assert_not_called()
        self.assertEqual(self.query('SELECT COUNT(*) FROM trade_experiences'), [(0,)])
        self.allow_commit('trade_experiences')
        self.record_experience(learner)
        self.assertEqual(self.query('SELECT token FROM trade_experiences'), [('BTC',)])
        self.assertEqual(len(learner.experience_buffer), 1)

    def test_learner_downstream_sql_failure_recovers_without_losing_committed_experience(self):
        learner = self.make_learner()
        learner.experience_buffer.extend([{}] * 49)

        def fail_evolution():
            with learner.conn.cursor() as cursor:
                cursor.execute('SELECT 1 / 0')

        learner._evolve_strategy = Mock(side_effect=fail_evolution)
        _, output = self.record_experience(learner)
        learner._evolve_strategy.assert_called_once()
        self.assertIn('division by zero', output)
        self.assert_ready(learner.conn)
        self.assertEqual(self.query('SELECT token FROM trade_experiences'), [('BTC',)])
        self.record_experience(learner, 'ETH')
        self.assertEqual(self.query('SELECT token FROM trade_experiences ORDER BY id'), [('BTC',), ('ETH',)])

    def test_learner_read_errors_allow_later_writes(self):
        calls = (
            ('_get_pattern_performance', ('test',), 'pattern_memory'),
            ('_get_pattern_performance_with_validation', ('test', 'test'), 'pattern_memory'),
            ('_get_token_statistics', ('BTC',), 'trade_experiences'),
            ('_get_best_historical_strategy', (), 'strategy_evolution'),
            ('get_learning_report', (), 'pattern_memory'),
            ('get_top_patterns', (), 'pattern_memory'),
        )
        for name, args, table in calls:
            with self.subTest(method=name):
                self.query('TRUNCATE trade_experiences')
                self.query(sql.SQL('ALTER TABLE {} RENAME TO unavailable_table').format(sql.Identifier(table)))
                learner = self.make_learner()
                self.call_quietly(getattr(learner, name), *args)
                try:
                    self.assert_ready(learner.conn)
                finally:
                    learner.conn.rollback()
                    self.query(sql.SQL('ALTER TABLE unavailable_table RENAME TO {}').format(sql.Identifier(table)))
                self.record_experience(learner)
                self.assertEqual(self.query('SELECT token FROM trade_experiences'), [('BTC',)])

    def test_learner_legacy_pattern_fallback_runs_after_query_error(self):
        # The committed schema lacks the newer regime columns used by the first query.
        self.query("INSERT INTO pattern_memory (pattern_hash, occurrences, success_rate, avg_profit) VALUES ('test', 5, 0.6, 2.0)")
        learner = self.make_learner()
        result, output = self.call_quietly(learner._get_pattern_performance_with_validation, 'test', 'bull')
        self.assertIsNotNone(result)
        self.assertEqual(result['occurrences'], 5)
        self.assertEqual(output.count('[ERROR]'), 1)
        self.record_experience(learner)
        self.assertEqual(self.query('SELECT token FROM trade_experiences'), [('BTC',)])


if __name__ == '__main__':
    unittest.main()
