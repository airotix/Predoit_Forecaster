import {apiClient} from './client';
import type {BuyingSimulation,PriceReview,SupplierFX} from './budget';

export interface POTotals {purchaseCost:number|null;knownPurchaseCost:number;turnover:number|null;knownTurnover:number;grossMargin:number|null;marginRate:number|null;units:number|null;articles:number;variants:number;}
export interface POLine {
 id:string;reference:string;color:string;size:string;name:string;forecast:number;budgetQuantity:number;
 quantity:number|null;unitCost:number|null;unitPrice:number|null;sellThrough:number;
 original:{quantity:number|null;unitCost:number|null;unitPrice:number|null;sellThrough:number};
 sourceSupplier:string;purchaseSource:string;sellingSource:string;sourceChecks:string[];allocationReason:string;
 priceReview?:PriceReview|null;budgetPriceReview?:PriceReview|null;
 supplierCurrency?:string;supplierUnitCost?:number|null;supplierPurchaseCost?:number|null;fx?:SupplierFX|null;
 purchaseCost:number|null;turnover:number|null;grossMargin:number|null;marginRate:number|null;
}
export interface POSummary {id:string;number:string;supplier:string;status:'draft'|'pending_validation'|'validated'|'cancelled';version:number;currency:string;forecastRun:string;budgetVersion:number;createdAt:string;updatedAt:string;totals:POTotals;}
export interface PurchaseOrder extends Omit<POSummary,'totals'> {
 seasonId:string;seasonName:string;scenario:string;sourceRun:string;contextKey:string;
 supplierCurrency?:string;supplierTotals?:{currency:string;purchaseCost:number|null};
 orderDate:string;deliveryDate:string;shipTo:string;notes:string;changeReason:string;
 sourceChanged:boolean;checks:string[];sourceChecks:string[];lines:POLine[];totals:POTotals;
 budget:{amount:number;targetMargin:number;knownCommitments:number;commitmentsComplete:boolean};
 batch:POTotals&{orders:number;currency:string;buyingBudget:number;knownCommitments:number;commitmentsComplete:boolean;provisionalRemaining:number;remaining:number|null;overBudget:boolean};
 history:{version:number;updatedAt:string}[];
 validation?:{id:string;reviewer:string;reason:string;createdAt:string;identityBasis:string;notice:string;budget:POValidationBudget};
}
export interface POValidationBudget {currency:string;amount:number;targetMargin:number;poCost:number|null;allPOCost:number|null;knownPOCost:number;knownCommitments:number;commitmentsComplete:boolean;knownTotal:number;remaining:number|null;provisionalRemaining:number;overBudget:boolean;}
export interface POValidation {order:PurchaseOrder;blockers:string[];warnings:string[];budget:POValidationBudget;source:{runId?:string;historyThrough?:string};}
export type POEdit=Pick<POLine,'id'> & Partial<Pick<POLine,'quantity'|'unitCost'|'unitPrice'|'sellThrough'|'supplierUnitCost'>>;
export type POChanges=Partial<Pick<PurchaseOrder,'supplier'|'orderDate'|'deliveryDate'|'shipTo'|'notes'|'changeReason'|'status'>>&{version:number;edits?:POEdit[]};
export interface SellingPricePreview {version:number;changes:{id:string;reference:string;color:string;size:string;previous:number|null;unitPrice:number;source:string}[];protectedOverrides:number;notice:string;}
export const purchaseOrdersApi={
 sellingPrices:(id:string)=>apiClient.get<SellingPricePreview>(`/purchase-orders/${id}/selling-prices`),
 list:(seasonId:string,scenario:string)=>apiClient.get<{orders:POSummary[];suppliers:string[]}>('/purchase-orders',{season_id:seasonId,scenario}),
 read:(id:string)=>apiClient.get<PurchaseOrder>(`/purchase-orders/${id}`),
 create:(draft:BuyingSimulation,mode:'all'|'fitting'|'selected')=>apiClient.post<{created:string[];existing:string[];skippedVariants:number;notice:string}>('/purchase-orders',{scenario:draft.scenario,version:draft.draft?.version,forecastRun:draft.draft?.forecastRun,revision:draft.revision,mode}),
 save:(id:string,changes:POChanges)=>apiClient.put<PurchaseOrder>(`/purchase-orders/${id}`,changes),
 export:(id:string)=>apiClient.get<{filename:string;csv:string}>(`/purchase-orders/${id}/export`),
 submit:(id:string,version:number)=>apiClient.post<PurchaseOrder>(`/purchase-orders/${id}/submit`,{version}),
 validation:(id:string)=>apiClient.get<POValidation>(`/purchase-orders/${id}/validation`),
 validate:(id:string,version:number,reviewer:string,reason:string,confirmed:boolean)=>apiClient.post<PurchaseOrder>(`/purchase-orders/${id}/validate`,{version,reviewer,reason,confirmed}),
 finalExport:(id:string)=>apiClient.get<{filename:string;csv:string}>(`/purchase-orders/${id}/final-export`),
};

export function downloadPO(filename:string,csv:string){
 const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
 const link=document.createElement('a');link.href=url;link.download=filename;link.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
