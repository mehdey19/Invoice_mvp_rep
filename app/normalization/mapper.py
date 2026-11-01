"""Declarative field mapping; no eval, code execution or guessed source locale."""
from datetime import date,datetime
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
import re
from app.normalization.schemas import clean_text,MODELS

TRANSFORMS={'trim','uppercase','date','decimal','number','enum'}
RESERVED={'company_id','provenance'}


def get_path(record,path):
    value=record
    for component in path.split('.'):
        if not isinstance(value,dict) or component not in value: return None
        value=value[component]
    return value


def validate_profile(mapping):
    if not isinstance(mapping,dict) or mapping.get('target') not in MODELS:
        raise ValueError('Mapping target must be INVOICE, PAYMENT or BANK_TRANSACTION')
    if type(mapping.get('version')) is not int or mapping['version']<1: raise ValueError('Mapping version must be a positive integer')
    fields=mapping.get('fields')
    if not isinstance(fields,dict) or not fields: raise ValueError('Mapping must contain fields')
    def validate_fields(fields,allowed):
        for target,rule in fields.items():
            if target.split('.')[0] in RESERVED or target.split('.')[0] not in allowed:
                raise ValueError('Unsupported or reserved target field: '+target)
            if not isinstance(rule,dict): raise ValueError('Each field rule must be an object')
            selectors=sum(key in rule for key in ('path','paths','constant'))
            if selectors!=1: raise ValueError('A field rule needs exactly one of path, paths or constant')
            paths=rule.get('paths',[rule.get('path')])
            if 'constant' not in rule and (not isinstance(paths,list) or not paths or any(not isinstance(p,str) or not re.fullmatch(r'[\w.-]+',p) for p in paths)):
                raise ValueError('Invalid field path')
            if rule.get('transform') and rule['transform'] not in TRANSFORMS: raise ValueError('Unsupported transform')
    validate_fields(fields,MODELS[mapping['target']].model_fields)
    identity=mapping.get('identity',{})
    if identity and (not isinstance(identity,dict) or not isinstance(identity.get('paths'),list) or not identity['paths']):
        raise ValueError('Identity requires an ordered paths list')
    lines=mapping.get('lines')
    if lines:
        from app.normalization.schemas import InvoiceLineData
        if mapping['target']!='INVOICE' or not isinstance(lines,dict) or not isinstance(lines.get('path'),str): raise ValueError('Invalid line collection mapping')
        validate_fields(lines.get('fields',{}),InvoiceLineData.model_fields)
    return mapping


def decimal_value(value,rule,quantize=True):
    if isinstance(value,bool): raise ValueError('Boolean is not an amount')
    text=clean_text(value)
    thousands=rule.get('thousands_separator')
    decimal=rule.get('decimal_separator','.')
    if thousands:
        if thousands==decimal: raise ValueError('Decimal and thousands separators must differ')
        text=text.replace(thousands,'')
    if decimal!='.':
        if '.' in text and thousands!='.': raise ValueError('Unexpected decimal separator')
        text=text.replace(decimal,'.')
    try:
        result=Decimal(text)
        if not result.is_finite() or abs(result)>=Decimal('10000000000000000'): raise ValueError('Amount outside numeric range')
        return result.quantize(Decimal('.01'),rounding=ROUND_HALF_UP) if quantize else result
    except InvalidOperation as exc: raise ValueError('Invalid decimal amount') from exc


def field_value(record,rule):
    if 'constant' in rule: value=rule['constant']
    else:
        candidates=[get_path(record,path) for path in rule.get('paths',[rule.get('path')])]
        populated=[x for x in candidates if x is not None and x!='']
        if rule.get('transform'):
            populated=[x for x in populated if not isinstance(x,(dict,list))]
        if not populated:
            if rule.get('required'): raise ValueError('Required field is missing')
            return None
        value=populated[0]
        if any(clean_text(x)!=clean_text(value) for x in populated[1:]): raise ValueError('Alternative paths contain conflicting values')
    if value is None: return None
    transform=rule.get('transform')
    if transform=='trim': return clean_text(value)
    if transform=='uppercase': return clean_text(value).upper()
    if transform in {'decimal','number'}: return decimal_value(value,rule,quantize=transform=='decimal')
    if transform=='date':
        if isinstance(value,date) and not isinstance(value,datetime): return value
        return datetime.strptime(clean_text(value),rule.get('format','%Y-%m-%d')).date()
    if transform=='enum':
        key=clean_text(value).upper()
        values=rule.get('values',{})
        if key not in values: raise ValueError('Unmapped source status/value: '+key)
        return values[key]
    return value


def map_fields(record,fields):
    output={};errors=[]
    for target,rule in fields.items():
        try:
            value=field_value(record,rule)
            if value is None: continue
            node=output;parts=target.split('.')
            for part in parts[:-1]: node=node.setdefault(part,{})
            node[parts[-1]]=value
        except (ValueError,TypeError,KeyError) as exc: errors.append({'field':target,'message':str(exc)})
    return output,errors


def normalize(record,mapping,company_id,provenance):
    output,errors=map_fields(record,mapping['fields'])
    lines=mapping.get('lines')
    if lines:
        source=get_path(record,lines['path']) or []
        if isinstance(source,dict): source=[source]
        if not isinstance(source,list): errors.append({'field':'lines','message':'Expected an array'})
        else:
            output['lines']=[]
            for i,line in enumerate(source):
                mapped,line_errors=map_fields(line,lines['fields']);output['lines'].append(mapped)
                errors += [dict(e,field=f"lines[{i}]."+e['field']) for e in line_errors]
    if mapping.get('direction_from_amount') and 'amount' in output:
        output['direction']='DEBIT' if output['amount']<0 else 'CREDIT';output['amount']=abs(output['amount'])
    if errors: return {},errors
    try:
        result=MODELS[mapping['target']].model_validate(dict(output,company_id=company_id,provenance=provenance))
        return result.model_dump(mode='json'),[]
    except Exception as exc:
        if hasattr(exc,'errors'):
            return {},[{'field':'.'.join(map(str,e['loc'])),'message':e['msg']} for e in exc.errors()]
        return {},[{'field':'record','message':str(exc)}]
