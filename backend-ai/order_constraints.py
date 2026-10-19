"""Validated client ordering rules; absent industrial data stays unspecified."""
import math

FIELDS={'minUnits','maxUnits','minArticleUnits','packSize','leadTimeDays','blocked'}


def validate_rules(rules):
    if not isinstance(rules,dict) or len(rules)>2000:raise ValueError('Ordering rules must be a map of up to 2000 article or variant identities.')
    for identity,rule in rules.items():
        if not isinstance(identity,str) or not identity or not isinstance(rule,dict) or set(rule)-FIELDS:raise ValueError('Unsupported ordering rule.')
        for name,value in rule.items():
            if name=='blocked':
                if type(value) is not bool:raise ValueError('Blocked must be true or false.')
            elif isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0 or (name=='packSize' and value<=0):
                raise ValueError('Ordering quantities and lead times must be finite and nonnegative; pack size must be positive.')
        if rule.get('maxUnits',math.inf)<rule.get('minUnits',0):raise ValueError('Maximum order cannot be less than minimum order.')
    return rules


def applicable(config,reference,variant_identity,source_pack=None):
    rules={**config.get('orderingRules',{}).get(reference,{}),**config.get('orderingRules',{}).get(variant_identity,{})}
    if 'packSize' not in rules and config.get('packRulesVerified') and source_pack is not None and source_pack>0:rules['packSize']=source_pack
    return rules


def propose(quantity,rules):
    if quantity is None:return None
    if rules.get('blocked'):return 0.
    if quantity<=0:return 0.
    quantity=max(quantity,rules.get('minUnits',0))
    pack=rules.get('packSize',1.)
    return math.ceil(quantity/pack-1e-10)*pack


def violations(quantity,rules):
    if quantity is None or quantity<=0:return []
    result=[]
    if rules.get('blocked'):result.append(rules.get('blockedReason') or 'Variant is blocked for ordering')
    if quantity<rules.get('minUnits',0):result.append('Below minimum order quantity')
    if quantity>rules.get('maxUnits',math.inf):result.append('Above maximum order quantity')
    pack=rules.get('packSize')
    if pack and abs(quantity/pack-round(quantity/pack))>1e-7:result.append('Order quantity does not match the verified pack multiple')
    return result


def article_violations(rows):
    groups={}
    for row in rows:
        if row.get('quantity') and row['quantity']>0:groups.setdefault(row['reference'],[]).append(row)
    result={}
    for reference,items in groups.items():
        minimum=max((r.get('orderingRules',{}).get('minArticleUnits',0) for r in items),default=0)
        if sum(r['quantity'] for r in items)<minimum:result[reference]='Selected article quantities are below the article minimum order'
    return result
