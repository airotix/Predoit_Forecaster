import type {RecommendationRow} from './api/forecast';

export interface RecommendationArticle {
 reference:string;name:string;colors:RecommendationRow[];
}

/** Group before filtering/paging so an article always retains all its colours. */
export function recommendationArticles(rows:RecommendationRow[]):RecommendationArticle[]{
 const articles=new Map<string,RecommendationArticle>();
 for(const row of rows){
  const [reference,color]=row.skuId.split('|');
  let article=articles.get(reference);
  if(!article){
   const name=(color&&row.skuName.endsWith(color)?row.skuName.slice(0,-color.length).replace(/\s*(?:—|â€”)\s*$/u,''):row.skuName).trim();
   article={reference,name,colors:[]};articles.set(reference,article);
  }
  article.colors.push(row);
 }
 for(const article of articles.values())article.colors.sort((a,b)=>a.skuId.split('|')[1].localeCompare(b.skuId.split('|')[1],'en',{numeric:true}));
 return [...articles.values()];
}

export function filterRecommendationArticles(articles:RecommendationArticle[],search:string,status:string,category:string){
 const query=search.trim().toLowerCase();
 return articles.filter(article=>(!query||`${article.reference} ${article.name} ${article.colors.map(c=>c.skuName+' '+c.skuId).join(' ')}`.toLowerCase().includes(query))
  &&(!status||article.colors.some(c=>c.status===status))&&(!category||article.colors.some(c=>c.category===category)));
}

/** Preserve unknown values instead of displaying a partial sum as a full total. */
export function completeQuantity(values:(number|null)[]):number|null{
 return values.length&&values.every(v=>v!==null)?values.reduce<number>((sum,value)=>sum+(value??0),0):null;
}
