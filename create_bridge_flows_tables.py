"""
Create Bridge Flows Database Tables
Run this to set up the bridge flows schema in PostgreSQL
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Database config
db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '54594'),
    'database': os.getenv('DB_NAME', 'pjx'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD')
}

print('[Creating Bridge Flows Database Schema]')
print('='*60)

try:
    # Connect to database
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    # Read and execute the schema file
    with open('data/bridge_flows_schema.sql', 'r') as f:
        sql = f.read()

    # Execute the SQL
    cur.execute(sql)
    conn.commit()

    print('[OK] All tables, views, and functions created successfully')

    # Verify tables exist
    tables = ['bridge_flows', 'bridge_flow_signals']
    for table in tables:
        cur.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = '{table}'
            )
        """)
        exists = cur.fetchone()[0]
        if exists:
            print(f'  [OK] Table {table} created')
        else:
            print(f'  [FAIL] Table {table} not found')

    # Verify views exist
    views = ['bridge_flows_latest', 'bridge_flows_7d', 'l2_rotation_rankings']
    for view in views:
        cur.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.views
                WHERE table_name = '{view}'
            )
        """)
        exists = cur.fetchone()[0]
        if exists:
            print(f'  [OK] View {view} created')
        else:
            print(f'  [FAIL] View {view} not found')

    print('\n[SUCCESS] Bridge flows schema ready for use!')

    cur.close()
    conn.close()

except Exception as e:
    print(f'[ERROR] Failed to create schema: {e}')
    if 'conn' in locals():
        conn.rollback()
        conn.close()