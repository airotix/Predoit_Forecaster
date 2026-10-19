import type {BuyingEdit,BuyingRow} from './api/budget';

export function updateBuyingEdit(previous:BuyingEdit|undefined,row:BuyingRow,name:keyof BuyingEdit,value:string):BuyingEdit {
 const next:BuyingEdit={...previous,id:row.id};
 if(name==='quoteId'){
  next.quoteId=value;
  delete next.supplier;
  // Selecting an order price adopts that price, not an earlier what-if cost.
  delete next.unitCost;
  if(value&&!next.reason?.trim())next.reason='Confirmed historical Joolan supplier-order price for this draft.';
 }else if(name==='supplier'){
  next.supplier=value;
  next.quoteId='';
 }else if(name==='reason')next.reason=value;
 else if(name==='assortmentReviewed')next.assortmentReviewed=value==='true';
 else if(name==='quantity'||name==='unitCost'||name==='unitPrice')next[name]=value.trim()===''?null:Number(value);
 else if(name==='sellThrough')next.sellThrough=Number(value);
 return next;
}
