# AI Release Oracle

AI Release Oracle is a tracking dashboard that calculates and visualizes the predicted release dates of upcoming AI models (like GPT-5, Gemini 3.5, Claude 5) based on data from prediction markets (Polymarket).

The application uses advanced statistical analysis, including exponential decay tail extrapolation and center-of-mass integrals, to derive expected release dates and uncertainty windows from live market probabilities.

## Key Features

- **Expected Release (Mean):** The statistically weighted average release date.
- **Confidence Window (±1σ):** Displays the standard deviation timeframe, showing the range where the release is most likely to occur.
- **Days Remaining Countdown:** Real-time countdown to the expected release date for every model.
- **Historical Trends:** Track how market expectations and uncertainty (standard deviation) have shifted over time with interactive charts.
- **Days Remaining Trend Chart:** A specialized view showing how the countdown to release has evolved.
- **Interactive Timeline:** A proportional vertical timeline showing the chronological order of model releases.
- **Dynamic Configuration:** Easily add or remove markets by editing a simple text file.

## Project Structure

- `manual_prediction.py`: The core mathematical engine. It calculates the mean date, variance, and standard deviation from Polymarket API data and stores snapshots in SQLite.
- `app.py`: Flask web server serving the dashboard and providing the data API.
- `templates/index.html`: The modern, interactive frontend dashboard (Cards and Timeline views).
- `urls.txt`: Configuration file for tracked Polymarket event URLs.
- `predictions.db`: SQLite database storing historical prediction data.

## Prerequisites

- Python 3.7+
- pip

## Installation & Setup

1. **Install dependencies:**
   ```bash
   pip install Flask requests
   ```

2. **Configure tracked markets:**
   Add Polymarket event URLs to `urls.txt` (one per line).

3. **Fetch initial data:**
   Run the engine to populate the database with the first snapshot.
   ```bash
   python manual_prediction.py
   ```

4. **Start the Web Dashboard:**
   ```bash
   python app.py
   ```
   Navigate to `http://localhost:5000` to view the dashboard.

## Statistical Methodology

The engine calculates the **Mean Expected Date** and **Standard Deviation** by treating the prediction market as a probability density function. It uses:
1. **Marginal Probability Calculation:** Deriving the probability of release within specific time windows.
2. **Center of Mass Integration:** Finding the expected date within each window using local decay rates.
3. **Exponential Tail Extrapolation:** Modeling the "late release" scenario for probabilities not covered by the market's listed dates.
4. **Variance Tracking:** Calculating the second moment to provide a ±1 standard deviation confidence interval.
