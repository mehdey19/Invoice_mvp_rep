import csv
from decimal import Decimal
import io
import json
from defusedxml.ElementTree import fromstring
from sqlalchemy import select
from app.integration_pipeline.models import ExtractionResult
from app.normalization.mapper import get_path


class ExtractionRequired(ValueError): pass


def xml_object(element):
    children=list(element)
    if not children: return element.text or ''
    output={}
    for child in children:
        value=xml_object(child)
        if child.tag in output:
            if not isinstance(output[child.tag],list): output[child.tag]=[output[child.tag]]
            output[child.tag].append(value)
        else: output[child.tag]=value
    return output


def records(engine,artifact,payload,source,mapping):
    fmt=artifact['data_format']
    if fmt in {'IMAGE','PNG','JPG','JPEG','PDF'}:
        with engine.connect() as conn:
            extracted=conn.execute(select(ExtractionResult.payload).where(ExtractionResult.company_id==artifact['company_id'],
                ExtractionResult.raw_artifact_id==artifact['raw_artifact_id'],ExtractionResult.status=='SUCCEEDED').order_by(ExtractionResult.created_at.desc()).limit(1)).scalar()
        if not extracted: raise ExtractionRequired('Extraction is required before this document can be normalized')
        yield 'extraction',extracted
    elif fmt=='CSV':
        text=payload.decode('utf-8-sig')
        reader=csv.DictReader(io.StringIO(text),delimiter=source['config'].get('delimiter',','),strict=True)
        if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)): raise ValueError('Missing or duplicate CSV headers')
        for i,row in enumerate(reader,2):
            if i>10001: raise ValueError('CSV record limit exceeded')
            if None in row: raise ValueError('CSV row has unexpected columns')
            yield f'row:{i}',row
    else:
        if fmt=='JSON': data=json.loads(payload,parse_float=Decimal)
        elif fmt=='XML':
            tree=fromstring(payload);data={tree.tag:xml_object(tree)}
        else: raise ValueError('Unsupported structured format')
        path=mapping.get('records_path')
        if artifact['artifact_kind']=='RESPONSE' and not path: path=source['config'].get('records_path')
        if path and artifact['artifact_kind']!='RECORD': data=get_path(data,path)
        if data is None: raise ValueError('Record selection path was not found')
        if isinstance(data,list):
            if len(data)>10000: raise ValueError('JSON record limit exceeded')
            for i,row in enumerate(data):
                if not isinstance(row,dict): raise ValueError('Expected record objects')
                yield f'item:{i}',row
        elif isinstance(data,dict): yield 'object',data
        else: raise ValueError('Expected an object or array')
