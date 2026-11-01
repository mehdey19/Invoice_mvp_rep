"""Run: python -m poc_demo.main --company-id YOUR_EXISTING_COMPANY_UUID"""
from __future__ import annotations
import argparse
import os
from uuid import UUID
from sqlalchemy import create_engine
from app.acquisition.universal_acquisition import acquire_all


def main():
    parser = argparse.ArgumentParser(description="Week 1 POC universal acquisition")
    parser.add_argument("--company-id", required=True, help="Existing company.company_id UUID")
    args = parser.parse_args()
    company_id = str(UUID(args.company_id))
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL must point to the existing PostgreSQL development database")
    from app.database import create_app_engine
    engine = create_app_engine(url)
    results = acquire_all(engine, company_id)
    print("\nSOURCE                  STATUS      NEW   DUPLICATES  ERROR")
    for r in results:
        print(f"{r['source']:<23} {r['status']:<11} {r['acquired']:<5} {r['duplicates']:<11} {(r['error'] or '')[:100]}")
    print("\nAcquisition metadata and raw content stored. See the dashboard for response/record details.")
    if any(r["status"] != "SUCCEEDED" for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
