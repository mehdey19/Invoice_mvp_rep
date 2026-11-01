"""Streamlit UI. All source management and ingestion go through FastAPI."""
import io
import json
import os
from pathlib import Path
import httpx
import pandas as pd
import streamlit as st

API = os.environ.get('POC_BACKEND_URL', 'http://127.0.0.1:8000').rstrip('/')
st.set_page_config(page_title='Acquisition lab', page_icon='📥', layout='wide')
st.title('Acquisition lab')
st.caption('Week 1 acquisition · Week 2 normalization · invoices, payments and bank data')


def request(method, path, **kwargs):
    try:
        timeout = 150 if '/normalization' in path else 15
        response = httpx.request(method, API+'/poc'+path, timeout=timeout, follow_redirects=False, **kwargs)
        response.raise_for_status()
        return response
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get('detail', exc.response.text)
        except ValueError:
            detail = exc.response.text
        st.error(f'Backend validation: {detail}')
    except httpx.HTTPError as exc:
        st.error(f'Cannot reach the backend at {API}: {exc}')
    return None


def fetch(path):
    response = request('GET', path)
    return response.json() if response is not None else None


companies = fetch('/companies')
if not companies:
    st.info('Start PostgreSQL and the backend, run migrations, then initialize sources with python -m poc_demo.seed.')
    st.stop()
company = st.sidebar.selectbox('Company', companies, format_func=lambda c: c['name']+' · '+c['company_id'][:8])
cid = company['company_id']
base = f'/companies/{cid}'
stage = st.sidebar.selectbox('Stage', ['Week 1 — Acquisition', 'Week 2 — Normalization'])
pages = (['Overview', 'Data Sources', 'Run Ingestion', 'Ingestion History', 'Raw Explorer'] if stage == 'Week 1 — Acquisition'
         else ['Overview', 'Mapping Profiles', 'Run Normalization', 'Normalization History', 'Canonical Explorer', 'Image Extraction'])
page = st.sidebar.radio('Workspace', pages)
st.sidebar.caption('Development demonstration · server-approved files and local mock APIs')
sources = fetch(base+'/sources')
if sources is None:
    st.stop()
source_names = {s['data_source_id']: s['name'] for s in sources}


def source_filter(key):
    return st.selectbox('Source', [None]+list(source_names), format_func=lambda x: source_names.get(x, 'All sources'), key=key)


def overview_page():
    st.subheader('Overview')
    summary = fetch(base+'/overview')
    if summary is None:
        return
    metrics = [('Registered sources','sources'), ('Active sources','active_sources'), ('Executions','executions'),
               ('Successful','successful'), ('Failed','failed'), ('Raw artifacts','artifacts'), ('Duplicates detected','duplicates')]
    columns = st.columns(4)
    for i, (label, key) in enumerate(metrics):
        columns[i % 4].metric(label, summary[key])
    st.write('Last ingestion:', summary['last_ingestion'] or 'No executions yet')
    st.caption(f"{summary['response_artifacts']} original HTTP responses · {summary['record_artifacts']} derived record artifacts. Duplicate counts are cumulative across executions.")
    st.dataframe(summary['by_transport'], use_container_width=True, hide_index=True)


def sources_page():
    st.subheader('Data Source Management')
    rows = []
    for source in sources:
        row = {k:source[k] for k in ('name','source_code','transport','data_format','entity_type','is_active')}
        config = source.get('config', {})
        row['config'] = (config.get('url') or config.get('path') or config.get('relative_path')
                         or (f"${config['env_dir']}" if config.get('env_dir') else ''))
        rows.append(row)
    st.dataframe(rows, use_container_width=True, hide_index=True, column_config={
        'config': st.column_config.TextColumn('Config (path / URL)', width='large',
            help='Configured file/directory path or API URL. $NAME refers to a backend environment variable.')})
    selected = st.selectbox('Create or edit', [None]+list(source_names), format_func=lambda x: source_names.get(x,'Register a new source'))
    existing = next((s for s in sources if s['data_source_id'] == selected), {})
    key = f'{cid}:{selected or "new"}'
    config = existing.get('config', {})
    choices = ['FILE','DIRECTORY','HTTP_GET']
    transport = st.selectbox('Transport', choices, index=choices.index(existing.get('transport','FILE')), key=key+'transport')
    formats = ['CSV','JSON','XML','PNG','JPG','JPEG','PDF','IMAGE']
    fmt = st.selectbox('Data format', formats, index=formats.index(existing.get('data_format','CSV')), key=key+'format')
    catalog = fetch(base+'/fixtures')
    if catalog is None:
        return
    cfg = {}
    if transport == 'FILE':
        uploaded = st.file_uploader('Upload a fixture (maximum 25 MiB)', type=['csv','json','xml','pdf','png','jpg','jpeg'], key=key+'upload')
        if st.button('Store uploaded fixture', disabled=uploaded is None, key=key+'store'):
            result = request('POST', base+'/uploads', files={'file':(uploaded.name, uploaded.getvalue(), uploaded.type)})
            if result is not None:
                st.session_state[key+'uploaded_path'] = result.json()['path']
                st.session_state[key+'uploaded_name'] = result.json()['original_filename']
                st.rerun()
        allowed_ext = {'IMAGE':['.png','.jpg','.jpeg'], 'JPG':['.jpg','.jpeg'], 'JPEG':['.jpg','.jpeg']}.get(fmt, ['.'+fmt.lower()])
        paths = [p for p in catalog['paths'] if Path(p).suffix.lower() in allowed_ext]
        if not paths:
            st.info('Upload a file in the selected format.')
            return
        current = st.session_state.get(key+'uploaded_path') or config.get('path') or config.get('relative_path')
        cfg['path'] = st.selectbox('Fixture file', paths, index=paths.index(current) if current in paths else 0, key=key+fmt+'path')
        if cfg['path'] == st.session_state.get(key+'uploaded_path'):
            cfg['original_filename'] = st.session_state[key+'uploaded_name']
        elif cfg['path'] == config.get('path') and config.get('original_filename'):
            cfg['original_filename'] = config['original_filename']
        if fmt == 'CSV':
            cfg['delimiter'] = st.selectbox('CSV delimiter', [',',';','\t'], index=1 if config.get('delimiter') == ';' else 0, key=key+'delimiter')
    elif transport == 'DIRECTORY':
        use_images = st.checkbox('Use configured POC_IMAGES_DIR', value=config.get('env_dir') == 'POC_IMAGES_DIR' or not config, key=key+'images')
        if use_images:
            cfg['env_dir'] = 'POC_IMAGES_DIR'
        else:
            cfg['path'] = st.text_input('Server directory within approved fixture roots', value=config.get('path','poc_demo/fixtures/images'), key=key+'dir')
    else:
        endpoints = ['/mock/erp/invoices','/mock/erp/invoices?variant=b','/mock/payments/transactions','/mock/payments/refunds',
                     '/mock/bank/transactions','/mock/erp/invoices.csv','/mock/erp/invoices.xml',
                     '/mock/bank/transactions.csv','/mock/documents/invoice-sample.pdf','/mock/erp/suppliers','/mock/erp/customers','/mock/bank/accounts','/api/invoices']
        from urllib.parse import urlsplit, parse_qs, urlencode
        parts = urlsplit(config.get('url',''))
        old_query = parse_qs(parts.query)
        current = parts.path+('?variant=b' if old_query.get('variant') == ['b'] else '')
        endpoint = st.selectbox('Approved mock endpoint', endpoints, index=endpoints.index(current) if current in endpoints else 0, key=key+'endpoint')
        cfg['url'] = catalog['mock_base_url']+endpoint
        if fmt == 'JSON' and endpoint.startswith(('/mock/erp/invoices','/mock/payments/','/mock/bank/transactions')):
            scenarios = ['success','empty','paginated','duplicates','new','updated','http500','http429','malformed']
            scenario = st.selectbox('Deterministic test scenario', scenarios, index=scenarios.index(old_query.get('scenario',['success'])[0]) if old_query.get('scenario',['success'])[0] in scenarios else 0, key=key+'scenario')
            cfg['url'] += ('&' if '?' in cfg['url'] else '?')+urlencode({'scenario':scenario})
            cfg['pagination'] = st.checkbox('Follow mock page numbers', value=config.get('pagination', scenario == 'paginated'), key=key+'pagination')
            default_id = 'document.reference' if 'variant=b' in endpoint else ('refund_id' if 'refunds' in endpoint else 'payment_id' if 'payments' in endpoint else 'transaction_id' if 'bank' in endpoint else 'invoice_id')
            cfg['records_path'] = st.text_input('Record array path', value=config.get('records_path','items'), key=key+'records')
            cfg['external_id_path'] = st.text_input('External record ID path', value=config.get('external_id_path', default_id), key=key+'identity')
    with st.form(key+'form'):
        code = st.text_input('Source code', value=existing.get('source_code','ui_demo'), max_chars=80)
        name = st.text_input('Source name', value=existing.get('name','My demonstration source'), max_chars=160)
        entities = ['INVOICE','PAYMENT','BANK_TRANSACTION']
        entity = st.selectbox('Entity type', entities, index=entities.index(existing.get('entity_type','INVOICE')))
        active = st.checkbox('Enabled', value=existing.get('is_active',True))
        mapping_text = st.text_area('Field mapping JSON (stored for future normalization)', value=json.dumps(existing.get('field_mapping',{}), indent=2))
        if st.form_submit_button('Save source', type='primary'):
            try:
                mapping = json.loads(mapping_text)
            except ValueError:
                st.error('Field mapping must be valid JSON.')
                return
            body = dict(source_code=code,name=name,transport=transport,data_format=fmt,entity_type=entity,config=cfg,field_mapping=mapping,is_active=active)
            response = request('PUT' if selected else 'POST', base+'/sources'+('/'+selected if selected else ''), json=body)
            if response is not None:
                st.success('Source saved in PostgreSQL. It can be executed immediately.')
                st.json(response.json())
    if existing:
        with st.expander('Registered source details'):
            st.json(existing)


def run_page():
    st.subheader('Acquisition Execution')
    st.caption('Counts include original files/HTTP responses and derived JSON records. RECORD artifacts retain external IDs.')
    if not sources:
        st.info('Register a source first.')
        return
    selected = st.selectbox('Select source', list(source_names), format_func=source_names.get)
    one, all_sources = st.columns(2)
    request_body = None
    if one.button('Run ingestion', type='primary'):
        request_body = {'source_id':selected}
    if all_sources.button('Run all active sources'):
        request_body = {}
    if request_body is not None:
        response = request('POST', base+'/runs', json=request_body)
        if response is not None:
            st.session_state['pending:'+cid] = response.json()['run_ids']
    @st.fragment(run_every=2)
    def progress():
        ids = st.session_state.get('pending:'+cid, [])
        if not ids:
            st.info('Choose a source and start an acquisition.')
            return
        rows = [fetch(base+'/runs/'+run_id) for run_id in ids]
        rows = [r for r in rows if r]
        done = sum(r['status'] != 'RUNNING' for r in rows)
        st.progress(done/len(ids), text=f'{done} of {len(ids)} executions finished')
        st.dataframe([{'Source':source_names.get(r['data_source_id'],r['data_source_id']), 'Status':r['status'],
                       'Acquired':r['attempted_count'], 'New artifacts':r['acquired_count'], 'Duplicates':r['duplicate_count'],
                       'Errors':r['error_count'], 'Duration (s)':r['duration_seconds']} for r in rows], use_container_width=True, hide_index=True)
        for row in rows:
            if row['error_message']:
                st.error(f"{source_names.get(row['data_source_id'],'Source')}: {row['error_message']}")
    progress()


def history_page():
    st.subheader('Ingestion History')
    source = source_filter('history_source')
    status = st.selectbox('Execution status',['All','RUNNING','SUCCEEDED','FAILED'])
    apply_dates = st.checkbox('Filter by date (UTC)')
    dates = st.columns(2)
    start = dates[0].date_input('From', key='start')
    end = dates[1].date_input('To', key='end')
    index = st.number_input('Results page', min_value=1, value=1, step=1, key='history_page')
    params = {'limit':100,'offset':(index-1)*100}
    if source:
        params['source_id'] = source
    if status != 'All':
        params['status'] = status
    if apply_dates:
        params.update(date_from=start.isoformat(),date_to=end.isoformat())
    response = request('GET', base+'/runs', params=params)
    if response is None:
        return
    rows = response.json()
    st.dataframe(rows,use_container_width=True,hide_index=True)
    if rows:
        selected = st.selectbox('Execution details',rows,format_func=lambda r:r['source_name']+' · '+r['ingestion_run_id'])
        st.json(selected)
        if selected['error_message']:
            st.error(selected['error_message'])


def explorer_page():
    st.subheader('Raw Data Explorer')
    source = source_filter('artifact_source')
    kind = st.selectbox('Artifact kind',['All','FILE','RESPONSE','RECORD'])
    index = st.number_input('Results page', min_value=1, value=1, step=1, key='artifact_page')
    params = {'limit':100,'offset':(index-1)*100}
    if source:
        params['source_id'] = source
    if kind != 'All':
        params['kind'] = kind
    response = request('GET', base+'/artifacts',params=params)
    if response is None:
        return
    rows = response.json()
    st.dataframe(rows,use_container_width=True,hide_index=True)
    if not rows:
        st.info('Run ingestion to acquire raw data.')
        return
    selected = st.selectbox('Select artifact',rows,format_func=lambda a:f"{a['source_name']} · {a['original_filename']} · {a['external_id'] or a['artifact_kind']} · {a['raw_artifact_id'][:8]}")
    st.json(selected)
    if st.button('Load preview (maximum 2 MiB)'):
        content = request('GET',base+'/artifacts/'+selected['raw_artifact_id']+'/content',params={'preview':True})
        if content is not None:
            payload = content.content
            mime = selected['mime_type'].split(';')[0]
            try:
                if mime == 'application/json':
                    st.json(json.loads(payload))
                elif mime == 'text/csv':
                    st.dataframe(pd.read_csv(io.BytesIO(payload),sep=None,engine='python',nrows=100),use_container_width=True)
                elif mime.startswith('image/'):
                    st.image(payload)
                elif 'xml' in mime:
                    st.code(payload.decode('utf-8',errors='replace'),language='xml')
                elif mime != 'application/pdf':
                    st.code(payload.decode('utf-8',errors='replace'))
            except Exception as exc:
                st.warning(f'Preview cannot interpret this artifact: {exc}')
                st.code(payload[:4096].decode('utf-8',errors='replace'))
            st.download_button('Download previewed artifact',payload,file_name=selected['original_filename'],mime=mime)
    if st.button('Prepare full download (maximum 25 MiB)'):
        content = request('GET',base+'/artifacts/'+selected['raw_artifact_id']+'/content',params={'preview':False})
        if content is not None:
            st.download_button('Download artifact',content.content,file_name=selected['original_filename'],mime=selected['mime_type'].split(';')[0])


def normalization_page():
    from app.normalization.dashboard import render
    render(st, base, sources, fetch, request, cid, section=page)


if stage == 'Week 2 — Normalization':
    normalization_page()
else:
    {'Overview':overview_page,'Data Sources':sources_page,'Run Ingestion':run_page,
     'Ingestion History':history_page,'Raw Explorer':explorer_page}[page]()
