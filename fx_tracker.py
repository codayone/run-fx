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
    Fetch latest 90-day SOFR Average from official NY Fed API.
    This is the correct and stable method (no scraping).
    """

    url = "https://markets.newyorkfed.org/api/rates/secured/sofr/averages/last/1.json"
    
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    data = resp.json()

    try:
        record = data["refRates"][0]

        # Values from API:
        # avg30, avg90, avg180
        avg_90 = record["avg90"]

        print(
            f"SOFR API row: "
            f"30D={record['avg30']} | "
            f"90D={record['avg90']} | "
            f"180D={record['avg180']}"
        )

        return float(avg_90)

    except Exception as e:
        raise Exception(f"Failed to parse SOFR API response: {e}")


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
    url = "https://eservices.mas.gov.sg/statistics/dir/domesticinterestrates.aspx"
    tables = get_html_tables(url)

    for tbl in tables:
        cols = [str(c).strip().lower() for c in tbl.columns]
        if any("1-month compounded sora" in c for c in cols):
            rate_col = next(c for c in tbl.columns if "1-month compounded sora" in str(c).lower())
            tbl[rate_col] = pd.to_numeric(tbl[rate_col], errors="coerce")
            tbl = tbl.dropna(subset=[rate_col])
            return float(tbl.iloc[0][rate_col])
    raise Exception("Could not fetch 1M SORA.")


def fetch_fixed_975():
    return 9.75


def fetch_euribor_3m():
    """
    Source requested by user:
    https://www.suomenpankki.fi/en/statistics/data-and-charts/interest-rates/charts/korot_kuviot_en/euriborkorot_pv_chrt_en/

    Note:
    Bank of Finland states Euribor data is published with a 24-hour delay.
    This function tries to parse tables from the page / related page structure.
    """
    url = "https://www.suomenpankki.fi/en/statistics/data-and-charts/interest-rates/charts/korot_kuviot_en/euriborkorot_pv_chrt_en/"
    tables = get_html_tables(url)

    for tbl in tables:
        # flatten columns
        tbl.columns = [str(c).strip() for c in tbl.columns]
        cols_lower = [c.lower() for c in tbl.columns]

        # Look for a column describing tenor / series and a numeric value column
        # Because site tables can vary, we search by content too
        for col in tbl.columns:
            if tbl[col].astype(str).str.contains("3 month|3-month|3 months", case=False, na=False).any():
                # Find first numeric-looking column other than the matching text col
                candidate_cols = [c for c in tbl.columns if c != col]
                for c in candidate_cols:
                    temp = pd.to_numeric(tbl[c], errors="coerce")
                    row_idx = tbl[col].astype(str).str.contains("3 month|3-month|3 months", case=False, na=False)
                    if temp[row_idx].notna().any():
                        return float(temp[row_idx].dropna().iloc[0])

        # If the table already has a '3-month' style column, use first valid row
        for c in tbl.columns:
            if "3 month" in c.lower() or "3-month" in c.lower() or "3 months" in c.lower():
                temp = pd.to_numeric(tbl[c], errors="coerce").dropna()
                if not temp.empty:
                    return float(temp.iloc[0])

    raise Exception("Could not fetch 3M EURIBOR from the Bank of Finland page.")

def fetch_tibor_3m():
    """
    Source requested by user:
    https://cio.cimb.com/ticker/interest_rates-bondapac-jptibor-03m-198200/snapshots

    IMPORTANT:
    This is a CIMB market-data page, not the official JBA administrator page.
    """
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
    User requested BI INDONIA page:
    https://www.bi.go.id/en/fungsi-utama/moneter/indonia-jibor/default.aspx

    Practical note:
    Bank Indonesia also has a more direct historical page for
    Compounded INDONIA / INDONIA Index.
    This function first tries the user's page, then falls back to the direct BI historical page.
    """
    candidate_urls = [
        "https://www.bi.go.id/en/fungsi-utama/moneter/indonia-jibor/default.aspx",
        "https://www.bi.go.id/en/statistik/indikator/Historis-Compounded-IndONIA-Index.aspx",
    ]

    import re

    for url in candidate_urls:
        html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30).text

        # Try to detect a 90-day / 3M compounded rate in raw text
        patterns = [
            r"90\s*day[s]?\D+([0-9]+\.[0-9]+)",
            r"90\s*calendar\s*day[s]?\D+([0-9]+\.[0-9]+)",
            r"3\s*month[s]?\D+([0-9]+\.[0-9]+)",
        ]
        for p in patterns:
            m = re.search(p, html, flags=re.IGNORECASE | re.DOTALL)
            if m:
                return float(m.group(1))

        # Try HTML tables
        try:
            tables = pd.read_html(StringIO(html))
        except Exception:
            tables = []

        for tbl in tables:
            tbl.columns = [str(c).strip() for c in tbl.columns]

            # Case 1: tenor as row values
            for col in tbl.columns:
                tenor_mask = tbl[col].astype(str).str.contains(
                    "90 day|90-day|3 month|3-month|3 months", case=False, na=False
                )
                if tenor_mask.any():
                    for value_col in tbl.columns:
                        if value_col != col:
                            vals = pd.to_numeric(tbl.loc[tenor_mask, value_col], errors="coerce").dropna()
                            if not vals.empty:
                                return float(vals.iloc[0])

            # Case 2: tenor as column headers
            for c in tbl.columns:
                if any(x in c.lower() for x in ["90 day", "90-day", "3 month", "3-month", "3 months"]):
                    vals = pd.to_numeric(tbl[c], errors="coerce").dropna()
                    if not vals.empty:
                        return float(vals.iloc[0])

    raise Exception("Could not fetch 3M compounded INDONIA from Bank Indonesia pages.")

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
