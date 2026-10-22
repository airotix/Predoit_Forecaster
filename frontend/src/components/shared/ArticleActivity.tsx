export interface ArticleActivity {
 lastCustomerOrder:string|null;asOf:string|null;dormant:boolean;
 status:'recent'|'dormant'|'no_history'|'unknown';label:string;
}
export default function ActivityBadge({activity}:{activity?:ArticleActivity|null}){
 if(!activity||activity.status==='recent'||activity.status==='unknown')return null;
 return <span title={`Last customer order: ${activity.lastCustomerOrder||'none recorded'}. Data through ${activity.asOf||'unknown'}. Historical data remains in forecasting; this does not change Catalogue status.`} className="inline-flex rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-semibold text-brand-800">{activity.label}</span>;
}
