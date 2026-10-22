import {describe,it,expect} from 'vitest';
import {articlePreview,previewBuyingRows} from './buyingPreview';
import type {BuyingRow} from './api/budget';
const row={id:'a',quantity:3,orderUnitCost:79,orderUnitPrice:null,sellThrough:100,quotes:[],orderCost:237,orderTurnover:null,orderGrossMargin:null,orderMarginRate:null} as unknown as BuyingRow;
describe('editable financial previews',()=>{
 it('shows turnover and margin as soon as the missing selling price is entered',()=>{
  const rows=previewBuyingRows([row],{a:{id:'a',unitPrice:129}});
  expect(articlePreview(rows)).toMatchObject({purchaseCost:237,turnover:387,grossMargin:150});
  expect(rows[0].orderMarginRate).toBeCloseTo(38.7596899);
  expect(row.orderUnitPrice).toBeNull();
 });
 it('keeps missing inputs unknown and includes all positive sizes',()=>{
  const second={...row,id:'b'};
  const rows=previewBuyingRows([row,second],{a:{id:'a',unitPrice:129}});
  expect(articlePreview(rows).turnover).toBeNull();
  expect(articlePreview(rows).purchaseCost).toBe(474);
 });
 it('recalculates quantities, costs and sell-through independently',()=>{
  const rows=previewBuyingRows([row],{a:{id:'a',quantity:4,unitCost:50,unitPrice:100,sellThrough:50}});
  expect(articlePreview(rows)).toEqual({purchaseCost:200,turnover:200,grossMargin:100,marginRate:50});
 });
 it('zero-quantity lines need no price; clearing a positive line price restores unknown',()=>{
  expect(articlePreview(previewBuyingRows([row],{a:{id:'a',quantity:0}})).purchaseCost).toBe(0);
  expect(articlePreview(previewBuyingRows([row],{a:{id:'a',unitPrice:null}})).turnover).toBeNull();
 });
});
