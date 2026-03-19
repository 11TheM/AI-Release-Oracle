from flask import Flask, render_template, jsonify
import os
import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

def get_db_connection():
    # Use DATABASE_URL from environment
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        return None
    
    # Handle potentially old postgres:// prefix
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    return conn

def extract_event_slug_from_url(url_string):
    clean_url = url_string.strip().rstrip('/')
    if "/event/" in clean_url:
        return clean_url.split("/event/")[-1].split("?")[0]
    return clean_url

def get_active_slugs():
    if not os.path.exists("urls.txt"): return set()
    with open("urls.txt", "r") as f:
        urls = [line.strip() for line in f if line.strip()]
    return {extract_event_slug_from_url(url) for url in urls}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    active_slugs = get_active_slugs()
    conn = get_db_connection()
    
    if not conn:
        return jsonify({
            'data': {},
            'error': 'DATABASE_URL not set in environment',
            'debug': {'db_path_used': 'POSTGRES'}
        })
    
    with conn:
        with conn.cursor() as cur:
            # Ensure table exists
            cur.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id SERIAL PRIMARY KEY,
                    slug TEXT,
                    title TEXT,
                    mean_date TEXT,
                    std_dev_days REAL,
                    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            try:
                cur.execute('SELECT slug, title, mean_date, std_dev_days, calculated_at FROM history ORDER BY calculated_at DESC')
                rows = cur.fetchall()
            except Exception:
                rows = []
    conn.close()
    
    last_updated = None
    data_by_slug = {}
    
    for row in rows:
        slug = row['slug']
        
        # Capture the most recent timestamp
        if last_updated is None:
            # Convert timestamp to string if it is a datetime object
            if isinstance(row['calculated_at'], datetime.datetime):
                last_updated = row['calculated_at'].isoformat()
            else:
                last_updated = str(row['calculated_at'])
            
        if slug not in data_by_slug:
            data_by_slug[slug] = {'title': row['title'], 'history': []}
        
        data_by_slug[slug]['history'].append({
            'x': row['calculated_at'].isoformat() if isinstance(row['calculated_at'], datetime.datetime) else str(row['calculated_at']),
            'y_mean': row['mean_date'],
            'y_std_dev': row['std_dev_days']
        })
    
    # Reverse history for each slug so charts go left-to-right (chronological)
    for slug in data_by_slug:
        data_by_slug[slug]['history'].reverse()
    
    return jsonify({
        'data': data_by_slug,
        'last_updated': last_updated,
        'debug': {
            'db_type': 'POSTGRESQL',
            'db_row_count': len(rows),
            'active_slugs_count': len(active_slugs)
        }
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)

