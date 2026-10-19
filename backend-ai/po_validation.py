"""PO approval follows editing, with current inputs and cumulative budget checks.

Finalization is local: no supplier communication or Joolan write. Reviewer labels
are user entered until named backend authentication is implemented.
"""
import datetime as dt
import json
import math
import uuid

import budgeting
import purchase_draft
import purchase_orders as po
from order_constraints import violations,article_violations


def persist(conn,doc,previous):
    doc.update(version=doc['version']+1,updatedAt=po.now())
    conn.execute('INSERT INTO supplier_po_versions VALUES(?,?,?)',(doc['id'],doc['version']-1,previous))
    conn.execute('UPDATE supplier_purchase_orders SET version=?,status=?,payload=? WHERE id=?',
                 (doc['version'],doc['status'],json.dumps(doc),doc['id']))


def submit(conn,ident,version):
    doc=po._read(conn,ident)
    if type(version) is not int or version!=doc['version']:raise ValueError('PO changed. Reload before sending it for validation.')
    if doc['status'] not in ('draft','pending_validation'):raise ValueError('Only an editable PO can be sent for validation.')
    if not any(line['quantity'] and line['quantity']>0 for line in doc['lines']):raise ValueError('The PO needs at least one positive quantity.')
    if doc['status']=='draft':
        previous=json.dumps(doc);doc.update(status='pending_validation',submittedAt=po.now())
        persist(conn,doc,previous)
    return doc


def review(conn,ident,report):
    doc=po.view(conn,ident)
    if doc['status']=='validated':
        return dict(order=doc,blockers=[],warnings=['Final local PO; not sent to Joolan or the supplier.'],
                    budget=doc['validation']['budget'],source=doc['validation']['source'])
    current=purchase_draft.context(conn,doc['scenario'])
    blocks=[];warnings=[]
    if doc['status']!='pending_validation':blocks.append('Save the PO and send it to Order Validation first.')
    if doc['seasonId']!=current['seasonId'] or doc['forecastRun']!=current['forecastRun']:
        blocks.append('This PO belongs to another season or forecast publication. Reconcile it before finalization.')
    if doc['currency']!=report['summary']['currency']:blocks.append('The buying-budget currency changed. Reconcile this PO currency first.')
    if not doc['supplier'].strip():blocks.append('Select a supplier in the PO editor.')
    suppliers=report.get('supplierOptions',[])
    if suppliers and doc['supplier'] and doc['supplier'] not in suppliers:blocks.append('Select a supplier from the saved Joolan supplier list.')
    source_rows={(r['reference'],r['color'],r['size']):r for r in report['rows']}
    active=[]
    for line in doc['lines']:
        qty=line['quantity'];name=f"{line['reference']} / {line['color']} / {line['size']}"
        if qty is None or isinstance(qty,bool) or not isinstance(qty,(int,float)) or not math.isfinite(qty) or qty<0 or qty!=int(qty):
            blocks.append(name+': enter a nonnegative whole-unit quantity.');continue
        if qty==0:continue
        active.append(line)
        source=source_rows.get((line['reference'],line['color'],line['size']))
        if not source:blocks.append(name+': no longer in the current buying scope.');continue
        if source.get('purchasingBlocked'):blocks.append(name+': inactive or blocked for purchasing.')
        if source['stock'] is None or source['incoming'] is None:blocks.append(name+': stock or incoming supply is unresolved.')
        if source.get('requiresDeliveryReview'):blocks.append(name+': customer delivery commitments need reconciliation.')
        if source.get('requiresAssortmentReview') and not line.get('assortmentReviewed'):
            blocks.append(name+': launch/assortment estimate requires planner review in Budget Tracker.')
        blocks.extend(name+': '+issue for issue in violations(qty,source.get('orderingRules',{})))
        line['orderingRules']=source.get('orderingRules',{})
        lead=line['orderingRules'].get('leadTimeDays')
        if lead and source.get('needBy') and (dt.date.fromisoformat(doc['orderDate'])+dt.timedelta(days=lead)).isoformat()>source['needBy']:
            blocks.append(name+': supplier lead time misses the next customer delivery.')
        if line['unitCost'] is None:blocks.append(name+': purchase price is missing.')
        if line['unitPrice'] is None:blocks.append(name+': selling price is missing.')
        if line['marginRate'] is None:blocks.append(name+': gross margin cannot be calculated.')
        elif line['marginRate']<report['summary']['targetMargin']:blocks.append(name+': gross margin is below the target.')
        if line.get('fx'):
            try:
                if line.get('supplierUnitCost') is None or abs(po.budget_unit(line['supplierUnitCost'],line['fx'])-line['unitCost'])>.000001:
                    blocks.append(name+': supplier and budget currency prices do not reconcile.')
            except (ValueError,TypeError,KeyError,ArithmeticError):blocks.append(name+': recorded currency conversion is invalid.')
    if not active:blocks.append('The PO needs at least one positive quantity.')
    blocks.extend(article_violations(active).values())
    edited=any(any(line[field]!=line['original'][field] for field in ('quantity','unitCost','unitPrice','sellThrough')) or
               line.get('supplierUnitCost')!=line['original'].get('supplierUnitCost',line.get('supplierUnitCost')) for line in active)
    if edited and not doc['changeReason'].strip():blocks.append('Record a reason for the PO quantity or price changes in the PO editor.')
    peers=[json.loads(r[0]) for r in conn.execute("SELECT payload FROM supplier_purchase_orders WHERE season_id=? AND status<>'cancelled'",(doc['seasonId'],))]
    peers=[p for p in peers if p['scenario']==doc['scenario'] or p['status']=='validated']
    if any(p['currency']!=doc['currency'] for p in peers):blocks.append('Other active POs use another budget currency. Reconcile them before finalization.')
    amounts=po.totals([line for p in peers if p['currency']==doc['currency'] for line in p['lines']])
    summary=report['summary'];known=round(amounts['knownPurchaseCost']+summary['knownCommittedCost'],2)
    complete=amounts['purchaseCost'] is not None and summary['commitmentsComplete']
    budget=dict(currency=doc['currency'],amount=summary['seasonBudget'],targetMargin=summary['targetMargin'],
                poCost=doc['totals']['purchaseCost'],allPOCost=amounts['purchaseCost'],knownPOCost=amounts['knownPurchaseCost'],
                knownCommitments=summary['knownCommittedCost'],commitmentsComplete=summary['commitmentsComplete'],
                knownTotal=known,remaining=round(summary['seasonBudget']-known,2) if complete else None,
                provisionalRemaining=round(summary['seasonBudget']-known,2),overBudget=known>summary['seasonBudget'])
    if not summary['budgetConfigured']:blocks.append('Save the season buying budget first.')
    if not summary['commitmentsComplete']:blocks.append('Existing Joolan supplier commitments are incomplete; reconcile them before final approval.')
    if amounts['purchaseCost'] is None:blocks.append('Some active supplier POs have unresolved purchase costs.')
    if budget['overBudget']:blocks.append('Active supplier POs plus existing commitments exceed the buying budget.')
    if doc['totals']['marginRate'] is not None and doc['totals']['marginRate']<summary['targetMargin']:blocks.append('PO gross margin is below the target.')
    if doc['sourceChanged']:warnings.append('The Budget Tracker or source changed after PO creation. These checks use current source inputs; the PO retains its edited quantities and prices.')
    if any(line.get('fx') for line in active):warnings.append('Historical recorded FX is a planning assumption; supplier documents use native currency.')
    warnings.append('Quantities come from the saved buying plan. Confirm whether they represent gross demand or net new purchasing.')
    return dict(order=doc,blockers=sorted(set(blocks)),warnings=warnings,budget=budget,source=report['source'])


def finalize(conn,ident,body,report):
    doc=po._read(conn,ident)
    if type(body.get('version')) is not int or body['version']!=doc['version']:raise ValueError('PO changed. Reload its validation review.')
    if doc['status']!='pending_validation':raise ValueError('Send this PO to Order Validation before finalizing it.')
    reviewer,reason=body.get('reviewer'),body.get('reason')
    if not isinstance(reviewer,str) or not 1<=len(reviewer.strip())<=120:raise ValueError('Enter the reviewer name.')
    if not isinstance(reason,str) or not 1<=len(reason.strip())<=1000:raise ValueError('Record the reason for approving this PO.')
    if body.get('confirmed') is not True:raise ValueError('Confirm the supplier, quantities, prices and financial totals.')
    result=review(conn,ident,report)
    if result['blockers']:raise ValueError('Final validation blocked: '+'; '.join(result['blockers'][:8]))
    previous=json.dumps(doc)
    doc['validation']=dict(id=uuid.uuid4().hex,reviewer=reviewer.strip(),reason=reason.strip(),createdAt=po.now(),
        identityBasis='User-entered local reviewer label; not verified sign-in',budget=result['budget'],source=result['source'],
        totals=result['order']['totals'],confirmedSupplier=doc['supplier'],confirmedVersion=doc['version'],notice='Validated locally; not sent to Joolan or supplier.')
    doc['status']='validated';persist(conn,doc,previous)
    return doc


def install(app,connection):
    from fastapi import Body,HTTPException

    @app.post('/api/purchase-orders/{ident}/submit')
    def send_for_validation(ident:str,body:dict=Body(...)):
        conn=connection()
        try:
            po.ensure(conn)
            with conn:
                conn.execute('BEGIN IMMEDIATE');submit(conn,ident,body.get('version'))
            return po.view(conn,ident)
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(409,str(e)) from None
        finally:conn.close()

    def current_review(conn,ident):
        doc=po._read(conn,ident)
        if doc['status']=='validated':return review(conn,ident,{})
        report=budgeting.build_report(conn,doc['scenario'])
        return review(conn,ident,report)

    @app.get('/api/purchase-orders/{ident}/validation')
    def review_order(ident:str):
        conn=connection()
        try:return current_review(conn,ident)
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(409,str(e)) from None
        finally:conn.close()

    @app.post('/api/purchase-orders/{ident}/validate')
    def validate_order(ident:str,body:dict=Body(...)):
        conn=connection()
        try:
            from catalogue import sync
            sync(conn)
            doc=po._read(conn,ident);before=po.source_stamp(conn,doc['scenario'])
            report=budgeting.build_report(conn,doc['scenario'],sync_catalogue=False)
            with conn:
                conn.execute('BEGIN IMMEDIATE')
                if before!=po.source_stamp(conn,doc['scenario']):raise ValueError('Source inputs changed. Reload the PO review.')
                finalize(conn,ident,body,report)
            return po.view(conn,ident)
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(409,str(e)) from None
        finally:conn.close()

    @app.get('/api/purchase-orders/{ident}/final-export')
    def final_document(ident:str):
        conn=connection()
        try:
            if po._read(conn,ident)['status']!='validated':raise ValueError('Validate this PO in Order Validation before downloading the final document.')
            return po.export_csv(conn,ident)
        except ValueError as e:raise HTTPException(409,str(e)) from None
        finally:conn.close()
