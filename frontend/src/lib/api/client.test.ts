import {afterEach,describe,expect,it,vi} from 'vitest';
import {apiClient,ApiError} from './client';
import {setTokenProvider} from './tokenProvider';

afterEach(()=>{setTokenProvider(async()=>null);vi.unstubAllGlobals();});

describe('merged API client',()=>{
 it('coalesces overlapping reads but refetches after a mutation',async()=>{
  setTokenProvider(async()=>null);
  let resolve!:(response:Response)=>void;
  const fetch=vi.fn().mockImplementationOnce(()=>new Promise<Response>(done=>{resolve=done;}))
   .mockResolvedValueOnce(new Response('{"saved":true}'))
   .mockResolvedValueOnce(new Response('{"version":2}'));
  vi.stubGlobal('fetch',fetch);
  const first=apiClient.get('/dashboard'),second=apiClient.get('/dashboard');
  await vi.waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
  await apiClient.put('/catalogue/prices',{rows:[]});
  await expect(apiClient.get('/dashboard')).resolves.toEqual({version:2});
  resolve(new Response('{"version":1}'));
  await expect(first).resolves.toEqual({version:1});await expect(second).resolves.toEqual({version:1});
  expect(fetch).toHaveBeenCalledTimes(3);
 });
 it('retains bearer authentication for the new catalogue endpoint',async()=>{
  setTokenProvider(async()=>'synthetic-test-token');
  const fetch=vi.fn().mockResolvedValue(new Response('{"rows":[]}',{status:200}));
  vi.stubGlobal('fetch',fetch);
  await apiClient.get('/catalogue',{search:'101126'});
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/catalogue?search=101126'),expect.objectContaining({headers:expect.objectContaining({Authorization:'Bearer synthetic-test-token'})}));
 });
 it('preserves actionable validation errors from current forecasting routes',async()=>{
  setTokenProvider(async()=>null);
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{"detail":"Publish matching forecast dates first"}',{status:409})));
  await expect(apiClient.get('/seasonal-allocation')).rejects.toMatchObject({status:409,message:'Publish matching forecast dates first'});
 });
 it('handles non-JSON errors without consuming the response twice',async()=>{
  setTokenProvider(async()=>null);
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('Service unavailable',{status:503,statusText:'Service Unavailable'})));
  const failure=await apiClient.get('/automatic').catch(error=>error);
  expect(failure).toBeInstanceOf(ApiError);
  if(!(failure instanceof ApiError))throw new Error('Expected a structured API error');
  expect(failure.details).toBe('Service unavailable');
 });
});
