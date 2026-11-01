"""Week 2 CLI: normalize one source or all configured active sources."""
import argparse,json
from uuid import UUID
from app.database import create_app_engine
from app.acquisition.services.source_service import get_source,list_sources
from app.normalization.service import preview_source,apply_run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--company-id',type=UUID,required=True)
    parser.add_argument('--source-id',type=UUID)
    parser.add_argument('--version',type=int)
    parser.add_argument('--apply',action='store_true',help='Apply valid records after previewing')
    parser.add_argument('--allow-updates',action='store_true')
    args=parser.parse_args();engine=create_app_engine()
    sources=[get_source(engine,args.company_id,args.source_id)] if args.source_id else [s for s in list_sources(engine,args.company_id) if s['is_active']]
    for source in sources:
        try:
            result=preview_source(engine,args.company_id,source['data_source_id'],args.version)
            if args.apply: result=apply_run(engine,args.company_id,result['normalization_run_id'],args.allow_updates)
            print(json.dumps({'source':source['source_code'],'run_id':str(result['normalization_run_id']),'status':result['status'],
                             'records':result['record_count'],'valid':result['valid_count'],'applied':result['applied_count'],
                             'skipped':result['skipped_count'],'errors':result['error_count']}))
        except (LookupError,ValueError) as exc: print(json.dumps({'source':source['source_code'],'error':str(exc)}))


if __name__=='__main__': main()
