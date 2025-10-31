"""
Setup script for AI Trading System database tables
Creates all necessary tables for trading decisions, portfolio tracking, and paper trading
Run this once to initialize the trading system
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')


def create_trading_tables():
    """Create all AI trading system tables"""

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )

        cursor = conn.cursor()

        print("Creating AI Trading System tables...\n")

        # =====================================================================
        # TABLE: trading_decisions
        # Logs every decision made by Tier 1 (Claude) and Tier 2 (Ensemble)
        # =====================================================================

        print("1. Creating trading_decisions table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trading_decisions (
                id SERIAL PRIMARY KEY,
                token VARCHAR(20) NOT NULL,
                decision_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                -- Tier 1 Decision (Claude initial screening)
                tier1_action VARCHAR(10),
                tier1_confidence NUMERIC(5,4),
                tier1_reasoning TEXT,

                -- Tier 2 Decision (Ensemble verification for BUY signals)
                tier2_triggered BOOLEAN DEFAULT false,
                tier2_action VARCHAR(10),
                tier2_confidence NUMERIC(5,4),
                tier2_consensus_score NUMERIC(5,4),

                -- Final Decision (what was actually executed)
                final_action VARCHAR(10) NOT NULL,
                final_confidence NUMERIC(5,4),

                -- Trade Parameters
                position_size_pct NUMERIC(5,2),
                position_size_usd NUMERIC(12,2),
                entry_price NUMERIC(20,8),
                stop_loss NUMERIC(20,8),
                take_profit NUMERIC(20,8),

                -- Market Context (snapshot of data at decision time)
                sentiment_summary JSONB,
                price_context JSONB,

                -- Execution Status
                status VARCHAR(20) DEFAULT 'PENDING',
                executed_at TIMESTAMP WITH TIME ZONE,
                rejected_reason TEXT,

                -- Performance Tracking
                outcome VARCHAR(20),
                exit_price NUMERIC(20,8),
                pnl_usd NUMERIC(12,2),
                pnl_pct NUMERIC(8,4),
                closed_at TIMESTAMP WITH TIME ZONE
            );
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_decisions_token ON trading_decisions(token);
            CREATE INDEX IF NOT EXISTS idx_decisions_time ON trading_decisions(decision_time DESC);
            CREATE INDEX IF NOT EXISTS idx_decisions_status ON trading_decisions(status);
            CREATE INDEX IF NOT EXISTS idx_decisions_outcome ON trading_decisions(outcome);
        """)

        # =====================================================================
        # TABLE: ensemble_votes
        # Tracks individual model votes for Tier 2 ensemble verification
        # =====================================================================

        print("2. Creating ensemble_votes table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ensemble_votes (
                id SERIAL PRIMARY KEY,
                decision_id INTEGER REFERENCES trading_decisions(id),
                model_name VARCHAR(50) NOT NULL,
                vote VARCHAR(10) NOT NULL,
                confidence NUMERIC(5,4),
                reasoning TEXT,
                response_time_ms INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_votes_decision ON ensemble_votes(decision_id);
            CREATE INDEX IF NOT EXISTS idx_votes_model ON ensemble_votes(model_name);
        """)

        # =====================================================================
        # TABLE: portfolio_state
        # Tracks current portfolio state (updated after each trading cycle)
        # =====================================================================

        print("3. Creating portfolio_state table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_state (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                -- Portfolio Value
                total_value NUMERIC(12,2) NOT NULL,
                cash NUMERIC(12,2) NOT NULL,
                positions_value NUMERIC(12,2) DEFAULT 0,

                -- Current Positions (JSONB for flexibility)
                positions JSONB DEFAULT '{}',

                -- Performance Metrics
                daily_pnl NUMERIC(12,2) DEFAULT 0,
                total_pnl NUMERIC(12,2) DEFAULT 0,
                total_pnl_pct NUMERIC(8,4) DEFAULT 0,

                -- Risk Metrics
                max_drawdown NUMERIC(8,4) DEFAULT 0,
                current_drawdown NUMERIC(8,4) DEFAULT 0,

                -- Trade Statistics
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                win_rate NUMERIC(5,4) DEFAULT 0,

                -- Circuit Breaker State
                trading_halted BOOLEAN DEFAULT false,
                halt_reason TEXT
            );
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_time ON portfolio_state(timestamp DESC);
        """)

        # =====================================================================
        # TABLE: paper_trades
        # Tracks all paper trade executions (entries and exits)
        # =====================================================================

        print("4. Creating paper_trades table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id SERIAL PRIMARY KEY,
                decision_id INTEGER REFERENCES trading_decisions(id),
                token VARCHAR(20) NOT NULL,

                -- Trade Details
                side VARCHAR(10) NOT NULL,
                quantity NUMERIC(20,8) NOT NULL,
                price NUMERIC(20,8) NOT NULL,
                value_usd NUMERIC(12,2) NOT NULL,

                -- Fees (simulate realistic trading costs)
                fee_pct NUMERIC(5,4) DEFAULT 0.001,
                fee_usd NUMERIC(12,2),

                -- Timing
                executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                -- For tracking paired entry/exit
                trade_pair_id INTEGER,
                is_entry BOOLEAN,

                -- P&L (calculated on exit)
                pnl_usd NUMERIC(12,2),
                pnl_pct NUMERIC(8,4),

                -- Market context at execution
                slippage_pct NUMERIC(5,4),
                spread_pct NUMERIC(5,4)
            );
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_token ON paper_trades(token);
            CREATE INDEX IF NOT EXISTS idx_trades_time ON paper_trades(executed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_trades_decision ON paper_trades(decision_id);
        """)

        # =====================================================================
        # TABLE: circuit_breaker_events
        # Logs when circuit breakers are triggered
        # =====================================================================

        print("5. Creating circuit_breaker_events table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS circuit_breaker_events (
                id SERIAL PRIMARY KEY,
                event_type VARCHAR(50) NOT NULL,
                triggered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                reason TEXT NOT NULL,
                portfolio_value NUMERIC(12,2),
                daily_drawdown NUMERIC(8,4),
                consecutive_losses INTEGER,
                auto_resume_at TIMESTAMP WITH TIME ZONE
            );
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_breaker_time ON circuit_breaker_events(triggered_at DESC);
        """)

        conn.commit()

        print("\n[SUCCESS] All tables created successfully!\n")

        # Verify tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('trading_decisions', 'ensemble_votes',
                              'portfolio_state', 'paper_trades',
                              'circuit_breaker_events')
            ORDER BY table_name;
        """)

        tables = cursor.fetchall()
        print("Created tables:")
        for table in tables:
            print(f"  - {table[0]}")

        # Insert initial portfolio state
        print("\nInitializing portfolio state...")
        cursor.execute("""
            INSERT INTO portfolio_state (total_value, cash, positions)
            VALUES (10000.00, 10000.00, '{}')
        """)
        conn.commit()
        print("[SUCCESS] Portfolio initialized with $10,000 paper trading capital")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"[ERROR] Failed to create tables: {e}")
        raise


if __name__ == "__main__":
    create_trading_tables()
