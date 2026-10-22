import type {BuyingEdit,BuyingRow} from './api/budget';

export function previewBuyingRows(rows:BuyingRow[],edits:Record<string,BuyingEdit>):BuyingRow[]{
 return rows.map(row=>{
  const edit=edits[row.id];if(!edit)return row;
  const quantity='quantity' in edit?edit.quantity??null:row.quantity;
  const quote='quoteId' in edit?row.quotes.find(q=>q.id===edit.quoteId):undefined;
  const cost='unitCost' in edit?edit.unitCost??null:quote?.unitCost??row.orderUnitCost;
  const price='unitPrice' in edit?edit.unitPrice??null:row.orderUnitPrice;
  const sellThrough=edit.sellThrough??row.sellThrough;
  const amount=(n:number|null,p:number|null)=>n===0?0:n==null||p==null?null:Math.round(n*p*100)/100;
  const sold=quantity==null?null:quantity*sellThrough/100;
  const turnover=amount(sold,price),cogs=amount(sold,cost);
  const margin=turnover==null||cogs==null?null:Math.round((turnover-cogs)*100)/100;
  return {...row,quantity,orderUnitCost:cost,orderUnitPrice:price,sellThrough,
   orderCost:amount(quantity,cost),orderTurnover:turnover,orderGrossMargin:margin,
   orderMarginRate:turnover&&margin!=null?margin/turnover*100:null};
 });
}

export function articlePreview(rows:BuyingRow[]){
 const active=rows.filter(r=>r.quantity==null||r.quantity>0);
 const total=(key:'orderCost'|'orderTurnover'|'orderGrossMargin')=>active.every(r=>r[key]!=null)?Math.round(active.reduce((sum,r)=>sum+(r[key]||0),0)*100)/100:null;
 const cost=total('orderCost'),turnover=total('orderTurnover'),margin=total('orderGrossMargin');
 return {purchaseCost:cost,turnover,grossMargin:margin,marginRate:turnover&&margin!=null?margin/turnover*100:null};
}
