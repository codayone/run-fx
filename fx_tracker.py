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
    {"loan_id": "EUR_2", "currency": "EUR", "benchmark": "Fixed Rate at 9.75%", "fetch_key": "FIXED_9_75"},
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
    """
    Fetch latest 90-day Average SOFR.

    Priority:
    1. FRED CSV (fast & reliable)
    2. NY Fed table (structured fallback, no regex)

    Returns:
        float or None
    """

    import requests
    import pandas as pd
    from io import StringIO

    headers = {
        "User-Agent": "Mozilla/5.0",
    }

    session = requests.Session()
    session.headers.update(headers)

    # =========================
    # 1️⃣ FRED CSV (PRIMARY)
    # =========================
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR90DAYAVG"
        resp = session.get(url, timeout=30)
        resp.raise_for_status()

        df = pd.read_csv(StringIO(resp.text))

        # Identify the value column (not date)
        value_col = [c for c in df.columns if str(c).upper() != "OBSERVATION_DATE"][0]

        df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
        df = df.dropna()

        value = float(df.iloc[-1][value_col])

        print(f"✅ SOFR from FRED: {value}")
        return value

    except Exception as e:
        print(f"⚠️ FRED failed: {e}")

    # =========================
    # 2️⃣ NY FED TABLE (FALLBACK)
    # =========================
    try:
        url = "https://www.newyorkfed.org/markets/reference-rates/sofr-averages-and-index"

        tables = pd.read_html(url)

        for table in tables:
            # find correct table dynamically
            col_90d = [c for c in table.columns if "90-DAY" in str(c).upper()]

            if col_90d:
                col_90d = col_90d[0]

                # latest row = first row
                row = table.iloc[0]

                value = float(row[col_90d])

                print(f"✅ SOFR from NY Fed: {value}")
                return value

        print("⚠️ SOFR table not found on NY Fed page")
        return None

    except Exception as e:
        print(f"⚠️ NY Fed failed: {e}")
        return None

def fetch_hibor_3m():
    # HKMA API
    url = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily?segment=hibor.fixing"
    data = requests.get(url, timeout=30).json()

    # HKMA JSON wrappers can differ slightly, so handle a few common shapes
    records = None
    if isinstance(data, dict):
        if "result" in data and isinstance(data["result"], dict) and "records" in data["result"]:
            records = data["result"]["records"]
        elif "records" in data:
            records = data["records"]

    if not records:
        raise Exception("Could not parse HKMA HIBOR API response.")

    df = pd.DataFrame(records)
    df["ir_3m"] = pd.to_numeric(df["ir_3m"], errors="coerce")
    df = df.dropna(subset=["ir_3m"])
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


def fetch_fixed_975():
    return 9.75


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
    Fetch latest 3M / 90-day Compounded INDONIA.

    Tries official Bank Indonesia pages first.
    If unavailable / blocked, returns None instead of crashing the script.

    Returns:
        float or None
    """

    import requests
    import pandas as pd
    import re
    from io import StringIO

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }

    session = requests.Session()
    session.headers.update(headers)

    urls = [
        "https://www.bi.go.id/en/statistik/indikator/Historis-Compounded-IndONIA-Index.aspx",
        "https://www.bi.go.id/id/statistik/indikator/Historis-Compounded-IndONIA-Index.aspx",
        "https://www.bi.go.id/en/fungsi-utama/moneter/indonia-jibor/Default_Old.aspx",
    ]

    def try_extract_from_tables(df):
        # try to detect a 3M / 90-day compounded column
        possible_cols = []
        for c in df.columns:
            c_upper = str(c).upper()
            if (
                ("3M" in c_upper) or
                ("3 M" in c_upper) or
                ("90" in c_upper) or
                ("90-DAY" in c_upper) or
                ("90 DAY" in c_upper)
            ):
                possible_cols.append(c)

        for col in possible_cols:
            vals = pd.to_numeric(df[col], errors="coerce").dropna()
            if not vals.empty:
                return float(vals.iloc[0])

        return None

    for url in urls:
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()

            # 1) Try HTML tables
            try:
                tables = pd.read_html(StringIO(resp.text))
                for table in tables:
                    value = try_extract_from_tables(table)
                    if value is not None:
                        print(f"✅ INDONIA from official BI table: {value}")
                        return value
            except Exception:
                pass

            # 2) Try lightweight text scan
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text)

            # very broad fallback patterns for 3M / 90-day type labels
            patterns = [
                r"(?:3M|3\s*MONTH|3\s*BULAN)[^\d]{0,30}(\d+\.\d+)",
                r"(?:90\s*DAY|90-DAY|90\s*HARI)[^\d]{0,30}(\d+\.\d+)",
            ]

            for pattern in patterns:
                m = re.search(pattern, text, flags=re.IGNORECASE)
                if m:
                    value = float(m.group(1))
                    print(f"✅ INDONIA from official BI text: {value}")
                    return value

            print(f"⚠️ INDONIA official source had no usable 3M/90D value: {url}")

        except Exception as e:
            print(f"⚠️ INDONIA official source failed: {url} | {e}")

    print("⚠️ Could not fetch 3M / 90-day Compounded INDONIA from available official pages")
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
        "FIXED_9_75": fetch_fixed_975,
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
