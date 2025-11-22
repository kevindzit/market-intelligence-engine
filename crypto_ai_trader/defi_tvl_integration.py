"""
DeFi TVL Integration for AI Trader
Provides functions to fetch and analyze DeFi TVL data for trading decisions
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import json

def get_defi_tvl_signals(db_config: Dict, lookback_hours: int = 24) -> Dict:
    """
    Get DeFi TVL signals for AI trading decisions

    Returns:
        Dict with:
        - risk_indicator: Current DeFi risk level (HIGH_OUTFLOWS, MODERATE_OUTFLOWS, NEUTRAL, STRONG_INFLOWS)
        - top_gainers: Protocols with biggest TVL increases
        - top_losers: Protocols with biggest TVL decreases
        - chain_dominance: TVL distribution across chains
        - category_trends: TVL trends by DeFi category
    """
    try:
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get latest flow signals
                cur.execute("""
                    SELECT *
                    FROM defi_flow_signals
                    WHERE scraped_at > NOW() - INTERVAL '%s hours'
                    ORDER BY scraped_at DESC
                    LIMIT 1
                """, (lookback_hours,))

                flow_signal = cur.fetchone()
                if not flow_signal:
                    return None

                # Get chain TVL breakdown
                cur.execute("""
                    WITH latest_chains AS (
                        SELECT DISTINCT ON (chain_name)
                            chain_name,
                            tvl_usd,
                            scraped_at
                        FROM defi_tvl_chains
                        WHERE scraped_at > NOW() - INTERVAL '%s hours'
                        ORDER BY chain_name, scraped_at DESC
                    )
                    SELECT
                        chain_name,
                        tvl_usd,
                        tvl_usd / SUM(tvl_usd) OVER () * 100 as dominance_pct
                    FROM latest_chains
                    ORDER BY tvl_usd DESC
                """, (lookback_hours,))

                chain_data = cur.fetchall()

                # Get category trends
                cur.execute("""
                    SELECT
                        category,
                        AVG(change_1d_pct) as avg_change_1d,
                        COUNT(*) as protocol_count,
                        SUM(tvl_usd) as total_tvl
                    FROM defi_protocols
                    WHERE scraped_at > NOW() - INTERVAL '%s hours'
                        AND category IS NOT NULL
                    GROUP BY category
                    HAVING COUNT(*) >= 2
                    ORDER BY SUM(tvl_usd) DESC
                """, (lookback_hours,))

                category_trends = cur.fetchall()

                return {
                    'risk_indicator': flow_signal['risk_indicator'],
                    'top_gainers': json.loads(flow_signal['biggest_gainers']) if flow_signal['biggest_gainers'] else [],
                    'top_losers': json.loads(flow_signal['biggest_losers']) if flow_signal['biggest_losers'] else [],
                    'chain_dominance': [
                        {
                            'chain': row['chain_name'],
                            'tvl': float(row['tvl_usd']),
                            'dominance': float(row['dominance_pct'])
                        }
                        for row in chain_data
                    ],
                    'category_trends': [
                        {
                            'category': row['category'],
                            'avg_change_1d': float(row['avg_change_1d']),
                            'protocol_count': row['protocol_count'],
                            'total_tvl': float(row['total_tvl'])
                        }
                        for row in category_trends
                    ],
                    'last_updated': flow_signal['scraped_at']
                }

    except Exception as e:
        print(f"[ERROR] Failed to get DeFi TVL signals: {e}")
        return None


def get_protocol_health(db_config: Dict, protocol_name: str) -> Optional[Dict]:
    """
    Get health metrics for a specific DeFi protocol

    Returns:
        Dict with protocol TVL, changes, and risk metrics
    """
    try:
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT *
                    FROM defi_protocols
                    WHERE LOWER(protocol_name) = LOWER(%s)
                    ORDER BY scraped_at DESC
                    LIMIT 1
                """, (protocol_name,))

                protocol = cur.fetchone()
                if not protocol:
                    return None

                return {
                    'name': protocol['protocol_name'],
                    'tvl': float(protocol['tvl_usd']),
                    'change_1d': float(protocol['change_1d_pct']) if protocol['change_1d_pct'] else 0,
                    'change_7d': float(protocol['change_7d_pct']) if protocol['change_7d_pct'] else 0,
                    'category': protocol['category'],
                    'main_chain': protocol['main_chain'],
                    'market_cap': float(protocol['market_cap']) if protocol['market_cap'] else None,
                    'tvl_to_mcap': float(protocol['tvl_to_mcap_ratio']) if protocol['tvl_to_mcap_ratio'] else None,
                    'risk_level': 'HIGH' if protocol['change_1d_pct'] and protocol['change_1d_pct'] < -10 else 'NORMAL'
                }

    except Exception as e:
        print(f"[ERROR] Failed to get protocol health: {e}")
        return None


def check_defi_risk_conditions(db_config: Dict) -> Dict:
    """
    Check for high-risk DeFi conditions that should affect trading

    Returns:
        Dict with:
        - should_reduce_exposure: Boolean indicating if positions should be reduced
        - risk_level: HIGH, MODERATE, or LOW
        - reasons: List of risk factors detected
    """
    try:
        signals = get_defi_tvl_signals(db_config, lookback_hours=6)
        if not signals:
            return {'should_reduce_exposure': False, 'risk_level': 'UNKNOWN', 'reasons': []}

        reasons = []
        risk_score = 0

        # Check for massive outflows
        if signals['risk_indicator'] == 'HIGH_OUTFLOWS':
            reasons.append("Significant DeFi capital outflows detected")
            risk_score += 3
        elif signals['risk_indicator'] == 'MODERATE_OUTFLOWS':
            reasons.append("Moderate DeFi capital outflows detected")
            risk_score += 1

        # Check for protocol collapses
        for loser in signals.get('top_losers', [])[:3]:
            if loser['change_pct'] < -20:
                reasons.append(f"{loser['name']} lost {abs(loser['change_pct']):.1f}% TVL")
                risk_score += 2

        # Check for category-wide issues
        for trend in signals.get('category_trends', []):
            if trend['avg_change_1d'] < -10:
                reasons.append(f"{trend['category']} sector down {abs(trend['avg_change_1d']):.1f}%")
                risk_score += 1

        # Determine risk level
        if risk_score >= 5:
            risk_level = 'HIGH'
            should_reduce = True
        elif risk_score >= 3:
            risk_level = 'MODERATE'
            should_reduce = False
        else:
            risk_level = 'LOW'
            should_reduce = False

        return {
            'should_reduce_exposure': should_reduce,
            'risk_level': risk_level,
            'reasons': reasons,
            'risk_score': risk_score
        }

    except Exception as e:
        print(f"[ERROR] Failed to check DeFi risk conditions: {e}")
        return {'should_reduce_exposure': False, 'risk_level': 'UNKNOWN', 'reasons': []}