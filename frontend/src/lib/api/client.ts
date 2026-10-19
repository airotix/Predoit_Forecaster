import { getAccessToken } from './tokenProvider';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000/api';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public details?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined | null>;
}

function buildUrl(path: string, params?: RequestOptions['params']): string {
  const url = new URL(`${API_BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value));
      }
    });
  }
  return url.toString();
}

const pendingGets = new Map<string, Promise<unknown>>();
let readGeneration = 0;

async function perform<T>(url:string, fetchOptions:RequestInit, token:string|null):Promise<T> {
  const response = await fetch(url, {
    ...fetchOptions,
    headers: {
      'Content-Type': 'application/json',
      ...fetchOptions.headers,
      ...(token ? {Authorization: `Bearer ${token}`} : {}),
    },
  });

  if (!response.ok) {
    const raw = await response.text();
    let details: unknown = raw;
    if (raw) {
      try {
        details = JSON.parse(raw);
      } catch {
        // keep raw text
      }
    }
    const detail = typeof details === "object" && details !== null && "detail" in details ? String((details as {detail:unknown}).detail) : `Request failed: ${response.statusText}`;
    throw new ApiError(response.status, detail, details);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {params,...fetchOptions}=options;
  const url=buildUrl(path,params);
  const token=await getAccessToken();
  if(fetchOptions.method!=='GET'){
    readGeneration++;pendingGets.clear();
    try{return await perform<T>(url,fetchOptions,token);}
    finally{readGeneration++;pendingGets.clear();}
  }
  // Coalesce overlapping Strict Mode, banner and page reads. Do not retain
  // completed results in the browser; source and price writes stay visible.
  if(fetchOptions.signal)return perform<T>(url,fetchOptions,token);
  const key=JSON.stringify([url,token,readGeneration]);
  const pending=pendingGets.get(key);if(pending)return pending as Promise<T>;
  const result=perform<T>(url,{...fetchOptions,signal:AbortSignal.timeout(120_000)},token)
    .catch((error:unknown)=>{if(error instanceof Error&&error.name==='TimeoutError')throw new ApiError(408,'The server took too long to respond. Check the backend connection and retry.');throw error;})
    .finally(()=>{if(pendingGets.get(key)===result)pendingGets.delete(key);});
  pendingGets.set(key,result);return result;
}

export const apiClient = {
  get: <T>(path: string, params?: RequestOptions['params'], options?: Omit<RequestOptions, 'method' | 'params'>) =>
    request<T>(path, { ...options, method: 'GET', params }),

  post: <T>(path: string, data?: unknown, params?: RequestOptions['params']) =>
    request<T>(path, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
      params,
    }),

  put: <T>(path: string, data?: unknown, params?: RequestOptions['params']) =>
    request<T>(path, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
      params,
    }),

  patch: <T>(path: string, data?: unknown, params?: RequestOptions['params']) =>
    request<T>(path, {
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
      params,
    }),

  delete: <T>(path: string, params?: RequestOptions['params']) =>
    request<T>(path, { method: 'DELETE', params }),
};
