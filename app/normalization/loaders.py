"""Company-scoped, transactional writes to the existing canonical models."""
import hashlib
import json
from uuid import uuid4,uuid5,NAMESPACE_URL
from sqlalchemy import select,delete,text
from sqlalchemy.orm import Session
from app.canonical.models import Party,Invoice,InvoiceLine,Payment,BankTransaction,Document,Company,PaymentAllocation
from app.integration_pipeline.models import SourceEntityLink,NormalizationItem,RawArtifact
from app.normalization.schemas import MODELS,clean_text


class NeedsReview(ValueError): pass


def party_for(db,company_id,source_id,data,role):
    if not data: return None
    company=db.get(Company,company_id)
    if company and clean_text(company.name).casefold()==clean_text(data.name).casefold(): return None
    values=data.model_dump(exclude={'external_id'},exclude_none=True)
    tax=values.get('tax_identifier')
    if tax:
        matches=list(db.scalars(select(Party).where(Party.company_id==company_id,Party.tax_identifier==tax)))
        if len(matches)>1: raise NeedsReview('Several parties have this tax identifier')
        if matches:
            party=matches[0]
            existing=party.party_type.value if hasattr(party.party_type,'value') else party.party_type
            if existing not in (role,'BOTH'): party.party_type='BOTH'
            return party
    # Without a trusted identifier, party identity is confined to this source.
    key=tax or f'{source_id}:{data.external_id or clean_text(data.name).casefold()}'
    pid=uuid5(NAMESPACE_URL,f'{company_id}:party:{key}')
    party=db.get(Party,pid)
    if party is None:
        party=Party(party_id=pid,company_id=company_id,party_type=role,**values);db.add(party)
    else:
        for k,v in values.items(): setattr(party,k,v)
        existing=party.party_type.value if hasattr(party.party_type,'value') else party.party_type
        if existing not in (role,'BOTH'): party.party_type='BOTH'
    db.flush()
    return party


def apply_item(engine,item_id,profile,allow_updates=False):
    with Session(engine) as db,db.begin():
        item=db.scalar(select(NormalizationItem).where(NormalizationItem.normalization_item_id==item_id).with_for_update())
        if item.status in ('APPLIED','SKIPPED'): return item.status
        if item.status!='READY': return item.status
        cid=item.company_id;sid=profile['data_source_id'];target=profile['target']
        model=MODELS[target].model_validate(item.normalized_payload)
        # Lock source identity and business key consistently for concurrent runs.
        key=hashlib.sha256(f'{cid}:{target}:{getattr(model,"invoice_number",item.source_record_id)}'.encode()).digest()[:8]
        db.execute(text('select pg_advisory_xact_lock(:key)'),{'key':int.from_bytes(key,'big',signed=True)})
        artifact=db.get(RawArtifact,item.raw_artifact_id)
        if artifact.external_id:
            latest=db.scalar(select(RawArtifact).where(RawArtifact.company_id==cid,RawArtifact.data_source_id==sid,
                RawArtifact.external_id==artifact.external_id,RawArtifact.artifact_kind==artifact.artifact_kind,
                RawArtifact.acquired_at>artifact.acquired_at).limit(1))
            if latest: raise NeedsReview('A newer raw version exists; preview that version before applying')
        link=db.scalar(select(SourceEntityLink).where(SourceEntityLink.company_id==cid,SourceEntityLink.data_source_id==sid,
            SourceEntityLink.target==target,SourceEntityLink.source_record_id==item.source_record_id).with_for_update())
        if link and link.input_checksum==item.input_checksum and link.mapping_version==profile['version']:
            item.status='SKIPPED';item.target_ids={k:str(getattr(link,k)) for k in ('invoice_id','payment_id','bank_transaction_id') if getattr(link,k)}
            return 'SKIPPED'
        if link and not allow_updates: raise NeedsReview('Existing record differs; explicit update approval is required')
        # This savepoint/transaction also rolls back party/line writes on errors.
        if target=='INVOICE':
            existing=db.get(Invoice,link.invoice_id) if link else None
            if existing is None:
                duplicates=list(db.scalars(select(Invoice).where(Invoice.company_id==cid,
                    Invoice.invoice_number==model.invoice_number,Invoice.invoice_type==model.invoice_type)))
                if duplicates: raise NeedsReview('Invoice number already exists in the company; review cross-source identity')
            supplier=party_for(db,cid,sid,model.supplier,'SUPPLIER')
            customer=party_for(db,cid,sid,model.customer,'CUSTOMER')
            values=model.model_dump(exclude={'company_id','provenance','supplier','customer','lines'})
            values.update(company_id=cid,document_id=artifact.document_id,
                          supplier_id=supplier.party_id if supplier else None,customer_id=customer.party_id if customer else None)
            record=existing or Invoice(invoice_id=uuid4(),**values)
            if existing:
                if db.scalar(select(PaymentAllocation.payment_allocation_id).where(PaymentAllocation.invoice_id==existing.invoice_id).limit(1)):
                    raise NeedsReview('Invoice has payment allocations; review changes before applying')
                for k,v in values.items(): setattr(record,k,v)
            else: db.add(record)
            db.flush()
            db.execute(delete(InvoiceLine).where(InvoiceLine.invoice_id==record.invoice_id))
            for i,line in enumerate(model.lines,1): db.add(InvoiceLine(invoice_id=record.invoice_id,line_number=i,**line.model_dump()))
            ids={'invoice_id':str(record.invoice_id)}
        elif target=='PAYMENT':
            party=party_for(db,cid,sid,model.party,'CUSTOMER' if model.payment_direction=='INCOMING' else 'SUPPLIER')
            values=model.model_dump(exclude={'company_id','provenance','party'})
            values.update(company_id=cid,party_id=party.party_id if party else None)
            record=db.get(Payment,link.payment_id) if link else None
            if record and db.scalar(select(PaymentAllocation.payment_allocation_id).where(PaymentAllocation.payment_id==record.payment_id).limit(1)):
                raise NeedsReview('Payment has invoice allocations; review changes first')
            if record:
                for k,v in values.items(): setattr(record,k,v)
            else: record=Payment(payment_id=uuid4(),**values);db.add(record)
            db.flush();ids={'payment_id':str(record.payment_id)}
        else:
            values=model.model_dump(exclude={'company_id','provenance'});values.update(company_id=cid,reconciliation_status='UNMATCHED')
            record=db.get(BankTransaction,link.bank_transaction_id) if link else None
            if record and record.matched_payment_id: raise NeedsReview('Bank transaction is matched; review changes first')
            if record:
                for k,v in values.items(): setattr(record,k,v)
            else: record=BankTransaction(bank_transaction_id=uuid4(),**values);db.add(record)
            db.flush();ids={'bank_transaction_id':str(record.bank_transaction_id)}
        if link is None:
            link=SourceEntityLink(source_entity_link_id=uuid4(),company_id=cid,data_source_id=sid,target=target,
                                  source_record_id=item.source_record_id);db.add(link)
        for k,v in ids.items():
            from uuid import UUID
            setattr(link,k,UUID(v))
        link.input_checksum=item.input_checksum;link.mapping_version=profile['version'];link.normalization_item_id=item_id
        from datetime import datetime,timezone
        link.updated_at=datetime.now(timezone.utc)
        item.target_ids=ids;item.status='APPLIED';item.applied_at=datetime.now(timezone.utc)
        return 'APPLIED'
