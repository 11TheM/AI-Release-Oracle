from flask import Flask, render_template, jsonify
import sqlite3
import os

app = Flask(__name__)

def get_db_connection():
    # Priority: /data/predictions.db for shared Runway volume
    # Fallback: local predictions.db for local development
    db_path = 'predictions.db'
    
    # Check if /data exists and is writable
    if os.path.isdir('/data'):
        db_path = '/data/predictions.db'
        # Ensure the file exists so we don't hit read-only errors later
        if not os.path.exists(db_path):
            try:
                open(db_path, 'a').close()
            except Exception as e:
                print(f"Warning: Could not touch {db_path}: {e}")
                db_path = 'predictions.db' # Revert to local if /data is read-only
                
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
    
    db_path = 'predictions.db'
    if os.path.isdir('/data'):
        db_path = '/data/predictions.db'
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
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
        rows = conn.execute('SELECT slug, title, mean_date, std_dev_days, calculated_at FROM history ORDER BY calculated_at DESC').fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    
    last_updated = None
    data_by_slug = {}
    
    # If urls.txt is empty or missing, we'll show all data. 
    # Otherwise, we'll use it as a priority list.
    for row in rows:
        slug = row['slug']
        
        # Capture the most recent timestamp
        if last_updated is None:
            last_updated = row['calculated_at']
            
        if slug not in data_by_slug:
            data_by_slug[slug] = {'title': row['title'], 'history': []}
        
        data_by_slug[slug]['history'].append({
            'x': row['calculated_at'],
            'y_mean': row['mean_date'],
            'y_std_dev': row['std_dev_days']
        })
    
    # Final check: If after filtering by active_slugs we have nothing, 
    # but the DB HAD rows, we should show them anyway to avoid a blank screen.
    if rows and not data_by_slug:
        # Re-run without filtering if the filter killed all results
        for row in rows:
            slug = row['slug']
            if slug not in data_by_slug:
                data_by_slug[slug] = {'title': row['title'], 'history': []}
            data_by_slug[slug]['history'].append({
                'x': row['calculated_at'],
                'y_mean': row['mean_date'],
                'y_std_dev': row['std_dev_days']
            })
    
    # Reverse history for each slug so charts go left-to-right (chronological)
    for slug in data_by_slug:
        data_by_slug[slug]['history'].reverse()
    
    # Get file lists for debugging
    local_files = os.listdir('.') if os.path.exists('.') else []
    data_files = os.listdir('/data') if os.path.isdir('/data') else ["/data is not a directory"]
    
    return jsonify({
        'data': data_by_slug,
        'last_updated': last_updated,
        'debug': {
            'db_path_used': os.path.abspath(db_path),
            'db_file_exists': os.path.exists(db_path),
            'db_row_count': len(rows),
            'active_slugs_count': len(active_slugs),
            'active_slugs_list': list(active_slugs),
            'local_directory_contents': local_files,
            'data_directory_contents': data_files
        }
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
