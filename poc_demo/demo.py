"""Repeatable HTTP end-to-end demonstration with the existing Demo Company.

No execution reset or deletion is performed. Unchanged replays may acquire zero
new artifacts; every assertion uses persisted results and retained record versions.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import time
import httpx
from poc_demo.seed import DEMO_COMPANY


def demonstrate(base_url, company_id):
    cid=str(company_id)
    base=f'/poc/companies/{cid}'
    report={'company_id':cid,'executed_at':datetime.now(timezone.utc).isoformat(),'scenarios':[]}
    with httpx.Client(base_url=base_url,timeout=20,trust_env=False) as client:
        def call(method,path,**kwargs):
            result=client.request(method,path,**kwargs)
            result.raise_for_status()
            return result.json()
        def run(source_id=None):
            ids=call('POST',base+'/runs',json={'source_id':source_id} if source_id else {})['run_ids']
            deadline=time.monotonic()+max(30,130*len(ids))
            while True:
                rows=[call('GET',base+'/runs/'+i) for i in ids]
                if all(r['status']!='RUNNING' for r in rows):
                    return rows
                if time.monotonic()>deadline:
                    raise RuntimeError('Ingestion did not finish within bounded demo timeout')
                time.sleep(.15)
        def record(name,rows):
            entry={'scenario':name,'executions':len(rows),'statuses':sorted({r['status'] for r in rows}),
                   'acquired':sum(r['attempted_count'] for r in rows),'new_artifacts':sum(r['acquired_count'] for r in rows),
                   'duplicates':sum(r['duplicate_count'] for r in rows),'errors':sum(r['error_count'] for r in rows),
                   'run_ids':[r['ingestion_run_id'] for r in rows]}
            report['scenarios'].append(entry)
            print(json.dumps(entry),flush=True)
        first=run()
        record('All active sources',first)
        assert all(r['status']=='SUCCEEDED' for r in first),first
        replay=run()
        record('Unchanged replay',replay)
        assert all(r['status']=='SUCCEEDED' and r['acquired_count']==0 for r in replay),replay
        sources=call('GET',base+'/sources')
        source=next((s for s in sources if s['source_code']=='poc_w1_scenario_demo'),None)
        body=dict(source_code='poc_w1_scenario_demo',name='Week 1 API scenario demonstration',transport='HTTP_GET',data_format='JSON',entity_type='INVOICE',
                  config={'url':'http://mock-api:9090/mock/erp/invoices','records_path':'items','external_id_path':'invoice_id'},field_mapping={},is_active=True)
        # Use the backend's execution environment URL for either host or Docker.
        catalog=call('GET',base+'/fixtures')
        endpoint=catalog['mock_base_url']+'/mock/erp/invoices'
        body['config']['url']=endpoint
        source=call('PUT' if source else 'POST',base+'/sources'+('/'+source['data_source_id'] if source else ''),json=body)
        sid=source['data_source_id']
        try:
            for scenario in ('success','new','updated','http500','success','paginated','duplicates','empty','http429','malformed','success'):
                body['config'].update(url=endpoint+'?scenario='+scenario,pagination=scenario=='paginated')
                call('PUT',base+'/sources/'+sid,json=body)
                rows=run(sid)
                record(scenario,rows)
                assert rows[0]['status']==('FAILED' if scenario in {'http500','http429','malformed'} else 'SUCCEEDED')
            versions=call('GET',base+'/artifacts',params={'source_id':sid,'kind':'RECORD'})
            assert len({r['sha256_hash'] for r in versions if r['external_id']=='INV-1001'})==2
            report['external_id_versions']={'INV-1001':2}
        finally:
            body['config'].update(url=endpoint,pagination=False)
            call('PUT',base+'/sources/'+sid,json=body)
        artifacts=call('GET',base+'/artifacts',params={'limit':500})
        types={a['data_format'] for a in artifacts}
        assert {'CSV','JSON','XML','PDF'} <= types and types & {'PNG','IMAGE'}
        for fmt in ('CSV','JSON','XML','PDF','PNG'):
            item=next(a for a in artifacts if a['data_format']==fmt)
            response=client.get(base+'/artifacts/'+item['raw_artifact_id']+'/content')
            response.raise_for_status()
            import hashlib
            assert hashlib.sha256(response.content).hexdigest()==item['sha256_hash']
        report['verified_formats']=sorted(t for t in types if t)
        report['overview']=call('GET',base+'/overview')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--company-id',default=str(DEMO_COMPANY))
    parser.add_argument('--backend-url',default=os.environ.get('POC_BACKEND_URL','http://127.0.0.1:8000'))
    parser.add_argument('--report',default='poc_demo/demo_results.json')
    args=parser.parse_args()
    report=demonstrate(args.backend_url,args.company_id)
    Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    print('Verified all scenarios. Report:',args.report)


if __name__=='__main__':
    main()
