# 🎁 Toys Budget Dashboard

A Streamlit-based internal dashboard for tracking client toy/material budgets under a 6-month reset policy.

This system ensures accurate enforcement of the business rule:

> Each client receives **$25 every 6 months**.  
> If the full $25 is used, the client must wait 6 months from their last purchase before receiving another $25.

---

## 🏢 Business Purpose

This dashboard provides LTE staff with:

- Clear visibility into each client’s current budget cycle
- Real-time tracking of purchased vs pending amounts
- Automatic 6-month reset enforcement
- Prevention of over-budget purchases
- Simple filtering by action status

It eliminates spreadsheet confusion and manual calculations.

---

## 🔁 Budget Policy Logic (Reset Model)

Each client operates under a **reset model**, not a rolling sum model.

### Rules:

1. Only rows where `Purchased = TRUE` count against the budget.
2. The 6-month reset clock starts from the **most recent purchase date**.
3. If 6 months pass, the client’s budget resets to $25.
4. Pending requests do NOT reduce balance until purchased.
5. Budget does not roll over.

---

## 🧠 Action Status Definitions

| Status | Meaning |
|--------|---------|
| **Eligible** | No purchases in current cycle. Full $25 available. |
| **Purchased** | Partial spend within current 6-month cycle. |
| **Place Order** | Pending request exists and fits within remaining balance. |
| **Over Budget — Pending** | Pending request exceeds remaining balance. |
| **Not Eligible — Wait 6 Months** | Full $25 used and reset window not reached. |

---

## 📊 KPI Cards

The dashboard displays:

- **Total Purchased** – Total dollars officially spent
- **Total Pending** – Total requested but not yet purchased
- **Clients Not Eligible** – Clients who must wait for reset

These provide a high-level executive overview.

---

## 🔐 Security Model

This project:

- Does NOT store credentials in code
- Uses Streamlit Secrets
- Uses Base64-encoded Google Service Account JSON
- Is safe for GitHub

Google Sheets access is read-only.

---

## 📂 Google Sheet Structure

The dashboard expects the following columns:

- `Date`
- `Client Name`
- `Item`
- `Cost`
- `Purchased` (TRUE/FALSE)
- `Status` (optional)

---

## 🐳 Docker (Local Test)

### Build image

```powershell
docker build -t toys-tracker .
```

### Run container

Mount your local Streamlit secrets file so `st.secrets` works inside the container.

```powershell
docker run --rm -p 8501:8501 -v "${PWD}\.streamlit\secrets.toml:/home/lteuser/.streamlit/secrets.toml:ro" toys-tracker
```

Open `http://localhost:8501`.
