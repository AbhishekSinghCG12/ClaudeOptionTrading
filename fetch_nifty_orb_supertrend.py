import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ==============================
# CONFIG
# ==============================
TICKER = "^NSEI"   # Nifty 50

# Yahoo Finance restricts 5-minute intraday data to the last 60 days ONLY.
# We cap the start date automatically so the script never breaks.
MAX_INTRADAY_DAYS = 59
END_DATE = datetime.today().strftime('%Y-%m-%d')
START_DATE = (datetime.today() - timedelta(days=MAX_INTRADAY_DAYS)).strftime('%Y-%m-%d')

INTERVAL = "5m"    # 5-minute candles for ORB
ATR_PERIOD = 10
SUPER_MULTIPLIER = 3
ORB_CANDLES = 3    # first 15 mins (3 x 5min candles)

OUTPUT_FILE = "nifty50_supertrend_orb_2026.csv"

print(f"Fetching {INTERVAL} data from {START_DATE} to {END_DATE}  (max 60-day window)")

# ==============================
# FETCH DATA
# ==============================
df = yf.download(
    TICKER,
    start=START_DATE,
    end=END_DATE,
    interval=INTERVAL,
    auto_adjust=True,
    progress=False
)

if df.empty:
    raise Exception(
        "No data fetched. Possible reasons:\n"
        "  1. Yahoo Finance API is temporarily unavailable.\n"
        "  2. The ticker '^NSEI' is not supported for intraday data in your region.\n"
        "  Try '^NSEBANK' or 'RELIANCE.NS' to verify connectivity."
    )

df.reset_index(inplace=True)

# Flatten MultiIndex columns if present (yfinance ≥ 0.2.x quirk)
if isinstance(df.columns, pd.MultiIndex):
    df.columns = ['_'.join(filter(None, col)).strip() for col in df.columns]

# Standardize column names to lowercase
df.columns = [col.lower().split('_')[0] if '_' in col else col.lower() for col in df.columns]

# Rename 'datetime' or 'date' column to 'datetime'
time_col = next((c for c in df.columns if c in ('datetime', 'date', 'timestamp')), None)
if time_col and time_col != 'datetime':
    df.rename(columns={time_col: 'datetime'}, inplace=True)

print(f"Columns after normalisation: {list(df.columns)}")
print(f"Rows fetched: {len(df)}")

# ==============================
# ATR Calculation
# ==============================
df['prev_close'] = df['close'].shift(1)

df['tr1'] = df['high'] - df['low']
df['tr2'] = (df['high'] - df['prev_close']).abs()
df['tr3'] = (df['low']  - df['prev_close']).abs()

df['tr']  = df[['tr1', 'tr2', 'tr3']].max(axis=1)
df['atr'] = df['tr'].rolling(ATR_PERIOD).mean()

# ==============================
# SUPERTREND
# ==============================
hl2 = (df['high'] + df['low']) / 2

df['upperband'] = hl2 + (SUPER_MULTIPLIER * df['atr'])
df['lowerband'] = hl2 - (SUPER_MULTIPLIER * df['atr'])

supertrend = [True] * len(df)

for i in range(1, len(df)):
    if df['close'].iloc[i] > df['upperband'].iloc[i - 1]:
        supertrend[i] = True
    elif df['close'].iloc[i] < df['lowerband'].iloc[i - 1]:
        supertrend[i] = False
    else:
        supertrend[i] = supertrend[i - 1]

        if supertrend[i] and df['lowerband'].iloc[i] < df['lowerband'].iloc[i - 1]:
            df.loc[df.index[i], 'lowerband'] = df['lowerband'].iloc[i - 1]

        if not supertrend[i] and df['upperband'].iloc[i] > df['upperband'].iloc[i - 1]:
            df.loc[df.index[i], 'upperband'] = df['upperband'].iloc[i - 1]

df['supertrend'] = np.where(supertrend, df['lowerband'], df['upperband'])
df['trend']      = np.where(supertrend, 'Bullish', 'Bearish')

# ==============================
# ORB CALCULATION
# ==============================
df['date_only'] = pd.to_datetime(df['datetime']).dt.date

for day in df['date_only'].unique():
    day_mask = df['date_only'] == day
    day_data  = df[day_mask]

    if len(day_data) < ORB_CANDLES:
        continue

    orb_range = day_data.iloc[:ORB_CANDLES]
    df.loc[day_mask, 'orb_high'] = orb_range['high'].max()
    df.loc[day_mask, 'orb_low']  = orb_range['low'].min()

# ==============================
# SIGNALS
# ==============================
df['buy_signal'] = (
    (df['close'] > df['orb_high']) &
    (df['trend'] == 'Bullish')
)

df['sell_signal'] = (
    (df['close'] < df['orb_low']) &
    (df['trend'] == 'Bearish')
)

# ==============================
# CLEANUP & SAVE
# ==============================
final_cols = [
    'datetime', 'open', 'high', 'low', 'close', 'volume',
    'atr', 'supertrend', 'trend',
    'orb_high', 'orb_low',
    'buy_signal', 'sell_signal'
]

# Keep only columns that actually exist (safety guard)
final_cols = [c for c in final_cols if c in df.columns]
df_final = df[final_cols]

df_final.to_csv(OUTPUT_FILE, index=False)

buy_count  = df_final['buy_signal'].sum()
sell_count = df_final['sell_signal'].sum()

print(f"\nCSV saved: {OUTPUT_FILE}")
print(f"Rows      : {len(df_final)}")
print(f"Buy signals : {buy_count}")
print(f"Sell signals: {sell_count}")