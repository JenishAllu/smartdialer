from pathlib import Path
import pandas as pd

def read_csv(directory: Path, filename: str):
    path = directory / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}; keep collections_30k_dataset beside app/")
    return pd.read_csv(path, dtype=str, keep_default_na=False)

def summary(directory: Path):
    names = ["borrowers.csv", "agents.csv", "calls.csv", "call_attempts.csv", "campaigns.csv", "accounts.csv", "daily_targeting.csv", "vendor_telephony.csv"]
    result = {"dataset_directory": str(directory), "files": {}}
    for name in names:
        df = read_csv(directory, name)
        result["files"][name] = {"rows": len(df), "columns": list(df.columns)}
    borrowers = read_csv(directory, "borrowers.csv")
    result["unique_borrowers"] = int(borrowers["borrower_id"].nunique())
    result["duplicate_borrower_ids"] = int(borrowers["borrower_id"].duplicated().sum())
    calls = read_csv(directory, "calls.csv")
    result["historical_call_statuses"] = calls["call_status"].value_counts().to_dict()
    result["note"] = "Synthetic dataset; contains intentional duplicates, missing values, inconsistent timestamps, and event anomalies."
    return result

def borrower_rows(directory: Path, limit=100):
    df = read_csv(directory, "borrowers.csv").drop_duplicates("borrower_id", keep="first")
    priorities = {}
    accounts_path = directory / "accounts.csv"
    if accounts_path.exists():
        accounts = read_csv(directory, "accounts.csv")
        if "dpd" in accounts and "borrower_id" in accounts:
            accounts["dpd_num"] = pd.to_numeric(accounts["dpd"], errors="coerce").fillna(0)
            priorities = accounts.groupby("borrower_id")["dpd_num"].max().to_dict()
    rows = []
    for _, row in df.head(limit).iterrows():
        bid, phone = row.get("borrower_id", "").strip(), row.get("phone", "").strip()
        if not bid or not phone:
            continue
        dpd = int(priorities.get(bid, 0))
        rows.append({"borrower_id": bid, "name": row.get("name") or "Unknown", "phone": phone,
                     "city": row.get("city", ""), "priority": min(10, max(1, 1 + dpd // 10))})
    return rows
