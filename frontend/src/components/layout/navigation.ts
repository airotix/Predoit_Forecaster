import {Settings2,LayoutDashboard,Users,ChartNoAxesCombined,TrendingUp,Package,Wallet,ClipboardCheck,BookOpen,Layers,FileText} from 'lucide-react';
import {roleMeetsRequired,routeMinRole,type PreduitRole} from '@/lib/auth/msalConfig';
export const navigation=[
 {label:'Season Setup',href:'/setup',group:'Workspace',description:'Manage Joolan exports, warehouse stock and seasonal forecasting.',icon:Settings2},
 {label:'Dashboard',href:'/dashboard',group:'Workspace',description:'See the season overview and recent planning activity.',icon:LayoutDashboard},
 {label:'SKU Catalogue',href:'/catalogue',group:'Workspace',description:'Save SKU purchase and selling prices for forecasting and budgets.',icon:BookOpen},
 {label:'Business Scope',href:'/scope',group:'Workspace',description:'Set current brands and classify primary, clearance, faulty and consignment stock.',icon:Settings2},
 {label:'Customer Coverage',href:'/customers',group:'Insights',description:'Explore customer activity and original order history.',icon:Users},
 {label:'Product KPIs',href:'/products',group:'Insights',description:'Compare product demand, reach and repeat buying.',icon:ChartNoAxesCombined},
 {label:'Demand Projection',href:'/projection',group:'Forecasting',description:'Compare demand scenarios and article breakdowns.',icon:TrendingUp},
 {label:'Seasonal Allocation',href:'/allocation',group:'Forecasting',description:'Select article season codes and view forecast quantities for a date interval.',icon:Layers},
 {label:'SKU Recommendations',href:'/recommendations',group:'Forecasting',description:'Review and adjust purchase quantities by size.',icon:Package},
 {label:'Budget Tracker',href:'/budget',group:'Buying',description:'Simulate costs, selling prices, margins and budget allocation.',icon:Wallet},
 {label:'Purchase Orders',href:'/purchase-orders',group:'Buying',description:'Create editable supplier PO drafts from saved budget quantities.',icon:FileText},
 {label:'Order Validation',href:'/validation',group:'Buying',description:'Validate supplier POs and download final purchase orders.',icon:ClipboardCheck},
 {label:'Settings & access',href:'/settings',group:'Workspace',description:'Manage your profile and team access.',icon:Settings2},
];
export const navigationForRole=(role:PreduitRole)=>navigation.filter(item=>roleMeetsRequired(role,routeMinRole(item.href)||'worker'));
