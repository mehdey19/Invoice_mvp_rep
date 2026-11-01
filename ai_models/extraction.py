import base64
from uuid import uuid4
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import insert,update,select
from app.integration_pipeline.models import ExtractionResult
from app.canonical.models.document import Document
from app.acquisition.services.artifact_service import read_artifact
from app.acquisition.services.source_service import identifier
from ai_models.registry import ROOT,PROMPT_VERSION,configuration,get_vision_model


class ExtractedInvoice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    invoice_number: str | None=None
    invoice_date: str | None=None
    due_date: str | None=None
    currency: str | None=None
    invoice_type: str | None=None
    subtotal_amount: str | None=None
    tax_amount: str | None=None
    total_amount: str | None=None
    supplier: dict | None=None
    customer: dict | None=None
    lines: list[dict]=Field(default_factory=list)


def save_extraction(engine,company_id,artifact_id,payload,provider='manual',model_name='manual-reviewed'):
    artifact,_=read_artifact(engine,company_id,artifact_id)
    if artifact['data_format'] not in {'PNG','JPG','JPEG','IMAGE','PDF'}: raise ValueError('Only binary invoice documents require extraction')
    data=ExtractedInvoice.model_validate(payload).model_dump(mode='json',exclude_none=True)
    rid=uuid4()
    with engine.begin() as conn:
        conn.execute(insert(ExtractionResult).values(extraction_result_id=rid,company_id=identifier(company_id),
            raw_artifact_id=identifier(artifact_id),provider=provider,model_name=model_name,prompt_version=PROMPT_VERSION,status='SUCCEEDED',payload=data))
        if artifact['document_id']:
            conn.execute(update(Document).where(Document.document_id==artifact['document_id'],Document.company_id==identifier(company_id)).values(processing_status='EXTRACTED'))
    return {'extraction_result_id':str(rid),'status':'SUCCEEDED','payload':data}


def extract_image(engine,company_id,artifact_id):
    artifact,payload=read_artifact(engine,company_id,artifact_id)
    if artifact['mime_type'].split(';')[0] not in {'image/png','image/jpeg'}: raise ValueError('Vision adapter accepts PNG/JPEG images; PDF rendering is a separate step')
    config=configuration()
    model=get_vision_model()  # no model is downloaded or contacted unless configured
    try:
        from langchain_core.messages import HumanMessage
        message=HumanMessage(content=[{'type':'text','text':(ROOT/'prompts/invoice_vision.txt').read_text()},
            {'type':'image_url','image_url':{'url':'data:'+artifact['mime_type'].split(';')[0]+';base64,'+base64.b64encode(payload).decode()}}])
        result=model.with_structured_output(ExtractedInvoice).invoke([message])
        data=result.model_dump(mode='json') if isinstance(result,BaseModel) else result
        return save_extraction(engine,company_id,artifact_id,data,'ollama',config['model'])
    except Exception as exc:
        with engine.begin() as conn:
            conn.execute(insert(ExtractionResult).values(extraction_result_id=uuid4(),company_id=identifier(company_id),
                raw_artifact_id=identifier(artifact_id),provider='ollama',model_name=config['model'],prompt_version=PROMPT_VERSION,
                status='FAILED',payload={},error_message=str(exc)[:2000]))
        raise ValueError('Image extraction failed; see the extraction history') from exc
