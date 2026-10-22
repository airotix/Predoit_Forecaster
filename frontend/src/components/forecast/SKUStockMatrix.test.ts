import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {describe,it,expect,vi} from 'vitest';
import {SKUStockMatrix} from './SKUStockMatrix';
import type {SKUDetailedProjection} from '@/types/stockMatrix';

vi.mock('@phosphor-icons/react',()=>({CaretDownIcon:()=>null,DropIcon:()=>null}));

function fixture():SKUDetailedProjection{
 return {
  skuId:'SKU-P',skuName:'Jacket',category:'Outerwear',scenario:'base',confidence:'low',projectionBasis:'season_bookings',
  productInfo:{reference:'P',name:'Jacket',matiere:'Leather',theme:'',famille:'Outerwear',sousFamille:'',rayon:'',saison:'CORE'},
  stockSummary:{stockReel:9,fournisseur:444,clientNegoce:2,total:453},
  colorVariants:[{color:'BLACK',availableStock:{S:9},totalDeFournisseur:{S:444},totalDeProduit:{S:3},totalDeCitNegoce:{S:2},recommendedQty:{S:12},totalDeLeStock:{S:8}}],
  warehouseStock:{sourceRun:'source',source:'query.do:stocks',snapshotAt:'2026-10-19T12:00:00Z',warehouses:['CENTRAL'],totalVariants:1,completeVariants:1,missingVariants:0,
   summary:{stock:6,toReceive:777,clients:3,allocated:1,theoretical:779,available:5},
   recordedSummary:{stock:6,toReceive:777,clients:3,allocated:1,theoretical:779,available:5},
   colors:[{color:'BLACK',stock:{S:6},toReceive:{S:777},clients:{S:3},allocated:{S:1},theoretical:{S:779},available:{S:5}}]},
 };
}
const render=(data:SKUDetailedProjection)=>renderToStaticMarkup(React.createElement(SKUStockMatrix,{data}));
const main=(html:string)=>html.split('<details')[0];
const body=(html:string)=>main(html).split('<tbody')[1].split('</tbody>')[0];
const row=(html:string,label:string)=>body(html).split('<tr').find(value=>value.includes('>'+label+'<'))||'';

describe('forecast stock matrix layout and source mapping',()=>{
 it('keeps all six original rows together before collapsed source details',()=>{
  const html=render(fixture());
  expect((body(html).match(/<tr/g)||[])).toHaveLength(6);
  for(const label of ['Available stock','Incoming supply','Season booked units','Delivered against season bookings','Forecast demand','Net purchase quantity'])expect(row(html,label)).not.toBe('');
  expect(main(html)).not.toContain('>Attribué<');
  expect(html.split('<details')[1]).not.toMatch(/^\s+open[\s>]/);
 });
 it('uses full À recevoir and Disponible, preserving published forecast and net quantities',()=>{
  const html=render(fixture());
  expect(row(html,'Incoming supply')).toContain('>777<');
  expect(row(html,'Incoming supply')).not.toContain('>444<');
  expect(row(html,'Available stock')).toContain('>5<');
  expect(row(html,'Forecast demand')).toContain('>12<');
  expect(row(html,'Net purchase quantity')).toContain('>8<');
  expect(html.split('<details')[1]).toContain('>444<');
 });
 it('keeps source gaps unknown instead of substituting scheduled receipts or hiding forecasts',()=>{
  const data=fixture();data.warehouseStock=null;
  const html=render(data);
  expect(row(html,'Incoming supply')).toContain('Unknown');
  expect(row(html,'Incoming supply')).not.toContain('>444<');
  expect(row(html,'Forecast demand')).toContain('>12<');
  expect(row(html,'Net purchase quantity')).toContain('>8<');
 });
 it('retains genuine zero receipts and isolates catalogue-only sizes to source details',()=>{
  const data=fixture();const color=data.warehouseStock!.colors[0];
  color.toReceive.S=0;color.toReceive.XS=100;color.stock.XS=100;
  const html=render(data);
  expect(row(html,'Incoming supply')).toContain('>0<');
  expect(row(html,'Incoming supply')).not.toContain('>100<');
  expect(main(html)).not.toContain('>XS<');
  expect(html.split('<details')[1]).toContain('>XS<');
  expect(row(html,'Forecast demand')).toContain('>12<');
 });
});
