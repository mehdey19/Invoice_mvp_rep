"""Week 2 pages, parallel to the existing Week 1 acquisition workspace."""
import json


def render(st,base,sources,fetch,request,cid,section='Run Normalization'):
    prefix=base+'/normalization'
    st.subheader(section)
    st.caption('Week 2 · process tracking: integration_pipeline · business records: canonical')
    if section=='Overview':
        summary=fetch(prefix+'/canonical-summary')
        if summary:
            columns=st.columns(4)
            for i,(name,count) in enumerate(summary['counts'].items()): columns[i%4].metric(name.replace('_',' ').title(),count)
        history=fetch(prefix+'/runs') or []
        st.dataframe(history,use_container_width=True,hide_index=True)
        st.caption('Counts above come from canonical tables. Run history comes from integration_pipeline.')
        return
    if section=='Canonical Explorer':
        entity=st.selectbox('Canonical table',['document','party','invoice','invoice_line','payment','payment_allocation','bank_transaction'])
        rows=fetch(prefix+'/canonical/'+entity)
        st.dataframe(rows or [],use_container_width=True,hide_index=True)
        if rows:
            selected=st.selectbox('Inspect canonical record',range(len(rows)),format_func=lambda i:str(next(iter(rows[i].values()))))
            st.json(rows[selected])
        return
    if section=='Normalization History':
        rows=fetch(prefix+'/runs') or []
        status=st.selectbox('Run status',['All','RUNNING','PREVIEWED','APPLIED','PARTIAL','NEEDS_REVIEW','FAILED'])
        if status!='All': rows=[r for r in rows if r['status']==status]
        st.dataframe(rows,use_container_width=True,hide_index=True)
        if rows:
            selected=st.selectbox('Inspect normalization run',rows,format_func=lambda r:r['normalization_run_id']+' · '+r['status'])
            details=fetch(prefix+'/runs/'+selected['normalization_run_id'])
            if details: st.json(details)
        return
    if not sources: st.info('Register a source in Week 1 first.');return
    selected=st.selectbox('Source to normalize',sources,format_func=lambda s:s['name'],key='norm_source:'+cid+':'+section)
    sid=selected['data_source_id']
    if section=='Image Extraction':
        config=fetch(prefix+'/ai-model')
        if config: st.json(config)
        artifacts=fetch(base+'/artifacts?source_id='+sid+'&limit=500') or []
        binary=[a for a in artifacts if a['data_format'] in ('PNG','JPEG','JPG','IMAGE','PDF')]
        if not binary: st.info('Select an acquired image/PDF source.');return
        image=st.selectbox('Document to extract',binary,format_func=lambda a:a['original_filename']+' · '+a['raw_artifact_id'][:8])
        if st.button('Extract image fields',disabled=not config or not config['enabled'] or image['data_format']=='PDF'):
            with st.spinner('Extracting visible invoice fields…'):
                response=request('POST',prefix+'/extractions/'+image['raw_artifact_id'])
            if response is not None: st.json(response.json())
        reviewed=st.text_area('Reviewed extraction JSON (existing OCR output or manual review)','{}')
        if st.button('Save reviewed extraction'):
            try: payload=json.loads(reviewed)
            except ValueError: st.error('Extraction must be valid JSON.');return
            response=request('POST',prefix+'/extractions/'+image['raw_artifact_id']+'/reviewed',json=payload)
            if response is not None: st.success('Extraction saved. Run normalization to validate its business fields.')
        st.dataframe(fetch(prefix+'/extractions') or [],use_container_width=True,hide_index=True)
        return
    profiles=fetch(prefix+'/profiles?source_id='+sid)
    if profiles is None: return
    current=st.selectbox('Mapping version',profiles,format_func=lambda p:f"Version {p['version']} · {p['target']}") if profiles else None
    mapping=current['mapping'] if current else fetch(prefix+'/profiles/'+sid+'/example')
    if section=='Mapping Profiles':
        if not mapping: return
        editor=st.text_area('Versioned mapping JSON',json.dumps(mapping,indent=2,ensure_ascii=False),height=420,
                            key='norm_mapping:'+sid+':'+str(mapping['version']))
        st.caption('Increment version to change an existing profile. company_id and provenance come from the backend.')
        if st.button('Save normalization profile'):
            try: parsed=json.loads(editor)
            except ValueError: st.error('Mapping must be valid JSON.');return
            response=request('POST',prefix+'/profiles/'+sid,json=parsed)
            if response is not None: st.success('Profile saved.');st.rerun()
        return
    if not current: st.info('Save a profile in Mapping Profiles before running normalization.')
    apply_valid=st.checkbox('Apply valid records after preview',value=False)
    updates=st.checkbox('Approve updates to existing records',value=False)
    one,all_sources=st.columns(2)
    body=None
    if one.button('Run normalization',disabled=not profiles,type='primary'):
        body={'source_id':sid,'version':current['version'],'apply_valid':apply_valid,'allow_updates':updates}
    if all_sources.button('Run all configured sources'):
        body={'apply_valid':apply_valid,'allow_updates':updates}
    if body is not None:
        response=request('POST',prefix+'/runs',json=body)
        if response is not None: st.session_state['norm_pending:'+cid]=response.json()['run_ids']
    @st.fragment(run_every=2)
    def progress():
        ids=st.session_state.get('norm_pending:'+cid,[])
        if not ids: st.info('Start a normalization run to inspect its result.');return
        rows=[fetch(prefix+'/runs/'+rid) for rid in ids];rows=[r for r in rows if r]
        done=sum(r['status']!='RUNNING' for r in rows)
        st.progress(done/len(ids),text=f'{done} of {len(ids)} normalization runs finished')
        st.dataframe([{k:r[k] for k in ('normalization_run_id','status','record_count','valid_count','applied_count','skipped_count','error_count')} for r in rows],use_container_width=True,hide_index=True)
        if rows:
            result=st.selectbox('Inspect run result',rows,format_func=lambda r:r['normalization_run_id']+' · '+r['status'])
            if result.get('error_message'): st.error(result['error_message'])
            if result['items']:
                item=st.selectbox('Inspect normalized record',result['items'],format_func=lambda i:f"{i['source_record_id'] or i['record_locator']} · {i['status']}")
                st.json(item)
            if st.button('Apply valid records',disabled=result['status']=='RUNNING' or not any(i['status']=='READY' for i in result['items'])):
                response=request('POST',prefix+'/runs/'+result['normalization_run_id']+'/apply',json={'allow_updates':updates})
                if response is not None: st.rerun()
    progress()
    st.caption('Refunds, conflicting values and incomplete documents remain visible for review. No automatic invoice allocations or bank matching are performed.')
