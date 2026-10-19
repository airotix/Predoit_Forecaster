import {describe,it,expect} from 'vitest';
import {updateBuyingEdit} from './budgetEdits';
import type {BuyingRow} from './api/budget';
const row={id:'variant'} as BuyingRow;

describe('supplier and draft price changes',()=>{
 it('adopts the selected order price instead of retaining a previous cost override',()=>{
  const result=updateBuyingEdit({id:row.id,unitCost:2,supplier:'Other',unitPrice:120,quantity:4},row,'quoteId','stable-order');
  expect(result).toMatchObject({quoteId:'stable-order',unitPrice:120,quantity:4});
  expect(result).not.toHaveProperty('unitCost');expect(result).not.toHaveProperty('supplier');
  expect(result.reason).toContain('Confirmed historical');
 });
 it('manual supplier selection clears the previous quote without losing edited prices',()=>{
  const result=updateBuyingEdit({id:row.id,quoteId:'old',unitCost:42,reason:'Supplier agreed'},row,'supplier','New supplier');
  expect(result).toMatchObject({quoteId:'',supplier:'New supplier',unitCost:42,reason:'Supplier agreed'});
 });
 it('preserves unknown prices and explicit zero quantities',()=>{
  expect(updateBuyingEdit(undefined,row,'unitPrice','').unitPrice).toBeNull();
  expect(updateBuyingEdit(undefined,row,'quantity','0').quantity).toBe(0);
 });
});
