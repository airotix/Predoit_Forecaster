"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
export default function PlanningInputs(){
  const [message,setMessage]=useState("");const [busy,setBusy]=useState(false);
  async function upload(file:File){
    setBusy(true);setMessage("");
    try{
      const body=new FormData();body.append("file",file);
      const response=await fetch(`${process.env.NEXT_PUBLIC_API_URL||"http://localhost:4000/api"}/planning/inputs`,{method:"POST",body});
      const result=await response.json();if(!response.ok)throw new Error(result.detail||"Import failed");
      setMessage(`${result.imported} input rows saved. Refresh forecasts to apply them.`);
    }catch(e){setMessage(e instanceof Error?e.message:"Import failed");}finally{setBusy(false);}
  }
  function template(){
    const blob=new Blob(["Reference,Couleur,Taille,Selling_Price,Purchase_Cost,STOCK,CDE_four_qte\n"],{type:"text/csv"});
    const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="planning-inputs.csv";a.click();URL.revokeObjectURL(url);
  }
  return <Card><CardHeader><CardTitle>Actual stock and costs</CardTitle></CardHeader><CardContent className="space-y-3">
    <p className="text-sm">Upload CSV or XLSX with Reference, Couleur, Taille, Selling_Price, Purchase_Cost, STOCK and CDE_four_qte. Match the identifiers shown in your order data. Blank values remain unknown; enter zero only when the value really is zero.</p>
    <p className="text-sm text-amber-700">Quantity forecasts can run without these inputs. Purchase approval requires complete matched stock and costs. Supplier incoming quantities must be those available during the planning period.</p>
    <Button type="button" variant="outline" onClick={template}>Download input template</Button>
    <Input type="file" accept=".csv,.xlsx" disabled={busy} aria-label="Actual inventory and costs" onChange={e=>{const file=e.target.files?.[0];if(file)void upload(file);}}/>
    {message&&<p role="status" className="text-sm">{message}</p>}
  </CardContent></Card>;
}
