import {afterEach,describe,expect,it,vi} from 'vitest';
import {budgetApi} from './budget';
import {setTokenProvider} from './tokenProvider';

afterEach(()=>{setTokenProvider(async()=>null);vi.unstubAllGlobals();vi.restoreAllMocks();});

describe('budget draft loading',()=>{
 it('shares overlapping loads, then fetches fresh data for the next load',async()=>{
  setTokenProvider(async()=>null);
  let resolve!:(response:Response)=>void;
  const fetch=vi.fn().mockImplementationOnce(()=>new Promise<Response>(done=>{resolve=done;}))
   .mockResolvedValueOnce(new Response('{"revision":"new"}'));
  vi.stubGlobal('fetch',fetch);
  const first=budgetApi.draft('base');const second=budgetApi.draft('base');
  await vi.waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
  resolve(new Response('{"revision":"old"}'));
  await expect(first).resolves.toEqual({revision:'old'});
  await expect(second).resolves.toEqual({revision:'old'});
  await expect(budgetApi.draft('base')).resolves.toEqual({revision:'new'});
  expect(fetch).toHaveBeenCalledTimes(2);
 });
 it('reports a timed-out load and permits retry without affecting another scenario',async()=>{
  setTokenProvider(async()=>null);
  vi.spyOn(AbortSignal,'timeout').mockReturnValue(new AbortController().signal);
  const fetch=vi.fn().mockRejectedValueOnce(new DOMException('Timed out','TimeoutError'))
   .mockResolvedValueOnce(new Response('{"scenario":"optimistic"}'))
   .mockResolvedValueOnce(new Response('{"scenario":"base"}'));
  vi.stubGlobal('fetch',fetch);
  const failed=budgetApi.draft('base');const other=budgetApi.draft('optimistic');
  await expect(failed).rejects.toThrow('more than two minutes');
  await expect(other).resolves.toEqual({scenario:'optimistic'});
  await expect(budgetApi.draft('base')).resolves.toEqual({scenario:'base'});
  expect(AbortSignal.timeout).toHaveBeenCalledWith(120_000);
 });
});
