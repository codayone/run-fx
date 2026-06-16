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
CURRENCIES = ["SGD", "MYR"]   # <- Add more here, e.g. ["SGD", "MYR", "EUR", "JPY"]
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
    print("PASSWORD is None?", password is None)

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

for ccy in CURRENCIES:
    print(f"{BASE_CURRENCY} → {ccy}: {current_rates[ccy]}")


# =========================
# 2) BNM OVERNIGHT RATE
# =========================
bnm_url = "https://financialmarkets.bnm.gov.my/data-download-bnm-money-market-operations"

headers = {
    "User-Agent": "Mozilla/5.0"
}

req = urllib.request.Request(bnm_url, headers=headers)
html = urllib.request.urlopen(req).read().decode("utf-8")

tables = pd.read_html(StringIO(html))

target_df = None

for i, tbl in enumerate(tables):
    temp = tbl.copy()

    temp.columns = [
        " ".join([str(x).strip() for x in col]).replace("\n", " ").strip()
        if isinstance(col, tuple)
        else str(col).replace("\n", " ").strip()
        for col in temp.columns
    ]

    print(f"Checking BNM table {i}: {temp.columns.tolist()}")

    cols_lower = [c.lower() for c in temp.columns]

    if any("date" in c for c in cols_lower) and any("overnight" in c for c in cols_lower):
        target_df = temp
        print(f"✅ Using BNM table {i}")
        break

if target_df is None:
    raise Exception("Could not find BNM table containing Date and Overnight columns.")

date_col = next(c for c in target_df.columns if "date" in c.lower())
overnight_col = next(c for c in target_df.columns if "overnight" in c.lower())

target_df[date_col] = pd.to_datetime(target_df[date_col], errors="coerce", dayfirst=True)
target_df[overnight_col] = pd.to_numeric(target_df[overnight_col], errors="coerce")

target_df = target_df.dropna(subset=[date_col, overnight_col])
target_df = target_df.sort_values(date_col)

overnight_rate = float(target_df.iloc[-1][overnight_col])
print("✅ Current Malaysia Overnight Rate:", overnight_rate)


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
