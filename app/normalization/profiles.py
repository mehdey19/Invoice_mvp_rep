from copy import deepcopy
from uuid import uuid4
from sqlalchemy import select
from app.integration_pipeline.models import NormalizationProfile
from app.acquisition.services.source_service import get_source,list_sources,identifier
from app.normalization.mapper import validate_profile


def save_profile(engine,company_id,source_id,mapping):
    source=get_source(engine,company_id,source_id)
    validate_profile(mapping)
    if mapping['target']!=source['entity_type']: raise ValueError('Mapping target must match the source entity type')
    with engine.begin() as conn:
        existing=conn.execute(select(NormalizationProfile.__table__).where(
            NormalizationProfile.company_id==identifier(company_id),NormalizationProfile.data_source_id==identifier(source_id),
            NormalizationProfile.version==mapping['version'])).mappings().first()
        if existing:
            if existing['mapping']!=mapping: raise ValueError('Mapping versions are immutable; increment version to change rules')
            return dict(existing)
        values=dict(profile_id=uuid4(),company_id=identifier(company_id),data_source_id=identifier(source_id),
                    version=mapping['version'],target=mapping['target'],mapping=mapping)
        return dict(conn.execute(NormalizationProfile.__table__.insert().values(**values).returning(NormalizationProfile.__table__)).mappings().one())


def get_profile(engine,company_id,source_id,version=None):
    get_source(engine,company_id,source_id)
    query=select(NormalizationProfile.__table__).where(NormalizationProfile.company_id==identifier(company_id),
        NormalizationProfile.data_source_id==identifier(source_id))
    if version is not None: query=query.where(NormalizationProfile.version==version)
    with engine.connect() as conn:
        row=conn.execute(query.order_by(NormalizationProfile.version.desc()).limit(1)).mappings().first()
    if not row: raise LookupError('No normalization profile registered for this source')
    return dict(row)


def rule(paths,transform=None,required=False,**params):
    return dict(paths=paths,**({'transform':transform} if transform else {}),**({'required':True} if required else {}),**params)


def example_profile(source):
    target=source['entity_type'];code=source['source_code'];fmt=source['data_format']
    mapping={'target':target,'version':1,'identity':{'paths':[]},'fields':{}}
    f=mapping['fields']
    if target=='INVOICE':
        mapping['identity']['paths']=['invoice_id','id','external_id','Numero','N_Facture','number','invoice_number','bill.ref','document.reference','Invoice.InvoiceNo','invoice.reference']
        f.update(invoice_number=rule(['invoice_number','Numero','N_Facture','number','document.reference','bill.ref','Invoice.InvoiceNo','invoice.reference'],'trim',True),
                 invoice_date=rule(['invoice_date','Date','Date_Facture','date','document.issued_at','bill.issued_on','Invoice.IssueDate'],'date',True),
                 due_date=rule(['due_date','Date_Echeance','document.due_at','bill.payment_due','Invoice.DueDate'],'date'),
                 currency=rule(['currency','Devise','currency_code','document.currency','bill.currency_code','Invoice.Currency','invoice.currency'],'uppercase',True),
                 total_amount=rule(['total_amount','Montant_TTC','Total_TTC','total','amount_total','amounts.total_including_tax','summary.gross_ttc','Invoice.Totals.PayableAmount','invoice.total'],'decimal',True),
                 subtotal_amount=rule(['subtotal_amount','subtotal','Total_HT','amounts.subtotal','summary.net_ht','Invoice.Totals.Subtotal'],'decimal'),
                 tax_amount=rule(['tax_amount','taxes','TVA','amounts.tax','summary.vat','Invoice.Totals.Tax'],'decimal'),
                 invoice_type={'constant':'PAYABLE' if 'purchase' in code or 'foreign' in code else 'RECEIVABLE'},
                 **{'supplier.name':rule(['supplier.name','supplier','vendor.legal_name','Invoice.Seller.Name'],'trim'),
                    'supplier.tax_identifier':rule(['supplier.ice','supplier.tax_identifier','vendor.tax_id'],'trim'),
                    'customer.name':rule(['Client','customer.name','customer','partner.name','buyer.name','Invoice.Buyer.Name','invoice.customer'],'trim'),
                    'customer.tax_identifier':rule(['ICE_Client','customer.tax_identifier'],'trim')})
        if 'purchase' in code:
            mapping['lines']={'path':'items','fields':{'description':rule(['label'],'trim',True),'quantity':rule(['qty'],'number'),
                'unit_price':rule(['unit_price_ht'],'decimal'),'tax_rate':rule(['vat_rate_percent'],'number'),'line_subtotal':rule(['amount_ht'],'decimal')}}
        if 'foreign' in code:
            mapping['lines']={'path':'Invoice.Lines.Line','fields':{'description':rule(['Description'],'trim',True),
                'quantity':rule(['Quantity'],'number'),'unit_price':rule(['UnitNet'],'decimal'),'line_subtotal':rule(['Net'],'decimal')}}
        if 'sales_detailed_csv' in code:
            for key in ('total_amount','subtotal_amount','tax_amount'): f[key]['decimal_separator']=','
        if fmt in {'IMAGE','PNG','JPG','JPEG','PDF'}:
            # AI extraction produces the same explicit business field names.
            f.update(invoice_date=rule(['invoice_date'],'date',True))
            mapping['lines']={'path':'lines','fields':{key:rule([key],'trim' if key=='description' else 'number') for key in
                ('description','quantity','unit_price','tax_rate','line_subtotal','line_tax_amount','line_total')}}
    elif target=='PAYMENT':
        mapping['identity']['paths']=['payment_id','id','reference']
        f.update(payment_date=rule(['transaction_date','payment_date','date'],'date',True),
                 amount=rule(['amount'],'decimal',True),currency=rule(['currency'],'uppercase',True),
                 payment_direction={'constant':'INCOMING'},reference=rule(['reference'],'trim'),
                 payment_method=rule(['method','payment_method'],'enum',values={x:x for x in ('BANK_TRANSFER','CARD','CASH','CHECK','DIRECT_DEBIT','OTHER')}),
                 status=rule(['status'],'enum',True,values={'SUCCESSFUL':'CONFIRMED','PENDING':'PENDING',
                                                                        'CONFIRMED':'CONFIRMED','CANCELLED':'CANCELLED'}),
                 **{'party.name':rule(['counterparty','party.name'],'trim')})
        if 'refund' in code: mapping['review_reason']='Refund events require an explicit refund business representation'
    else:
        mapping['identity']['paths']=['transaction_id','Reference','reference','id']
        f.update(transaction_date=rule(['booking_date','transaction_date','Date','Date_operation'],'date',True),
                 value_date=rule(['value_date'],'date'),amount=rule(['amount','Montant'],'decimal',True),
                 currency=rule(['currency','Devise'],'uppercase',True),direction=rule(['direction','Sens'],'uppercase'),
                 description=rule(['description','Libelle','Libellé'],'trim'),reference=rule(['reference','Reference','transaction_id'],'trim'),
                 counterparty_name=rule(['counterparty'],'trim'),bank_account_reference=rule(['account_reference'],'trim'))
        if code=='demo_bank_csv':
            mapping['direction_from_amount']=True
            f['amount']['decimal_separator']=','
    if code=='demo_invoice_api': mapping['records_path']='invoices'
    # Support original legacy field aliases as explicitly configured paths.
    for target_field,path in source.get('field_mapping',{}).items():
        if target_field=='external_id': mapping['identity']['paths'].insert(0,path)
        elif target_field in f and 'paths' in f[target_field]: f[target_field]['paths']=list(dict.fromkeys([path]+f[target_field]['paths']))
    return mapping


def seed_profiles(engine,company_id):
    count=0
    for source in list_sources(engine,company_id):
        if source['source_code'].startswith(('demo_','poc_w1_')):
            try: get_profile(engine,company_id,source['data_source_id'])
            except LookupError:
                save_profile(engine,company_id,source['data_source_id'],example_profile(source));count+=1
    return count
