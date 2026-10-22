import {describe,it,expect} from 'vitest';
import type {RecommendationRow} from './api/forecast';
import {recommendationArticles,filterRecommendationArticles,completeQuantity} from './recommendationArticles';
const row=(skuId:string,status='pending')=>({skuId,skuName:'Jacket — '+skuId.split('|')[1],status,category:'Outerwear'} as RecommendationRow);

describe('article recommendation browsing',()=>{
 it('keeps nonadjacent colours together without merging distinct article references',()=>{
  const input=[row('001|RED'),row('1|BLACK'),row('001|BLACK')];
  const grouped=recommendationArticles(input);
  expect(grouped.map(a=>a.reference)).toEqual(['001','1']);
  expect(grouped[0].name).toBe('Jacket');
  expect(grouped[0].colors.map(c=>c.skuId)).toEqual(['001|BLACK','001|RED']);
  expect(input.map(c=>c.skuId)).toEqual(['001|RED','1|BLACK','001|BLACK']);
 });
 it('retains all colours when searching by colour or filtering a mixed article by status',()=>{
  const articles=recommendationArticles([row('A|RED','locked'),row('A|BLACK'),row('B|BLACK')]);
  expect(filterRecommendationArticles(articles,'RED','','')[0].colors).toHaveLength(2);
  expect(filterRecommendationArticles(articles,'','locked','Outerwear')[0].colors).toHaveLength(2);
  expect(filterRecommendationArticles(articles,'','locked','Footwear')).toHaveLength(0);
 });
 it('pages complete articles, preserving every size/colour row',()=>{
  const input=Array.from({length:51},(_,i)=>[row(`${i}|RED`),row(`${i}|BLACK`)]).flat();
  const articles=recommendationArticles(input);
  expect(articles.slice(0,50).flatMap(a=>a.colors)).toHaveLength(100);
  expect(articles.slice(50)[0].colors).toHaveLength(2);
 });
 it('keeps incomplete purchase totals unknown and real zeros as zero',()=>{
  expect(completeQuantity([4,null])).toBeNull();
  expect(completeQuantity([0,0])).toBe(0);
  expect(completeQuantity([4,6])).toBe(10);
 });
});
