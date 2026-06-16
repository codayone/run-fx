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
# loan_id can be whatever name you want for each facility/loan
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
FX_ALERT_THRESHOLD = 0.005    # 0.5%

EMAIL_TO = "tangsuancoco.tan@dayonedc.com"
EMAIL_FROM_DISPLAY = "FX Bot <tangsuancoco.tan@dayonedc.com>"
CSV_FILE = "market_data.csv"


# =========================
# EMAIL FUNCTION
# =========================
def send_email(current_rates, previous_rates, changes,
               overnight_rate, yesterday_overnight_rate,
               overnight_changed, currencies, base_currency):

    fx_section = ""

    for ccy in currencies:
        curr = float(current_rates[ccy])
        prev = float(previous_rates.get(ccy, curr))
        change = float(changes.get(ccy, 0))

        if change > 0:
            direction = "↑"
        elif change < 0:
            direction = "↓"
        else:
            direction = "-"

        if abs(change) > FX_ALERT_THRESHOLD:
            fx_status = "🚨 ALERT: Significant FX movement (>0.5%)"
        else:
            fx_status = "✅ Normal FX movement"

        fx_section += f"""
        <p><b>{base_currency}/{ccy}</b></p>
        <p>
        Today: <b>{curr:.4f}</b><br>
        Yesterday: {prev:.4f}<br><br>
        Change: {direction} {change*100:.4f}%<br><br>
        {fx_status}
        </p>
        """

    if overnight_changed:
        overnight_status = (
            f"🚨 ALERT: Rate changed from {yesterday_overnight_rate:.2f}% "
            f"to {overnight_rate:.2f}%"
        )
    else:
        overnight_status = f"✅ No change ({overnight_rate:.2f}%)"

    body = f"""
<html>
<body>

<p><b>DAILY MARKET REPORT</b></p>

{fx_section}

<p><b>Malaysia Overnight Rate</b></p>
<p>
Today: <b>{overnight_rate:.2f}%</b><br>
Yesterday: {yesterday_overnight_rate:.2f}%<br><br>
{overnight_status}
</p>

<p>----------------------------------<br>
Auto-generated report</p>

</body>
</html>
"""

    msg = MIMEText(body, "html")
    msg["Subject"] = f"Daily FX Report: {base_currency} Pairs"
    msg["From"] = EMAIL_FROM_DISPLAY
    msg["To"] = EMAIL_TO

    email = os.getenv("EMAIL")
    password = os.getenv("PASSWORD")
    
    print("EMAIL:", email)
    print("PASSWORD length:", len(password))

    server = smtplib.SMTP("smtp.office365.com", 587)
    server.starttls()
    server.login(email, password)
    server.send_message(msg)
    server.quit()

    print("✅ Email sent successfully")


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
    Fetch latest 90D SOFR from FRED CSV (robust column handling).
    """

    import pandas as pd

    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR90DAYAVG"

    df = pd.read_csv(url)

    # Normalize column names
    df.columns = [col.strip().upper() for col in df.columns]

    if "SOFR90DAYAVG" not in df.columns:
        raise Exception(f"SOFR column not found. Columns found: {df.columns.tolist()}")

    df = df.dropna(subset=["SOFR90DAYAVG"])

    if df.empty:
        raise Exception("No valid SOFR data.")

    latest_row = df.iloc[-1]

    date_col = df.columns[0]   # first column is the date column
    date = latest_row[date_col]
    value = latest_row["SOFR90DAYAVG"]

    print(f"SOFR 90-day raw: {date} {value}")

    return float(value)

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
    Try official Bank Indonesia pages first.
    If all official pages fail, fall back to Cbonds 90 Days IndONIA page.
    """

    import re
    from io import StringIO

    official_urls = [
        "https://www.bi.go.id/en/statistik/indikator/Historis-Compounded-IndONIA-Index.aspx",
        "https://www.bi.go.id/id/statistik/indikator/Historis-Compounded-IndONIA-Index.aspx",
        "https://www.bi.go.id/en/fungsi-utama/moneter/indonia-jibor/Default_Old.aspx",
    ]

    fallback_urls = [
        "https://cbonds.com/indexes/59993/"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "close",
    }

    # ---------- 1) Official BI pages ----------
    for url in official_urls:
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            print(f"INDONIA official source failed: {url} | {e}")
            continue

        # Try HTML tables first
        try:
            tables = pd.read_html(StringIO(html))
        except Exception:
            tables = []

        for tbl in tables:
            tbl.columns = [str(c).strip() for c in tbl.columns]

            # Case A: tenor appears in row values
            for col in tbl.columns:
                mask = tbl[col].astype(str).str.contains(
                    r"90\s*(day|days|hari)|3\s*month|3\s*months|3\s*bulan",
                    case=False,
                    na=False,
                    regex=True,
                )
                if mask.any():
                    for value_col in tbl.columns:
                        if value_col != col:
                            vals = pd.to_numeric(tbl.loc[mask, value_col], errors="coerce").dropna()
                            if not vals.empty:
                                value = float(vals.iloc[0])
                                print(f"INDONIA 90D official table raw ({url}): {value}")
                                return value

            # Case B: tenor appears in column names
            for c in tbl.columns:
                if re.search(r"90\s*(day|days|hari)|3\s*month|3\s*months|3\s*bulan", c, flags=re.IGNORECASE):
                    vals = pd.to_numeric(tbl[c], errors="coerce").dropna()
                    if not vals.empty:
                        value = float(vals.iloc[0])
                        print(f"INDONIA 90D official column raw ({url}): {value}")
                        return value

        # Try raw page text
        text = re.sub(r"<[^>]+>", " ", html)
        text = text.replace("&nbsp;", " ")
        text = re.sub(r"\s+", " ", text).strip()

        patterns = [
            r"90\s*(?:day|days|hari)\D{0,60}([0-9]+\.[0-9]+)",
            r"3\s*(?:month|months|bulan)\D{0,60}([0-9]+\.[0-9]+)",
        ]

        for p in patterns:
            m = re.search(p, text, flags=re.IGNORECASE)
            if m:
                value = float(m.group(1))
                print(f"INDONIA 90D official text raw ({url}): {value}")
                return value

    # ---------- 2) Fallback website: Cbonds ----------
    for url in fallback_urls:
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            print(f"INDONIA fallback source failed: {url} | {e}")
            continue

        text = re.sub(r"<[^>]+>", " ", html)
        text = text.replace("&nbsp;", " ")
        text = re.sub(r"\s+", " ", text).strip()

        # Try to find the 90 Days IndONIA value near its label
        patterns = [
            r"90\s*Days\s*IndONIA[^0-9]*([0-9]+\.[0-9]+)",
            r"90\s*Days\s*IndONIA.*?([0-9]+\.[0-9]+)",
        ]

        for p in patterns:
            m = re.search(p, text, flags=re.IGNORECASE)
            if m:
                value = float(m.group(1))
                print(f"INDONIA 90D fallback raw ({url}): {value}")
                return value

    raise Exception("Could not fetch 3M / 90-day Compounded INDONIA from official BI pages or fallback website.")


def fetch_benchmark_rates():
    rates = {}

    rates["THOR_3M"] = fetch_thor_3m()
    rates["KLIBOR_3M"] = fetch_klibor_3m()
    rates["SOFR_3M_COMPOUNDED"] = fetch_sofr_3m_compounded()
    rates["HIBOR_3M"] = fetch_hibor_3m()
    rates["SORA_1M"] = fetch_sora_1m()
    rates["TIBOR_3M"] = fetch_tibor_3m()
    rates["EURIBOR_3M"] = fetch_euribor_3m()
    rates["INDONIA_3M_COMPOUNDED"] = fetch_indonia_3m_compounded()
    rates["FIXED_9_75"] = fetch_fixed_975()

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
    "Malaysia_Overnight_Rate": overnight_rate
}

for ccy in CURRENCIES:
    new_row[f"{BASE_CURRENCY}_{ccy}"] = current_rates[ccy]

new_data = pd.DataFrame([new_row])


# =========================
# 5) LOAD EXISTING DATA
# =========================
if os.path.exists(CSV_FILE):
    df = pd.read_csv(CSV_FILE)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
else:
    base_columns = ["Timestamp", "Malaysia_Overnight_Rate"] + [
        f"{BASE_CURRENCY}_{ccy}" for ccy in CURRENCIES
    ]
    df = pd.DataFrame(columns=base_columns)

# If you add a new currency later, make sure old CSV gains the new column
for ccy in CURRENCIES:
    col = f"{BASE_CURRENCY}_{ccy}"
    if col not in df.columns:
        df[col] = pd.NA

if "Malaysia_Overnight_Rate" not in df.columns:
    df["Malaysia_Overnight_Rate"] = pd.NA

df = df.sort_values("Timestamp")


# =========================
# 6) CALCULATE CHANGES VS LAST RUN
# =========================
previous_rates = {}
changes = {}

if not df.empty:
    last_row = df.iloc[-1]

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

    prev_overnight_raw = last_row["Malaysia_Overnight_Rate"]
    if pd.notna(prev_overnight_raw):
        yesterday_overnight_rate = float(prev_overnight_raw)
        overnight_changed = float(yesterday_overnight_rate) != float(overnight_rate)
    else:
        yesterday_overnight_rate = overnight_rate
        overnight_changed = False

else:
    for ccy in CURRENCIES:
        previous_rates[ccy] = float(current_rates[ccy])
        changes[ccy] = 0.0

    yesterday_overnight_rate = overnight_rate
    overnight_changed = False


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

print(f"Malaysia Overnight Rate changed today? {overnight_changed}")


# =========================
# 9) SEND EMAIL
# =========================
send_email(
    current_rates=current_rates,
    previous_rates=previous_rates,
    changes=changes,
    overnight_rate=overnight_rate,
    yesterday_overnight_rate=yesterday_overnight_rate,
    overnight_changed=overnight_changed,
    currencies=CURRENCIES,
    base_currency=BASE_CURRENCY
)
