
import pandas as pd
from datetime import datetime, timezone
import os
import sys

# Mock common dependencies
sys.path.append(os.getcwd())
from data_sync import get_gap_info

print("=== Starting Manual Test of Gap Logic ===")

# Test 1: Random data with NaN at the end
data_nan = {
    'time': [pd.Timestamp('2026-03-24 10:00:00', tz='UTC'), pd.NaT],
    'close': [2100.0, 2101.0]
}
df_nan = pd.DataFrame(data_nan)
print(f"\n1. Testing with NaT at the end...")
gap_nan = get_gap_info(df_nan)
print(f"Result: {gap_nan}")

# Test 2: Normal data
data_ok = {
    'time': [pd.Timestamp('2026-03-24 10:00:00', tz='UTC'), pd.Timestamp('2026-03-25 10:00:00', tz='UTC')],
    'close': [2100.0, 2101.0]
}
df_ok = pd.DataFrame(data_ok)
print(f"\n2. Testing with Normal data (24h ago)...")
gap_ok = get_gap_info(df_ok)
print(f"Result: {gap_ok}")

# Test 3: Empty data
print(f"\n3. Testing with Empty DataFrame...")
gap_empty = get_gap_info(pd.DataFrame())
print(f"Result: {gap_empty}")

print("\n=== Test Finished ===")
