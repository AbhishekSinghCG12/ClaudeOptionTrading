import pandas as pd
import numpy as np
from dhanhq import dhanhq , DhanContext
from datetime import datetime

# --- CONFIGURATION ---
CLIENT_ID = "1102717349"
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzc4OTUwMTQwLCJpYXQiOjE3Nzg4NjM3NDAsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTAyNzE3MzQ5In0.aBjkwZrJIQhp2xrUeiTe50WSA2Mm_HG8avFREdO34ZuLQmIrhNl-OUTGhraf_QqDUqd6RTSvLB_3C31pdMjhnQ"
NIFTY_INDEX_ID = '13' 

dhan_context = DhanContext(CLIENT_ID, ACCESS_TOKEN)
dhan = dhanhq(dhan_context)

def calculate_supertrend(df, period=10, multiplier=3):
    """Manually calculates Supertrend without external indicator libraries"""
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    # 1. Calculate True Range (TR)
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    df['TR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # 2. Calculate ATR using Simple Moving Average
    df['ATR'] = df['TR'].rolling(window=period).mean()
    
    # 3. Basic Upper and Lower Bands
    hl2 = (high + low) / 2
    df['upperband'] = hl2 + (multiplier * df['ATR'])
    df['lowerband'] = hl2 - (multiplier * df['ATR'])
    
    # 4. Final Supertrend Logic
    df['st'] = 0.0
    df['dir'] = 1 # 1 for bullish, -1 for bearish
    
    for i in range(period, len(df)):
        # Final Upper Band
        if close.iloc[i-1] <= df['upperband'].iloc[i-1]:
            df.loc[df.index[i], 'upperband'] = min(df['upperband'].iloc[i], df['upperband'].iloc[i-1])
        
        # Final Lower Band
        if close.iloc[i-1] >= df['lowerband'].iloc[i-1]:
            df.loc[df.index[i], 'lowerband'] = max(df['lowerband'].iloc[i], df['lowerband'].iloc[i-1])
        
        # Direction Logic
        if close.iloc[i] > df['upperband'].iloc[i-1]:
            df.loc[df.index[i], 'dir'] = 1
        elif close.iloc[i] < df['lowerband'].iloc[i-1]:
            df.loc[df.index[i], 'dir'] = -1
        else:
            df.loc[df.index[i], 'dir'] = df['dir'].iloc[i-1]
            
        # Set final Supertrend value
        df.loc[df.index[i], 'st'] = df['lowerband'].iloc[i] if df['dir'].iloc[i] == 1 else df['upperband'].iloc[i]
        
    return df

def run_strategy(df):
    """Executes the ORB + Manual Supertrend Logic"""
    
    # Calculate Supertrend
    df = calculate_supertrend(df)
    
    # Time formatting
    df['time'] = df['start_Time'].dt.time
    
    # 1. Identify 09:15 - 09:30 ORB
    morning_mask = (df['time'] >= datetime.strptime("09:15", "%H:%M").time()) & \
                   (df['time'] <= datetime.strptime("09:30", "%H:%M").time())
    morning_data = df[morning_mask]
    
    if morning_data.empty: return
    
    orb_high = morning_data['High'].max()
    orb_low = morning_data['Low'].min()
    
    print(f"ORB High: {orb_high} | ORB Low: {orb_low}")

    # 2. Scanning Window (Post 09:30)
    trading_window = df[df['time'] > datetime.strptime("09:30", "%H:%M").time()]
    
    for idx, row in trading_window.iterrows():
        # Condition 1: Price Crosses ORB High
        # Condition 2: Supertrend Direction is Bullish (1)
        if row['Close'] > orb_high and row['dir'] == 1:
            
            # Condition 3: Body Ratio > 0.45
            candle_range = row['High'] - row['Low']
            body_size = abs(row['Close'] - row['Open'])
            ratio = body_size / candle_range if candle_range > 0 else 0
            
            if ratio > 0.45:
                print(f"✅ BUY TRIGGER at {row['time']}")
                print(f"Price: {row['Close']} | Ratio: {ratio:.2f} | ST Line: {row['st']:.2f}")
                break

# --- DATA FETCH & RUN ---
def fetch_dhan_data(symbol_id, start, end):
    data = dhan.intraday_minute_data(
        security_id=symbol_id,
        exchange_segment="IDX_I",
        instrument_type="INDEX",
        from_date=start,
        to_date=end
    )
    
    print("API Response:", data)
    
    if data['status'] == 'success':
        df = pd.DataFrame(data['data'])
        df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'})
        df['start_Time'] = pd.to_datetime(df['start_Time'], unit='s')
        
        df.to_csv("nifty_data.csv", index=False)
        print(f"✅ Saved {len(df)} rows to nifty_data.csv")
        return df
    
    print(f"❌ API error: {data}")
    return None

if __name__ == "__main__":
    try:
        print("Script started...")
        print("Connecting to Dhan...")
        raw_df = fetch_dhan_data(NIFTY_INDEX_ID, "2026-05-14", "2026-05-15")
        print("fetch done, df:", raw_df)
        if raw_df is not None:
            run_strategy(raw_df)
    except Exception as e:
        import traceback
        print("ERROR:", e)
        traceback.print_exc()
