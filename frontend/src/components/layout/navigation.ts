import {BookOpenIcon,ChartBarIcon,ClipboardTextIcon,DatabaseIcon,FileTextIcon,GearSixIcon,PackageIcon,SlidersHorizontalIcon,SquaresFourIcon,StackIcon,TrendUpIcon,UsersThreeIcon,WalletIcon} from '@phosphor-icons/react';
import {roleMeetsRequired,routeMinRole,type PreduitRole} from '@/lib/auth/msalConfig';
export const navigation=[
 {label:'Season Setup',href:'/setup',group:'Workspace',description:'Manage Joolan exports, warehouse stock and seasonal forecasting.',icon:DatabaseIcon},
 {label:'Dashboard',href:'/dashboard',group:'Workspace',description:'See the season overview and recent planning activity.',icon:SquaresFourIcon},
 {label:'SKU Catalogue',href:'/catalogue',group:'Workspace',description:'Save SKU purchase and selling prices for forecasting and budgets.',icon:BookOpenIcon},
 {label:'Business Scope',href:'/scope',group:'Workspace',description:'Set current brands and classify primary, clearance, faulty and consignment stock.',icon:SlidersHorizontalIcon},
 {label:'Customer Coverage',href:'/customers',group:'Insights',description:'Explore customer activity and original order history.',icon:UsersThreeIcon},
 {label:'Product KPIs',href:'/products',group:'Insights',description:'Compare product demand, reach and repeat buying.',icon:ChartBarIcon},
 {label:'Demand Projection',href:'/projection',group:'Forecasting',description:'Compare demand scenarios and article breakdowns.',icon:TrendUpIcon},
 {label:'Seasonal Allocation',href:'/allocation',group:'Forecasting',description:'Select article season codes and view forecast quantities for a date interval.',icon:StackIcon},
 {label:'SKU Recommendations',href:'/recommendations',group:'Forecasting',description:'Review and adjust purchase quantities by size.',icon:PackageIcon},
 {label:'Budget Tracker',href:'/budget',group:'Buying',description:'Simulate costs, selling prices, margins and budget allocation.',icon:WalletIcon},
 {label:'Purchase Orders',href:'/purchase-orders',group:'Buying',description:'Create editable supplier PO drafts from saved budget quantities.',icon:FileTextIcon},
 {label:'Order Validation',href:'/validation',group:'Buying',description:'Validate supplier POs and download final purchase orders.',icon:ClipboardTextIcon},
 {label:'Settings & access',href:'/settings',group:'Workspace',description:'Manage your profile and team access.',icon:GearSixIcon},
];
export const navigationForRole=(role:PreduitRole)=>navigation.filter(item=>roleMeetsRequired(role,routeMinRole(item.href)||'worker'));
