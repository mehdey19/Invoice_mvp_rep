"""Exercise acquisition and normalization using the existing Demo Company."""
import argparse,json
from pathlib import Path
from sqlalchemy import select,func,text
from app.database import create_app_engine
from app.integration_pipeline.bootstrap import bootstrap
from app.acquisition.seed import DEMO_COMPANY
from app.acquisition.services.source_service import list_sources
from app.acquisition.services.acquisition_service import acquire_all
from app.normalization.service import preview_source,apply_run
from app.canonical.models import Document,Invoice,InvoiceLine,Party,Payment,BankTransaction,PaymentAllocation


def demonstrate(engine,company_id=DEMO_COMPANY):
    report={'bootstrap':bootstrap(engine,company_id),'acquisition':acquire_all(engine,str(company_id)),'normalization':[]}
    if any(r['status']!='SUCCEEDED' for r in report['acquisition']): raise RuntimeError('An acquisition failed')
    codes=['poc_w1_purchase_detailed_json','poc_w1_sales_detailed_csv','poc_w1_foreign_supplier_xml',
           'poc_w1_erp_a','poc_w1_payments_json','poc_w1_bank_csv']
    sources={s['source_code']:s for s in list_sources(engine,company_id)}
    for code in codes:
        source=sources[code]
        preview=preview_source(engine,company_id,source['data_source_id'])
        applied=apply_run(engine,company_id,preview['normalization_run_id'])
        replay=preview_source(engine,company_id,source['data_source_id'])
        skipped=apply_run(engine,company_id,replay['normalization_run_id'])
        entry={'source':code,'run_id':str(applied['normalization_run_id']),'records':applied['record_count'],
               'applied':applied['applied_count'],'skipped':applied['skipped_count'],'errors':applied['error_count'],
               'replay_applied':skipped['applied_count'],'replay_skipped':skipped['skipped_count'],
               'issues':[{'record':i['source_record_id'],'errors':i['errors']} for i in applied['items'] if i['errors']]}
        if entry['replay_applied']!=0: raise RuntimeError('Replay created or changed canonical records')
        report['normalization'].append(entry)
        print(json.dumps(entry),flush=True)
    with engine.connect() as conn:
        report['canonical_counts']={cls.__tablename__:conn.scalar(select(func.count()).select_from(cls).where(cls.company_id==company_id))
            for cls in (Document,Invoice,Party,Payment,BankTransaction)}
        report['canonical_counts']['invoice_line']=conn.scalar(select(func.count()).select_from(InvoiceLine).join(Invoice,InvoiceLine.invoice_id==Invoice.invoice_id).where(Invoice.company_id==company_id))
        report['canonical_counts']['payment_allocation']=conn.scalar(select(func.count()).select_from(PaymentAllocation).join(Payment,PaymentAllocation.payment_id==Payment.payment_id).where(Payment.company_id==company_id))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',default='poc_demo/pipeline_demo_results.json')
    args=parser.parse_args()
    result=demonstrate(create_app_engine())
    Path(args.report).write_text(json.dumps(result,indent=2,default=str)+'\n')
    print(json.dumps(result['canonical_counts'],indent=2))


if __name__=='__main__': main()
