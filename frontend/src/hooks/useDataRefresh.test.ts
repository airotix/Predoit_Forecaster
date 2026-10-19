import {afterEach,describe,expect,it,vi} from 'vitest';
import {setTokenProvider} from '@/lib/api/tokenProvider';

const harness=vi.hoisted(()=>({effects:[] as (()=>(()=>void))[]}));
vi.mock('react',async()=>({...await vi.importActual('react'),
 useRef:(value:unknown)=>({current:value}),
 useEffect:(effect:()=>()=>void)=>{harness.effects.push(effect);},
}));
import {useDataRefresh} from './useDataRefresh';

class FakeEvents {
 static instances:FakeEvents[]=[];
 onerror:(()=>void)|null=null;
 close=vi.fn();
 listeners=new Map<string,(event:MessageEvent<string>)=>void>();
 constructor(public url:string){FakeEvents.instances.push(this);}
 addEventListener(name:string,listener:(event:MessageEvent<string>)=>void){this.listeners.set(name,listener);}
 publish(value:string){this.listeners.get('data-refreshed')?.(new MessageEvent('data-refreshed',{data:value}));}
}

afterEach(()=>{harness.effects=[];FakeEvents.instances=[];setTokenProvider(async()=>null);vi.useRealTimers();vi.unstubAllGlobals();});

describe('publication connection lifecycle',()=>{
 it('shares one stream between the page and banner without losing either subscriber',async()=>{
  vi.useFakeTimers();setTokenProvider(async()=>null);vi.stubGlobal('EventSource',FakeEvents);
  const page=vi.fn(),banner=vi.fn();useDataRefresh(page);useDataRefresh(banner);
  const stopPage=harness.effects[0](),stopBanner=harness.effects[1]();
  await vi.advanceTimersByTimeAsync(0);expect(FakeEvents.instances).toHaveLength(1);
  const source=FakeEvents.instances[0];source.publish('initial');expect(page).not.toHaveBeenCalled();
  source.publish('new run');expect(page).toHaveBeenCalledTimes(1);expect(banner).toHaveBeenCalledTimes(1);
  stopPage();expect(source.close).not.toHaveBeenCalled();source.publish('another run');expect(banner).toHaveBeenCalledTimes(2);
  stopBanner();expect(source.close).toHaveBeenCalledTimes(1);
 });
 it('does not open a leaked connection when Strict Mode cleans up before token lookup finishes',async()=>{
  let finish!:(token:null)=>void;
  setTokenProvider(()=>new Promise(done=>{finish=done;}));
  vi.stubGlobal('EventSource',FakeEvents);
  useDataRefresh(vi.fn());const cleanup=harness.effects[0]();cleanup();finish(null);
  await Promise.resolve();await Promise.resolve();
  expect(FakeEvents.instances).toHaveLength(0);
 });
 it('skips the initial budget reload, ignores reconnect duplicates and refreshes for changed publications',async()=>{
  vi.useFakeTimers();setTokenProvider(async()=>null);vi.stubGlobal('EventSource',FakeEvents);
  const refresh=vi.fn();useDataRefresh(refresh,true);const cleanup=harness.effects[0]();
  await vi.advanceTimersByTimeAsync(0);
  const first=FakeEvents.instances[0];first.publish('run1');expect(refresh).not.toHaveBeenCalled();
  first.publish('run2');expect(refresh).toHaveBeenCalledTimes(1);
  first.onerror?.();await vi.advanceTimersByTimeAsync(10_000);
  const second=FakeEvents.instances[1];second.publish('run2');expect(refresh).toHaveBeenCalledTimes(1);
  second.publish('run3');expect(refresh).toHaveBeenCalledTimes(2);
  cleanup();second.onerror?.();await vi.advanceTimersByTimeAsync(10_000);
  expect(FakeEvents.instances).toHaveLength(2);expect(second.close).toHaveBeenCalled();
 });
});
