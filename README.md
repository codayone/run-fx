# FX & Overnight Rate Tracker

This project automatically tracks:

- USD to selected currencies (via API)
- Malaysia Overnight Rate (via BNM)
- Daily changes in rates

It also:
- Stores historical data in CSV
- Sends automated email alerts
- Runs on GitHub Actions (scheduled)

---

## 🔧 Configuration

Edit this in the script:

```python
CURRENCIES = ["SGD", "MYR"]
``
