"""Idempotent example initialization and document catalogue backfill."""
import argparse,json
from uuid import UUID
from sqlalchemy import select
from app.database import create_app_engine
from app.canonical.models.company import Company
from app.acquisition.seed import seed,DEMO_COMPANY
from app.normalization.profiles import seed_profiles
from app.acquisition.services.document_service import backfill_documents


def bootstrap(engine,company_id=DEMO_COMPANY):
    seed(engine,company_id)
    profiles=seed_profiles(engine,company_id)
    return {'profiles_created':profiles,'documents':backfill_documents(engine,company_id)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--company-id',type=UUID,default=DEMO_COMPANY)
    args=parser.parse_args()
    print(json.dumps(bootstrap(create_app_engine(),args.company_id),indent=2))


if __name__=='__main__': main()
