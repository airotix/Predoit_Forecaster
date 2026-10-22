import type {ArticleActivity} from '@/components/shared/ArticleActivity';
import {apiClient,ApiError} from './client';
export interface SupplierFX {unitCost:number;currency:string;nativeUnitCost:number;nativeCurrency:string;exchangeRate:number;method:string;rateSource:string;verificationId:string;notice:string;}
export interface BudgetSettings {
 brands:string[];warehouses:string[];sellingTariff:string;costField:'Prix_Achat'|'Prix_Achat_Moyen';costCurrency:string;tariffCurrency:string;
 costBasisVerified:boolean;tariffVerified:boolean;poCostsVerified:boolean;budgetConfigured:boolean;packRulesVerified?:boolean;orderingRules?:Record<string,{minUnits?:number;maxUnits?:number;minArticleUnits?:number;packSize?:number;leadTimeDays?:number;blocked?:boolean}>;
}
export interface BudgetSeason {id:string;name:string;startDate:string;endDate:string;currency:string;budget:number;targetMargin:number;}
export interface BudgetOptions {settings:BudgetSettings;season:BudgetSeason;brands:string[];warehouses:string[];
 tariffs:{code:string;name:string;exTax:boolean}[];currencies:{code:string;iso:string;name:string}[];observedCurrencyCodes:string[];sourceRun:string;operatingScope?:{brands:string[];warehouseRoles:Record<string,string>}|null;}
export interface BudgetVariant {
 activity?:ArticleActivity|null;purchasingBlocked?:boolean;catalogueStatus?:{active:boolean|null;reason:string};reference:string;color:string;size:string;name:string;category:string;forecast:number;stock:number|null;incoming:number|null;
 purchaseQuantity:number|null;manualOverride:number|null;unitCost:number|null;unitPrice:number|null;purchaseCost:number|null;revenue:number|null;grossMargin:number|null;marginPercent:number|null;missing:string[];requiresAssortmentReview?:boolean;requiresDeliveryReview?:boolean;futureDemand?:number|null;needBy?:string|null;orderingRules?:{minUnits?:number;maxUnits?:number;minArticleUnits?:number;packSize?:number;leadTimeDays?:number;blocked?:boolean};}
export interface BudgetOrder {orderId:string;orderNumber:string;supplier:string;reference:string;color:string;size:string;warehouse:string;status:string;receiptDate:string;
 ordered:number;delivered:number;outstanding:number;currency:string;nativeValue:number|null;value:number|null;unitCost:number|null;}
export interface BudgetReport {
 summary:{seasonBudget:number;budgetConfigured:boolean;knownPurchaseCost:number;totalPurchaseCost:number|null;knownCommittedCost:number;committedCost:number|null;
 knownBudgetUsage:number;budgetUsage:number|null;remainingBudget:number|null;remainingAfterKnown:number;purchaseComplete:boolean;commitmentsComplete:boolean;budgetComplete:boolean;
 knownTurnover:number;expectedTurnover:number|null;knownGrossMargin:number;grossMargin:number|null;grossMarginPercent:number|null;marginComplete:boolean;targetMargin:number;currency:string;overBudget:boolean;};
 settings:BudgetSettings;season:BudgetSeason;supplierOptions?:string[];fxPolicy?:{baseCurrency:string|null;pairs:Record<string,{sampleCount:number;verifiedAt:string;source:string}>};coverage:{variants:number;stockKnown:number;incomingKnown:number;costKnown:number;priceKnown:number;purchasePriced:number;};
 categories:{category:string;knownPurchaseCost:number;complete:boolean;variants:number;unpriced:number;marginPercent:number|null;}[];
 rows:BudgetVariant[];purchaseOrders:BudgetOrder[];unallocatedSupplierLines:number;supplierExceptions:{reason:string;orderId:string;orderNumber:string;supplier:string;reference:string;color:string;size:string;warehouse:string;receiptDate:string|null;}[];otherCurrencyCommitments:Record<string,number>;warnings:string[];financialComplete:boolean;
 source:{runId:string;historyThrough:string;inventoryAsOf:string|null;currencyAsOf:string|null;revision:string;};scenario:string;
}
function loadDraft(scenario:string){
 // Shared API handling coalesces reads by credentials and write generation,
 // so a season activation or price save cannot reuse an older in-flight draft.
 return apiClient.get<BuyingSimulation>('/budget/draft',{scenario})
  .catch((error:unknown)=>{if(error instanceof ApiError&&error.status===408)throw new Error('The buying plan took more than two minutes to load. Check that the backend is running, then reload the saved draft.');throw error;});
}
export const budgetApi={
 draft:loadDraft,
 reconciliation:(scenario:string,issue:string,search:string,offset:number)=>apiClient.get<PurchasingInputs>('/budget/reconciliation',{scenario,issue,search,offset,limit:25}),
 saveDraft:(simulation:BuyingSimulation,edits:BuyingEdit[],selected:string[],refreshPrices=false)=>apiClient.put<BuyingSimulation>('/budget/draft',{scenario:simulation.scenario,revision:simulation.revision,version:simulation.draft?.version,forecastRun:simulation.draft?.forecastRun,edits,selected,refreshPrices}),
 reviewDraft:(simulation:BuyingSimulation)=>apiClient.post<{id:string;notice:string}>('/budget/draft/review',{scenario:simulation.scenario,version:simulation.draft?.version,forecastRun:simulation.draft?.forecastRun}),
 approvePrices:(simulation:BuyingSimulation,selected:string[],reviewer:string,reason:string)=>apiClient.post<BuyingSimulation>('/budget/draft/prices/review',{scenario:simulation.scenario,version:simulation.draft?.version,forecastRun:simulation.draft?.forecastRun,revision:simulation.revision,selected,reviewer,reason}),
 reviews:()=>apiClient.get<BuyingReview[]>('/budget/reviews'),
 simulate:(scenario:string,edits:BuyingEdit[])=>apiClient.post<BuyingSimulation>('/budget/simulate',{scenario,edits,quantityBasis:'forecast'}),
 validate:(simulation:BuyingSimulation,edits:BuyingEdit[],selected:string[])=>apiClient.post<{id:string;notice:string}>('/budget/validate',{scenario:simulation.scenario,revision:simulation.revision,quantityBasis:simulation.quantityBasis,edits,selected}),
 report:(scenario:string)=>apiClient.get<BudgetReport>('/budget',{scenario}),
 options:()=>apiClient.get<BudgetOptions>('/budget/options'),
 save:(settings:Partial<BudgetSettings>)=>apiClient.put<BudgetSettings>('/budget/settings',settings),
 currencies:(apiKey:string)=>apiClient.post<{imported:number;notice:string}>('/budget/currencies',{apiKey}),
};
export interface BuyingEdit {id:string;quantity?:number|null;unitCost?:number|null;unitPrice?:number|null;sellThrough?:number;quoteId?:string;supplier?:string;reason?:string;assortmentReviewed?:boolean;}
export interface PriceReview {id:string;createdAt:string;reviewer:string;reason:string;draftVersion:number;}
export interface SupplierPriceOption {id:string;supplier:string;order:string;unitCost:number;date:string;currency?:string;source?:string;matchLevel?:string;requiresReview?:boolean;fx?:SupplierFX|null;}
export interface BuyingRow extends BudgetVariant {id:string;quantity:number|null;orderUnitCost:number|null;orderUnitPrice:number|null;sellThrough:number;expectedSold:number|null;
 orderCost:number|null;orderTurnover:number|null;orderGrossMargin:number|null;orderMarginRate:number|null;quotes:SupplierPriceOption[];
 supplier?:string;priceReviewRequired?:boolean;priceReview?:PriceReview|null;priceReviewFingerprint?:string;
 quoteId:string;costBasis:string;priceBasis?:string;reason:string;adjusted:boolean;blockers:string[];}
export interface PurchasingInputs {summary:Record<string,number>;affectedVariants:number;budgetVariants:number;total:number;offset:number;limit:number;currency:string;notice:string;source:BudgetReport['source'];fxPolicy:NonNullable<BudgetReport['fxPolicy']>;supplierExceptionCount:number;rows:{id:string;reference:string;name:string;color:string;size:string;quantity:number|null;inactive:boolean;issues:Record<string,string>;reasonCode?:string;purchaseCost:number|null;draftPurchaseCost:number|null;priceReview?:PriceReview|null;candidates:SupplierPriceOption[];otherCurrencyCandidates:{price:number;currency:string;supplier:string;orderId:string;orderDate:string}[]}[];}
export interface ArticleAllocation {activity?:ArticleActivity|null;reference:string;rowIds:string[];forecast:number;quantity:number;purchaseCost:number|null;turnover:number|null;grossMargin:number|null;marginRate:number|null;status:string;reason:string;rank:number|null;shortfall:number|null;}
export interface BuyingReview {id:string;createdAt:string;seasonId:string;scenario:string;currency:string;draftVersion?:number;forecastRun?:string;orders:BuyingRow[];notice:string;}
export interface PurchaseDraft {version:number;forecastRun:string;seasonId:string;updatedAt:string|null;edits:BuyingEdit[];selected:string[];stale:boolean;excludedEdits:number;supplierPriceChanged:boolean;currencyChanged?:boolean;}
export interface BuyingSimulation {draft?:PurchaseDraft;quantityBasis:string;articlePlan:{articles:ArticleAllocation[];capacity:number;remaining:number;purchaseCost:number;turnover:number;grossMargin:number;provisional:boolean;method:string};rows:BuyingRow[];context:BudgetReport;revision:string;scenario:string;currency:string;blockers:string[];
 covered:{rowIds:string[];supplierOrders:BudgetOrder[];recommendationCount:number;excludedRecommendations:number;supplierLines:number;excludedSupplierLines:number;
 purchaseCost:number;turnover:number;grossMargin:number;marginRate:number|null;commitments:number;balanceAfterCovered:number;fullPlanComplete:boolean;};
 summary:{knownOrderCost:number;totalOrderCost:number|null;knownTurnover:number;turnover:number|null;grossMargin:number|null;marginRate:number|null;knownCommitments:number;
 commitmentsComplete:boolean;budget:number;targetMargin:number;provisionalBalance:number;balance:number|null;overBudget:boolean;ready:number;orders:number;};}
