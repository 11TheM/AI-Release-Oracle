from flask import Flask, render_template, jsonify
import sqlite3
import os

app = Flask(__name__)

def get_db_connection():
    db_path = 'predictions.db'
    if os.path.exists('/data'):
        db_path = '/data/predictions.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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
    
    # Ensure table exists
    conn.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT,
            title TEXT,
            mean_date TEXT,
            std_dev_days REAL,
            calculated_at DATETIME
        )
    ''')
    
    try:
        rows = conn.execute('SELECT slug, title, mean_date, std_dev_days, calculated_at FROM history ORDER BY calculated_at ASC').fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    
    last_updated = None
    data_by_slug = {}
    for row in rows:
        slug = row['slug']
        # If we have active slugs, filter by them. Otherwise, show everything found.
        if active_slugs and slug not in active_slugs: continue
        
        last_updated = row['calculated_at']
            
        if slug not in data_by_slug:
            data_by_slug[slug] = {'title': row['title'], 'history': []}
        
        data_by_slug[slug]['history'].append({
            'x': row['calculated_at'],
            'y_mean': row['mean_date'],
            'y_std_dev': row['std_dev_days']
        })
    
    return jsonify({
        'data': data_by_slug,
        'last_updated': last_updated,
        'debug': {
            'db_row_count': len(rows),
            'active_slugs_count': len(active_slugs),
            'filtered_slugs_count': len(data_by_slug)
        }
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
