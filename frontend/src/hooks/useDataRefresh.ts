"use client";

import { useEffect, useCallback, useRef, useState } from "react";
import { getAccessToken } from "@/lib/api/tokenProvider";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000/api";

// The banner and page share one stream. Two streams per tab can exhaust the
// browser's six HTTP/1 connections when several planning tabs are open.
const subscribers=new Set<{notify:()=>void;skipInitial:boolean}>();
let sharedEvents:EventSource|null=null;
let reconnect:ReturnType<typeof setTimeout>|undefined;
let connecting=false;
let generation=0;
let lastPublication:string|undefined;

async function connectEvents(){
 if(connecting||sharedEvents||!subscribers.size)return;
 connecting=true;const version=++generation;
 try{
  const token=await getAccessToken();
  if(version!==generation||!subscribers.size)return;
  const url=token?`${API_BASE}/events?access_token=${encodeURIComponent(token)}`:`${API_BASE}/events`;
  const source=new EventSource(url);sharedEvents=source;
  source.addEventListener('data-refreshed',(event)=>{
   if(version!==generation)return;
   const publication=(event as MessageEvent<string>).data;
   if(publication===lastPublication)return;
   const initial=lastPublication===undefined;lastPublication=publication;
   for(const subscriber of subscribers)if(!initial||!subscriber.skipInitial)subscriber.notify();
  });
  source.onerror=()=>{
   source.close();if(sharedEvents===source)sharedEvents=null;
   if(version===generation&&subscribers.size)reconnect=setTimeout(()=>void connectEvents(),10_000);
  };
 }catch{
  if(version===generation&&subscribers.size)reconnect=setTimeout(()=>void connectEvents(),10_000);
 }finally{if(version===generation)connecting=false;}
}

function subscribe(notify:()=>void,skipInitial:boolean){
 const subscriber={notify,skipInitial};subscribers.add(subscriber);
 if(lastPublication!==undefined&&!skipInitial)queueMicrotask(()=>{if(subscribers.has(subscriber))notify();});
 void connectEvents();
 return()=>{
  subscribers.delete(subscriber);
  if(!subscribers.size){generation++;connecting=false;sharedEvents?.close();sharedEvents=null;clearTimeout(reconnect);lastPublication=undefined;}
 };
}

export function useDataRefresh(onRefresh: () => void, skipInitial = true) {
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;

  useEffect(()=>subscribe(()=>onRefreshRef.current(),skipInitial),[skipInitial]);
}

export function useApiData<T>(
  fetchFn: () => Promise<T>,
  deps: unknown[] = [],
) {
  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await fetchFn();
      setData(result);
    } catch (err) {
      console.error("API fetch error:", err);
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setIsLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    load();
  }, [load]);

  useDataRefresh(load);

  return { data, isLoading, error, reload: load };
}
