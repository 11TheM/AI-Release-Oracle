import requests
import json
import os
import sqlite3
import math
from datetime import datetime, timedelta

# The base URL for Polymarket's Gamma API
POLYMARKET_API_URL = "https://gamma-api.polymarket.com"

def save_prediction_to_database(event_slug, event_title, mean_date, std_dev_days):
    """Saves the calculated prediction metrics to a local SQLite database."""
    db_path = 'predictions.db'
    if os.path.exists('/data'):
        db_path = '/data/predictions.db'
    db_connection = sqlite3.connect(db_path)
    db_cursor = db_connection.cursor()
    
    db_cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT,
            title TEXT,
            mean_date TEXT,
            std_dev_days REAL,
            calculated_at DATETIME
        )
    ''')
    
    # Check if column exists (for migration)
    db_cursor.execute("PRAGMA table_info(history)")
    columns = [column[1] for column in db_cursor.fetchall()]
    if 'std_dev_days' not in columns:
        db_cursor.execute('ALTER TABLE history ADD COLUMN std_dev_days REAL')

    db_cursor.execute('''
        INSERT INTO history (slug, title, mean_date, std_dev_days, calculated_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        event_slug, 
        event_title, 
        mean_date.strftime('%Y-%m-%d %H:%M:%S') if mean_date else None, 
        std_dev_days,
        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ))
    
    db_connection.commit()
    db_connection.close()

def fetch_polymarket_event(event_slug):
    """Fetches the full event JSON data from the Polymarket API."""
    api_endpoint = f"{POLYMARKET_API_URL}/events/slug/{event_slug}"
    api_response = requests.get(api_endpoint)
    if api_response.status_code == 200:
        return api_response.json()
    return None

def extract_event_slug_from_url(url_string):
    """Parses a standard Polymarket URL to isolate the event slug."""
    clean_url = url_string.strip().rstrip('/')
    if "/event/" in clean_url:
        return clean_url.split("/event/")[-1].split("?")[0]
    return clean_url

def calculate_window_center_of_mass(window_days, lambda_rate):
    """Calculates the center of mass (expected offset in days) for a truncated exponential window."""
    if window_days <= 0:
        return 0
    if abs(lambda_rate) < 1e-6:
        return window_days / 2.0
    try:
        offset = (1.0 / lambda_rate) - (window_days / (math.exp(lambda_rate * window_days) - 1.0))
        return max(0.0, min(window_days, offset))
    except OverflowError:
        return window_days / 2.0

def analyze_event_predictions(event_slug):
    """
    Analyzes market probabilities to project Expected (Mean) and Standard Deviation.
    """
    event_data = fetch_polymarket_event(event_slug)
    if not event_data:
        print(f"Error: Could not retrieve data for event slug '{event_slug}'")
        return

    print(f"\n{'='*65}")
    print(f"ANALYSIS: {event_data.get('title')}")
    print(f"{'='*65}")
    
    sub_markets = event_data.get('markets', [])
    extracted_market_data = []
    fallback_event_year = event_data.get('endDate', str(datetime.now().year)).split('-')[0]

    for market in sub_markets:
        best_bid = float(market.get('bestBid', 0))
        best_ask = float(market.get('bestAsk', 0))
        if best_bid > 0 and best_ask > 0:
            implied_prob = (best_bid + best_ask) / 2
        else:
            try:
                outcome_prices = json.loads(market.get('outcomePrices', '["0", "1"]'))
                implied_prob = float(outcome_prices[0])
            except ValueError: continue
            
        market_label = market.get('groupItemTitle', market.get('question', 'Unknown'))
        target_date = None
        try:
            target_date = datetime.strptime(f"{market_label} {fallback_event_year}", "%B %d %Y")
        except ValueError:
            try:
                question_text = market.get('question', '')
                date_substring = question_text.split('by ')[-1].split('?')[0].strip()
                target_date = datetime.strptime(date_substring, "%B %d, %Y")
            except ValueError:
                try:
                    target_date = datetime.strptime(market.get('endDate', '').split('T')[0], "%Y-%m-%d")
                except ValueError: continue
        
        if target_date:
            extracted_market_data.append({"date": target_date, "cumulative_probability": implied_prob, "label": market_label})

    if not extracted_market_data:
        print("Error: No valid market dates parsed.")
        return

    extracted_market_data.sort(key=lambda item: item['date'])

    analysis_start_date = datetime.now()
    period_start_date = analysis_start_date
    expected_days_sum = 0.0
    expected_days_squared_sum = 0.0
    highest_cumulative_prob = 0
    processed_windows = []

    for time_period in extracted_market_data:
        current_cumulative_prob = max(highest_cumulative_prob, time_period["cumulative_probability"])
        marginal_prob = max(0, current_cumulative_prob - highest_cumulative_prob)
        window_duration = (time_period["date"] - period_start_date).total_seconds() / 86400.0
        window_days = max(1.0, window_duration)
        daily_rate = marginal_prob / window_days

        processed_windows.append({
            "start": period_start_date, "end": time_period["date"], "days": window_days,
            "marginal_prob": marginal_prob, "daily_rate": daily_rate, "cum_prob": current_cumulative_prob
        })
        highest_cumulative_prob = current_cumulative_prob
        period_start_date = time_period["date"] + timedelta(days=1)

    for i, window in enumerate(processed_windows):
        if i > 0 and processed_windows[i-1]["daily_rate"] > 0 and window["daily_rate"] > 0:
            delta_t = (processed_windows[i-1]["days"] + window["days"]) / 2.0
            raw_lambda = math.log(processed_windows[i-1]["daily_rate"] / window["daily_rate"]) / delta_t
            local_lambda = max(-0.2, min(0.2, raw_lambda)) 
        else: local_lambda = 0.0 
            
        offset_days = calculate_window_center_of_mass(window["days"], local_lambda)
        midpoint_date = window["start"] + timedelta(days=offset_days)
        days_from_start = (midpoint_date - analysis_start_date).total_seconds() / 86400.0
        
        expected_days_sum += days_from_start * window["marginal_prob"]
        expected_days_squared_sum += (days_from_start**2) * window["marginal_prob"]

    remaining_probability_space = max(0.0, 1.0 - highest_cumulative_prob)
    latest_listed_date = extracted_market_data[-1]['date']
    probability_happens_late = 0
    tail_lambda = 0.0019

    if remaining_probability_space > 0.001 and len(processed_windows) >= 1:
        last_rate = processed_windows[-1]["daily_rate"]
        if len(processed_windows) >= 2:
            prev_rate = processed_windows[-2]["daily_rate"]
            if prev_rate > 0 and last_rate > 0 and prev_rate > last_rate:
                delta_t = (processed_windows[-2]["days"] + processed_windows[-1]["days"]) / 2.0
                raw_tail_lambda = math.log(prev_rate / last_rate) / delta_t
                tail_lambda = max(0.0001, min(0.1, raw_tail_lambda))
        
        if last_rate > 0:
            tail_start_rate = last_rate * math.exp(-tail_lambda * (processed_windows[-1]["days"] / 2.0))
            max_tail_probability = tail_start_rate / tail_lambda
            probability_happens_late = min(remaining_probability_space, max_tail_probability)
            
            if probability_happens_late < max_tail_probability and probability_happens_late > 0:
                ratio = (tail_lambda * probability_happens_late) / tail_start_rate
                w_tail = -math.log(1.0 - min(0.999999, ratio)) / tail_lambda
                expected_days_into_tail = calculate_window_center_of_mass(w_tail, tail_lambda)
                # Second moment for exponential tail is more complex but we approximate with mass center squared for simplicity in this script
            else:
                expected_days_into_tail = 1.0 / tail_lambda 
                
            late_midpoint_date = latest_listed_date + timedelta(days=expected_days_into_tail)
            days_from_start = (late_midpoint_date - analysis_start_date).total_seconds() / 86400.0
            
            expected_days_sum += days_from_start * probability_happens_late
            expected_days_squared_sum += (days_from_start**2) * probability_happens_late

    total_prob = highest_cumulative_prob + probability_happens_late
    if total_prob == 0: return

    avg_days = expected_days_sum / total_prob
    projected_mean_date = analysis_start_date + timedelta(days=avg_days)
    
    avg_days_sq = expected_days_squared_sum / total_prob
    variance = max(0, avg_days_sq - (avg_days**2))
    std_dev_days = math.sqrt(variance)

    print(f"=> Expected Date: {projected_mean_date.strftime('%B %d, %Y')}")
    print(f"=> Std Dev:      +/- {std_dev_days:.1f} days")

    save_prediction_to_database(event_slug, event_data.get('title'), projected_mean_date, std_dev_days)

if __name__ == "__main__":
    with open("urls.txt", "r") as f:
        urls = [line.strip() for line in f if line.strip()]
    for url in urls:
        analyze_event_predictions(extract_event_slug_from_url(url))
