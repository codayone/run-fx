import requests
from datetime import datetime
import pytz
import pandas as pd
import os
import smtplib
from email.mime.text import MIMEText
from io import StringIO
import urllib.request

print("Script started ✅")

# =========================
# CONFIG - ONLY EDIT HERE
# =========================
BASE_CURRENCY = "USD"
# ============================================
# BENCHMARK CONFIG
# ============================================
LOAN_BENCHMARKS = [
    {"loan_id": "THB_1", "currency": "THB", "benchmark": "3M Compound O/N THOR", "fetch_key": "THOR_3M"},
    {"loan_id": "MYR_1", "currency": "MYR", "benchmark": "3M KLIBOR", "fetch_key": "KLIBOR_3M"},
    {"loan_id": "USD_1", "currency": "USD", "benchmark": "3M Compound O/N SOFR", "fetch_key": "SOFR_3M_COMPOUNDED"},
    {"loan_id": "HKD_1", "currency": "HKD", "benchmark": "3M HIBOR", "fetch_key": "HIBOR_3M"},
    {"loan_id": "HKD_2", "currency": "HKD", "benchmark": "3M HIBOR", "fetch_key": "HIBOR_3M"},
    {"loan_id": "HKD_3", "currency": "HKD", "benchmark": "3M HIBOR", "fetch_key": "HIBOR_3M"},
    {"loan_id": "IDR_1", "currency": "IDR", "benchmark": "3M Compound O/N INDONIA", "fetch_key": "INDONIA_3M_COMPOUNDED"},
    {"loan_id": "SGD_1", "currency": "SGD", "benchmark": "1M SORA", "fetch_key": "SORA_1M"},
    {"loan_id": "JPY_1", "currency": "JPY", "benchmark": "3M TIBOR", "fetch_key": "TIBOR_3M"},
    {"loan_id": "EUR_1", "currency": "EUR", "benchmark": "3M EURIBOR", "fetch_key": "EURIBOR_3M"},
]
CURRENCIES = list(set([
    x["currency"]
    for x in LOAN_BENCHMARKS
    if not (x["currency"] == "EUR" and "Fixed" in x["benchmark"])
]))

# loan_id can be whatever name you want for each facility/loan
FX_ALERT_THRESHOLD = 0.005    # 0.5%
BENCHMARK_ALERT_THRESHOLD = 0.01   # 0.01 percentage point = 1 bp

# unique benchmark labels for reporting
BENCHMARK_LABELS = {}
for item in LOAN_BENCHMARKS:
    BENCHMARK_LABELS.setdefault(
        item["fetch_key"],
        f'{item["currency"]} - {item["benchmark"]}'
    )

EMAIL_TO = "tangsuancoco.tan@dayonedc.com"
EMAIL_FROM_DISPLAY = "FX Bot <tangsuancoco.tan@dayonedc.com>"
CSV_FILE = "market_data.csv"

# =========================
# 1) FX FROM API (DYNAMIC)
# =========================
currency_str = ",".join(CURRENCIES)
url = f"https://api.frankfurter.app/latest?from={BASE_CURRENCY}&to={currency_str}"

response = requests.get(url, timeout=30)
response.raise_for_status()
data = response.json()

print("API response:", data)

current_rates = data["rates"]
current_rates[BASE_CURRENCY] = 1.0

for ccy in CURRENCIES:
    print(f"{BASE_CURRENCY} → {ccy}: {current_rates[ccy]}")


import requests
import pandas as pd
from io import StringIO


# ============================================
# HELPER
# ============================================
def get_html_tables(url):
    html = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    ).text

    try:
        return pd.read_html(StringIO(html))
    except ValueError:
        return []

# ============================================
# FETCHERS
# ============================================
def fetch_thor_3m():
    """
    Fetch latest 3M THOR Average from BOT CSV download endpoint.
    Source:
    https://app.bot.or.th/BTWS_STAT/statistics/DownloadFile.aspx?file=FM_RT_013_ENG_ALL.CSV
    """

    import re

    url = "https://app.bot.or.th/BTWS_STAT/statistics/DownloadFile.aspx?file=FM_RT_013_ENG_ALL.CSV"
    headers = {"User-Agent": "Mozilla/5.0"}

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    text = resp.text

    # Read raw lines instead of pandas.read_csv
    lines = text.splitlines()

    # Find the line that contains "3 Months"
    target_line = None
    for line in lines:
        if "3 Months" in line:
            target_line = line
            break

    if target_line is None:
        raise Exception("Could not find '3 Months' row in THOR CSV.")

    print("THOR 3M raw line found:", target_line[:200])  # debug only

    # Extract decimal numbers from the row
    nums = re.findall(r"([0-9]+\.[0-9]+)", target_line)

    if not nums:
        raise Exception("Could not extract numeric values from THOR 3M row.")

    # Latest value should be the last numeric item in the row
    return float(nums[-1])

def fetch_klibor_3m():
    """
    Fetch latest 3M KLIBOR from BNM FMIP page.

    The visible page layout is:
    Date | 1M | 2M | 3M | 6M | 9M | 12M
    Example shown on page:
    15/06/2026  3.00  -  3.36  3.39  -  -
    """

    import re

    url = "https://financialmarkets.bnm.gov.my/data-download-klibor"
    headers = {"User-Agent": "Mozilla/5.0"}

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    html = resp.text

    # Remove HTML tags first
    text = re.sub(r"<[^>]+>", " ", html)

    # Decode common HTML spaces and normalize whitespace
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text).strip()

    # Find all data rows in the form:
    # dd/mm/yyyy 1M 2M 3M 6M 9M 12M
    rows = re.findall(
        r"(\d{2}/\d{2}/\d{4})\s+([0-9.]+|-)\s+([0-9.]+|-)\s+([0-9.]+|-)\s+([0-9.]+|-)\s+([0-9.]+|-)\s+([0-9.]+|-)",
        text
    )

    if not rows:
        raise Exception("Could not find latest KLIBOR row.")

    # First row on page is latest date
    row_date, val_1m, val_2m, val_3m, val_6m, val_9m, val_12m = rows[0]

    print(
        f"KLIBOR raw row: {row_date} | "
        f"1M={val_1m} | 2M={val_2m} | 3M={val_3m} | "
        f"6M={val_6m} | 9M={val_9m} | 12M={val_12m}"
    )

    if val_3m == "-":
        raise Exception("Latest 3M KLIBOR is '-' on source page.")

    return float(val_3m)

def fetch_sofr_3m_compounded():
    import requests
    import pandas as pd
    from io import BytesIO

    url = "https://markets.newyorkfed.org/read?productCode=50&eventCodes=525&limit=25&startPosition=0&sort=postDt:-1&format=xlsx"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()

        df = pd.read_excel(BytesIO(resp.content))

        # find 90-day column
        col = None
        for c in df.columns:
            if "90" in str(c).upper():
                col = c
                break

        if col is None:
            print("⚠️ 90-day column not found")
            return None

        value = float(df.iloc[0][col])

        print(f"✅ SOFR from NY Fed XLSX: {value}")
        return value

    except Exception as e:
        print(f"⚠️ SOFR XLSX failed: {e}")
        return None

def fetch_hibor_3m():
    import requests
    import pandas as pd

    url = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily?segment=hibor.fixing"

    resp = requests.get(url, timeout=30)

    # ✅ Check response first
    if resp.status_code != 200:
        raise Exception(f"HKMA API failed: {resp.status_code}")

    # ✅ Try parse JSON safely
    try:
        data = resp.json()
    except Exception:
        raise Exception("HKMA API returned non-JSON response")

    # ✅ Handle structure safely
    records = None
    if isinstance(data, dict):
        if "result" in data and isinstance(data["result"], dict):
            records = data["result"].get("records")
        else:
            records = data.get("records")

    if not records:
        raise Exception("No records found in HKMA API")

    df = pd.DataFrame(records)

    # ✅ Make sure column exists
    if "ir_3m" not in df.columns:
        raise Exception("ir_3m column missing")

    df["ir_3m"] = pd.to_numeric(df["ir_3m"], errors="coerce")
    df = df.dropna(subset=["ir_3m"])

    if df.empty:
        raise Exception("No valid HIBOR values")

    return float(df.iloc[0]["ir_3m"])


def fetch_sora_1m():
    """
    Fetch latest 1M Compounded SORA from a public page that displays
    MAS-sourced daily domestic interest rates in a simple text layout.
    """

    import re

    url = "https://straitsdata.com/finance/mas"
    headers = {"User-Agent": "Mozilla/5.0"}

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    html = resp.text

    # Strip HTML tags and normalize spaces
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text).strip()

    # Try the summary block first:
    # "1M Compounded SORA 0.0059% 1.0386% 1-month compounded"
    m = re.search(
        r"1M Compounded SORA\s+[+-]?[0-9.]+%\s+([0-9.]+)%",
        text,
        flags=re.IGNORECASE
    )
    if m:
        value = float(m.group(1))
        print(f"SORA 1M summary raw: {value}")
        return value

    # Fallback: first visible daily row in the historical block:
    # "Sun, 14 Jun 2026 1.0038% -16.5 bp 1.0386% 1.0864% 1.0910% ..."
    m = re.search(
        r"[A-Z][a-z]{2},\s+\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}\s+[0-9.]+%\s+[+-]?[0-9.]+\s+bp\s+([0-9.]+)%",
        text
    )
    if m:
        value = float(m.group(1))
        print(f"SORA 1M row raw: {value}")
        return value

    raise Exception("Could not fetch 1M SORA.")


def fetch_euribor_3m():

    import pandas as pd
    from io import StringIO

    url = (
        "https://data-api.ecb.europa.eu/service/data/"
        "FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA"
        "?lastNObservations=1&detail=dataonly&format=csvdata"
    )

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text))

    # Normalize columns
    df.columns = [col.strip().upper() for col in df.columns]

    if "OBS_VALUE" not in df.columns:
        raise Exception(f"ECB EURIBOR response missing OBS_VALUE. Columns: {df.columns.tolist()}")

    df = df.dropna(subset=["OBS_VALUE"])

    if df.empty:
        raise Exception("No valid EURIBOR data returned by ECB API.")

    latest_row = df.iloc[-1]

    date = latest_row["TIME_PERIOD"] if "TIME_PERIOD" in df.columns else "N/A"
    value = latest_row["OBS_VALUE"]

    print(f"EURIBOR 3M raw: {date} {value}")

    return float(value)

def fetch_tibor_3m():
    url = "https://cio.cimb.com/ticker/interest_rates-bondapac-jptibor-03m-198200/snapshots"
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30).text

    # Simple regex fallback because pages like this often render a "Last: X.XXXX"
    import re
    m = re.search(r"Last:\s*([0-9]+\.[0-9]+)", html, flags=re.IGNORECASE)
    if m:
        return float(m.group(1))

    # Fallback to read_html if page exposes tables
    tables = pd.read_html(StringIO(html))
    for tbl in tables:
        for col in tbl.columns:
            temp = tbl[col].astype(str)
            hit = temp.str.extract(r"([0-9]+\.[0-9]+)")
            if hit.notna().any().any():
                return float(hit.dropna().iloc[0, 0])

    raise Exception("Could not fetch 3M TIBOR from CIMB page.")

def fetch_indonia_3m_compounded():
    """
    Fetch IDR - 3M Compound O/N INDONIA directly from Bank Indonesia
    using a real browser (Selenium), so you don't need your own
    history file and you don't need to wait to build 90 days of data.

    Returns:
        float or None
    """

    import re
    import time
    import pandas as pd
    from io import StringIO

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    urls = [
        # current page with latest published values
        "https://www.bi.go.id/en/fungsi-utama/moneter/indonia-jibor/default.aspx#floating-1",

        # historical compounded page
        "https://www.bi.go.id/en/statistik/indikator/Historis-Compounded-IndONIA-Index.aspx",

        # Indonesian historical page
        "https://www.bi.go.id/id/statistik/indikator/Historis-Compounded-IndONIA-Index.aspx",
    ]

    def setup_driver():
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=en-US")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        )

        # In GitHub Actions ubuntu runners, chromedriver is usually already available.
        # If yours needs an explicit path, replace Service() with Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=Service(), options=options)
        return driver

    def extract_90_from_tables(html):
        try:
            tables = pd.read_html(StringIO(html))
        except Exception:
            tables = []

        # 1) Try normal table parsing
        for df in tables:
            try:
                temp = df.copy()
                temp.columns = [str(c).strip() for c in temp.columns]

                # Case A: "90 Days (%)" exists as a column
                for col in temp.columns:
                    if "90" in str(col).lower() and "day" in str(col).lower():
                        vals = pd.to_numeric(temp[col], errors="coerce").dropna()
                        vals = vals[(vals > 0) & (vals < 20)]
                        if not vals.empty:
                            return float(vals.iloc[0])

                # Case B: header row embedded in first row
                # search row text for "90 Days"
                for i in range(len(temp)):
                    row_text = " | ".join(map(str, temp.iloc[i].tolist()))
                    if "90 Days" in row_text or "90 days" in row_text:
                        # look a few rows after it for rates
                        for j in range(i + 1, min(i + 4, len(temp))):
                            nums = pd.to_numeric(temp.iloc[j], errors="coerce").dropna()
                            nums = nums[(nums > 0) & (nums < 20)]
                            if len(nums) >= 2:
                                # usually row is: 30D, 90D, 180D, 360D, Index
                                # second numeric should be 90D
                                return float(nums.iloc[1])
                            elif len(nums) == 1:
                                return float(nums.iloc[0])
            except Exception:
                pass

        # 2) Regex fallback from page source near "90 Days"
        # This is useful when the page is rendered visually but pandas doesn't build clean tables.
        patterns = [
            r"90\s*Days\s*\(%\).*?([0-9]+\.[0-9]+)",
            r"90\s*Days.*?([0-9]+\.[0-9]+)",
        ]
        for pat in patterns:
            m = re.search(pat, html, flags=re.IGNORECASE | re.DOTALL)
            if m:
                val = float(m.group(1))
                if 0 < val < 20:
                    return val

        return None

    driver = None
    try:
        driver = setup_driver()

        for url in urls:
            try:
                print(f"🔎 Trying INDONIA page: {url}")
                driver.get(url)

                WebDriverWait(driver, 25).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )

                # let BI scripts render
                time.sleep(5)

                html = driver.page_source

                # quick block detection
                blocked_signals = [
                    "Access Denied",
                    "Request failed",
                    "challenge",
                    "Just a moment",
                    "RemoteDisconnected",
                ]
                if any(x.lower() in html.lower() for x in blocked_signals):
                    print(f"⚠️ Page looks blocked or incomplete: {url}")
                    continue

                value = extract_90_from_tables(html)
                if value is not None:
                    print(f"✅ INDONIA 3M compounded (90 Days) from BI: {value}")
                    return value

                print(f"⚠️ Could not parse 90 Days value from: {url}")

            except Exception as e:
                print(f"⚠️ Failed on {url}: {e}")

    except Exception as e:
        print(f"⚠️ Selenium setup failed: {e}")

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    print("❌ INDONIA 3M compounded not found")
    return None
        
def fetch_benchmark_rates():
    rates = {}

    fetchers = {
        "THOR_3M": fetch_thor_3m,
        "KLIBOR_3M": fetch_klibor_3m,
        "SOFR_3M_COMPOUNDED": fetch_sofr_3m_compounded,
        "HIBOR_3M": fetch_hibor_3m,
        "SORA_1M": fetch_sora_1m,
        "TIBOR_3M": fetch_tibor_3m,
        "EURIBOR_3M": fetch_euribor_3m,
        "INDONIA_3M_COMPOUNDED": fetch_indonia_3m_compounded,
    }

    for key, func in fetchers.items():
        try:
            rates[key] = func()
        except Exception as e:
            print(f"⚠️ {key} failed: {e}")
            rates[key] = None

    return rates

# ============================================
# BUILD LOAN RATE TABLE
# ============================================
benchmark_rates = fetch_benchmark_rates()

loan_rows = []
for item in LOAN_BENCHMARKS:
    rate_value = benchmark_rates.get(item["fetch_key"])
    loan_rows.append({
        "Loan_ID": item["loan_id"],
        "Currency": item["currency"],
        "Loan_Benchmark_Rate": item["benchmark"],
        "Benchmark_Value": rate_value
    })

loan_df = pd.DataFrame(loan_rows)

print("=== Loan Benchmark Rates ===")
print(loan_df)


# =========================
# 3) TIMEZONE
# =========================
sgt = pytz.timezone("Asia/Singapore")
now = datetime.now(sgt)

# =========================
# 4) BUILD NEW ROW
# =========================
new_row = {
    "Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
}

# FX rates
for ccy in CURRENCIES:
    new_row[f"{BASE_CURRENCY}_{ccy}"] = current_rates[ccy]

# Benchmark rates
for key, value in benchmark_rates.items():
    new_row[f"BM_{key}"] = value

new_data = pd.DataFrame([new_row])


# =========================
# 5) LOAD EXISTING DATA
# =========================
if os.path.exists(CSV_FILE):
    df = pd.read_csv(CSV_FILE)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
else:
    base_columns = ["Timestamp"] + [
        f"{BASE_CURRENCY}_{ccy}" for ccy in CURRENCIES
    ] + [
        f"BM_{key}" for key in BENCHMARK_LABELS.keys()
    ]
    df = pd.DataFrame(columns=base_columns)

# ensure FX columns exist
for ccy in CURRENCIES:
    col = f"{BASE_CURRENCY}_{ccy}"
    if col not in df.columns:
        df[col] = pd.NA

# ensure Benchmark columns exist
for key in BENCHMARK_LABELS.keys():
    col = f"BM_{key}"
    if col not in df.columns:
        df[col] = pd.NA

df = df.sort_values("Timestamp")

# =========================
# 6) CALCULATE CHANGES VS LAST RUN
# =========================
previous_rates = {}
changes = {}

previous_benchmark_rates = {}
benchmark_changes = {}

if not df.empty:
    last_row = df.iloc[-1]

    # FX changes
    for ccy in CURRENCIES:
        col = f"{BASE_CURRENCY}_{ccy}"
        prev_value = last_row[col]

        if pd.notna(prev_value) and float(prev_value) != 0:
            prev_value = float(prev_value)
            previous_rates[ccy] = prev_value
            changes[ccy] = (float(current_rates[ccy]) - prev_value) / prev_value
        else:
            previous_rates[ccy] = float(current_rates[ccy])
            changes[ccy] = 0.0

    # Benchmark changes
    for key in BENCHMARK_LABELS.keys():
        col = f"BM_{key}"
        prev_raw = last_row[col] if col in last_row.index else pd.NA
        curr_raw = benchmark_rates.get(key)

        if pd.notna(prev_raw):
            previous_benchmark_rates[key] = float(prev_raw)
        else:
            previous_benchmark_rates[key] = None

        if curr_raw is None or pd.isna(curr_raw) or pd.isna(prev_raw):
            benchmark_changes[key] = None
        else:
            benchmark_changes[key] = float(curr_raw) - float(prev_raw)

else:
    for ccy in CURRENCIES:
        previous_rates[ccy] = float(current_rates[ccy])
        changes[ccy] = 0.0

    for key in BENCHMARK_LABELS.keys():
        previous_benchmark_rates[key] = None
        benchmark_changes[key] = None


# =========================
# 7) APPEND + SAVE CSV
# =========================
df = pd.concat([df, new_data], ignore_index=True)
df.to_csv(CSV_FILE, index=False)

print("Saved to CSV ✅")
print(df.tail())


# =========================
# 8) PRINT SUMMARY
# =========================
for ccy in CURRENCIES:
    change_pct = changes[ccy] * 100
    if change_pct > 0:
        arrow = "▲"
    elif change_pct < 0:
        arrow = "▼"
    else:
        arrow = "➜"

    print(f"{BASE_CURRENCY}/{ccy} Previous:", previous_rates[ccy])
    print(f"{BASE_CURRENCY}/{ccy} Current:", current_rates[ccy])
    print(f"{BASE_CURRENCY}/{ccy} Change:", f"{arrow} {change_pct:.4f}%")

print("=== Benchmark Summary ===")
for key, label in BENCHMARK_LABELS.items():
    curr = benchmark_rates.get(key)
    prev = previous_benchmark_rates.get(key)
    diff = benchmark_changes.get(key)

    curr_txt = "N/A" if curr is None or pd.isna(curr) else f"{float(curr):.5f}%"
    prev_txt = "N/A" if prev is None or pd.isna(prev) else f"{float(prev):.5f}%"

    if diff is None:
        diff_txt = "N/A"
    else:
        direction = "▲" if diff > 0 else "▼" if diff < 0 else "➜"
        diff_txt = f"{direction} {abs(diff)*100:.2f} bps"

    print(f"{label} | Previous: {prev_txt} | Current: {curr_txt} | Change: {diff_txt}")


# =========================
# 9) SEND EMAIL
# =========================
def send_email(current_rates, previous_rates, changes,
               current_benchmark_rates, previous_benchmark_rates, benchmark_changes,
               currencies, base_currency):

    fx_rows = ""
    
    for ccy in currencies:
        curr = float(current_rates[ccy])
        prev = float(previous_rates.get(ccy, curr))
        change = float(changes.get(ccy, 0)) * 100
    
        if change > 0:
            direction = "↑"
        elif change < 0:
            direction = "↓"
        else:
            direction = "-"
    
        if abs(change) > FX_ALERT_THRESHOLD * 100:
            status = "🚨"
        else:
            status = "✅"
    
        fx_rows += f"""
        <tr>
            <td>{base_currency}/{ccy}</td>
            <td>{curr:.4f}</td>
            <td>{prev:.4f}</td>
            <td>{direction} {change:.4f}%</td>
            <td>{status}</td>
        </tr>
        """
    
    fx_section = f"""
    <table border="1" cellpadding="5" cellspacing="0">
    <tr>
        <th>Pair</th>
        <th>Today</th>
        <th>Yesterday</th>
        <th>Change</th>
        <th>Status</th>
    </tr>
    {fx_rows}
    </table>
    """
      

    benchmark_rows = ""
    
    for key, label in BENCHMARK_LABELS.items():
        curr = current_benchmark_rates.get(key)
        prev = previous_benchmark_rates.get(key)
    
        if curr is None or pd.isna(curr):
            curr_txt = "N/A"
            status = "⚠️"
            change_txt = "N/A"
        else:
            curr = float(curr)
            curr_txt = f"{curr:.5f}%"
    
            if prev is None or pd.isna(prev):
                change_txt = "-"
                status = "🆕"
            else:
                prev = float(prev)
                diff = (curr - prev) * 100
    
                arrow = "↑" if diff > 0 else "↓" if diff < 0 else "-"
                change_txt = f"{arrow} {abs(diff):.2f} bps"
    
                status = "🚨" if abs(diff) >= 1 else "✅"
    
        benchmark_rows += f"""
        <tr>
            <td>{label}</td>
            <td>{curr_txt}</td>
            <td>{change_txt}</td>
            <td>{status}</td>
        </tr>
        """

        benchmark_section = f"""
        <table border="1" cellpadding="5">
        <tr>
            <th>Benchmark</th>
            <th>Value</th>
            <th>Change</th>
            <th>Status</th>
        </tr>
        {benchmark_rows}
        </table>
        """

    body = f"""
<html>
<body>

<p><b>DAILY MARKET REPORT</b></p>

<p><b>FX RATES</b></p>
{fx_section}

<p><b>LOAN BENCHMARK RATES</b></p>
{benchmark_section}

<p>----------------------------------<br>
Auto-generated report</p>

</body>
</html>
"""

    msg = MIMEText(body, "html")
    msg["Subject"] = f"Daily FX Report: {base_currency} Pairs + Benchmark Rates"
    msg["From"] = EMAIL_FROM_DISPLAY
    msg["To"] = EMAIL_TO

    email = os.getenv("EMAIL")
    password = os.getenv("PASSWORD")

    print("EMAIL:", email)
    print("PASSWORD length:", len(password) if password else 0)

    server = smtplib.SMTP("smtp.office365.com", 587)
    server.starttls()
    server.login(email, password)
    server.send_message(msg)
    server.quit()

    print("✅ Email sent successfully")

# =========================
# 9) SEND EMAIL
# =========================
send_email(
    current_rates=current_rates,
    previous_rates=previous_rates,
    changes=changes,
    current_benchmark_rates=benchmark_rates,
    previous_benchmark_rates=previous_benchmark_rates,
    benchmark_changes=benchmark_changes,
    currencies=CURRENCIES,
    base_currency=BASE_CURRENCY
)
