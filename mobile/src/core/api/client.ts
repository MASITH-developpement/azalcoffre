/**
 * API Client for AZALPLUS Mobile PWA
 *
 * Features:
 * - JWT token management with automatic refresh
 * - Request/response interceptors
 * - Offline queue support (basic)
 * - Typed fetch wrapper
 */

// Types
export interface ApiResponse<T> {
  data: T;
  message?: string;
  success: boolean;
}

export interface ApiError {
  message: string;
  code?: string;
  status: number;
  details?: Record<string, unknown>;
}

export interface QueuedRequest {
  id: string;
  url: string;
  method: string;
  body?: unknown;
  timestamp: number;
  retryCount: number;
}

type RequestInterceptor = (config: RequestConfig) => RequestConfig | Promise<RequestConfig>;
type ResponseInterceptor = (response: Response) => Response | Promise<Response>;
type ErrorInterceptor = (error: ApiError) => ApiError | Promise<ApiError>;

interface RequestConfig {
  url: string;
  method: string;
  headers: Record<string, string>;
  body?: unknown;
}

// Constants
const STORAGE_KEYS = {
  ACCESS_TOKEN: 'azalplus_access_token',
  REFRESH_TOKEN: 'azalplus_refresh_token',
  OFFLINE_QUEUE: 'azalplus_offline_queue',
} as const;

const BASE_URL = import.meta.env.VITE_API_URL || '/api';

// Offline queue storage
class OfflineQueue {
  private static getQueue(): QueuedRequest[] {
    try {
      const stored = localStorage.getItem(STORAGE_KEYS.OFFLINE_QUEUE);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  }

  private static saveQueue(queue: QueuedRequest[]): void {
    localStorage.setItem(STORAGE_KEYS.OFFLINE_QUEUE, JSON.stringify(queue));
  }

  static add(request: Omit<QueuedRequest, 'id' | 'timestamp' | 'retryCount'>): string {
    const queue = this.getQueue();
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    queue.push({
      ...request,
      id,
      timestamp: Date.now(),
      retryCount: 0,
    });
    this.saveQueue(queue);
    return id;
  }

  static remove(id: string): void {
    const queue = this.getQueue();
    this.saveQueue(queue.filter((req) => req.id !== id));
  }

  static getAll(): QueuedRequest[] {
    return this.getQueue();
  }

  static clear(): void {
    localStorage.removeItem(STORAGE_KEYS.OFFLINE_QUEUE);
  }

  static incrementRetry(id: string): void {
    const queue = this.getQueue();
    const request = queue.find((req) => req.id === id);
    if (request) {
      request.retryCount += 1;
      this.saveQueue(queue);
    }
  }
}

// Token management
class TokenManager {
  static getAccessToken(): string | null {
    return localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
  }

  static getRefreshToken(): string | null {
    return localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
  }

  static setTokens(accessToken: string, refreshToken?: string): void {
    localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, accessToken);
    if (refreshToken) {
      localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refreshToken);
    }
  }

  static clearTokens(): void {
    localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
  }

  static isTokenExpired(token: string): boolean {
    try {
      const parts = token.split('.');
      const payloadPart = parts[1];
      if (!payloadPart) return true;
      const payload = JSON.parse(atob(payloadPart));
      // Add 30 second buffer before expiration
      return payload.exp * 1000 < Date.now() + 30000;
    } catch {
      return true;
    }
  }
}

// API Client class
class ApiClient {
  private baseUrl: string;
  private requestInterceptors: RequestInterceptor[] = [];
  private responseInterceptors: ResponseInterceptor[] = [];
  private errorInterceptors: ErrorInterceptor[] = [];
  private refreshPromise: Promise<boolean> | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  // Interceptor registration
  addRequestInterceptor(interceptor: RequestInterceptor): void {
    this.requestInterceptors.push(interceptor);
  }

  addResponseInterceptor(interceptor: ResponseInterceptor): void {
    this.responseInterceptors.push(interceptor);
  }

  addErrorInterceptor(interceptor: ErrorInterceptor): void {
    this.errorInterceptors.push(interceptor);
  }

  // Token refresh
  private async refreshToken(): Promise<boolean> {
    const refreshToken = TokenManager.getRefreshToken();
    if (!refreshToken) {
      return false;
    }

    try {
      const response = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        TokenManager.clearTokens();
        return false;
      }

      const data = await response.json();
      TokenManager.setTokens(data.access_token, data.refresh_token);
      return true;
    } catch {
      TokenManager.clearTokens();
      return false;
    }
  }

  // Ensure valid token before request
  private async ensureValidToken(): Promise<void> {
    const accessToken = TokenManager.getAccessToken();
    if (!accessToken) {
      return;
    }

    if (TokenManager.isTokenExpired(accessToken)) {
      // Use shared promise to prevent multiple simultaneous refresh attempts
      if (!this.refreshPromise) {
        this.refreshPromise = this.refreshToken().finally(() => {
          this.refreshPromise = null;
        });
      }
      await this.refreshPromise;
    }
  }

  // Build headers
  private buildHeaders(customHeaders?: Record<string, string>): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...customHeaders,
    };

    const token = TokenManager.getAccessToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    return headers;
  }

  // Process request through interceptors
  private async processRequestInterceptors(config: RequestConfig): Promise<RequestConfig> {
    let processedConfig = config;
    for (const interceptor of this.requestInterceptors) {
      processedConfig = await interceptor(processedConfig);
    }
    return processedConfig;
  }

  // Process response through interceptors
  private async processResponseInterceptors(response: Response): Promise<Response> {
    let processedResponse = response;
    for (const interceptor of this.responseInterceptors) {
      processedResponse = await interceptor(processedResponse);
    }
    return processedResponse;
  }

  // Process error through interceptors
  private async processErrorInterceptors(error: ApiError): Promise<ApiError> {
    let processedError = error;
    for (const interceptor of this.errorInterceptors) {
      processedError = await interceptor(processedError);
    }
    return processedError;
  }

  // Main request method
  async request<T>(
    url: string,
    options: {
      method?: string;
      body?: unknown;
      headers?: Record<string, string>;
      queueOffline?: boolean;
    } = {}
  ): Promise<ApiResponse<T>> {
    const { method = 'GET', body, headers: customHeaders, queueOffline = false } = options;

    // Check online status
    if (!navigator.onLine && queueOffline && method !== 'GET') {
      const queueId = OfflineQueue.add({ url, method, body });
      return {
        data: { queued: true, queueId } as unknown as T,
        success: true,
        message: 'Request queued for offline sync',
      };
    }

    // Ensure valid token
    await this.ensureValidToken();

    // Build request config
    let config: RequestConfig = {
      url: `${this.baseUrl}${url}`,
      method,
      headers: this.buildHeaders(customHeaders),
      body,
    };

    // Process request interceptors
    config = await this.processRequestInterceptors(config);

    try {
      // Make the request
      let response = await fetch(config.url, {
        method: config.method,
        headers: config.headers,
        ...(config.body ? { body: JSON.stringify(config.body) } : {}),
      });

      // Process response interceptors
      response = await this.processResponseInterceptors(response);

      // Handle 401 - try to refresh token once
      if (response.status === 401) {
        const refreshed = await this.refreshToken();
        if (refreshed) {
          // Retry the request with new token
          config.headers = this.buildHeaders(customHeaders);
          response = await fetch(config.url, {
            method: config.method,
            headers: config.headers,
            ...(config.body ? { body: JSON.stringify(config.body) } : {}),
          });
        }
      }

      // Parse response
      const data = await response.json();

      if (!response.ok) {
        const error: ApiError = {
          message: data.message || data.detail || 'An error occurred',
          code: data.code,
          status: response.status,
          details: data.details,
        };
        const processedError = await this.processErrorInterceptors(error);
        throw processedError;
      }

      return {
        data: data.data ?? data,
        message: data.message,
        success: true,
      };
    } catch (error) {
      // Handle network errors
      if (error instanceof TypeError && error.message.includes('fetch')) {
        if (queueOffline && method !== 'GET') {
          const queueId = OfflineQueue.add({ url, method, body });
          return {
            data: { queued: true, queueId } as unknown as T,
            success: true,
            message: 'Request queued for offline sync',
          };
        }
        throw {
          message: 'Network error - please check your connection',
          status: 0,
          code: 'NETWORK_ERROR',
        } as ApiError;
      }
      throw error;
    }
  }

  // Convenience methods
  async get<T>(url: string, headers?: Record<string, string>): Promise<ApiResponse<T>> {
    return this.request<T>(url, { method: 'GET', ...(headers ? { headers } : {}) });
  }

  async post<T>(
    url: string,
    body?: unknown,
    options?: { headers?: Record<string, string>; queueOffline?: boolean }
  ): Promise<ApiResponse<T>> {
    return this.request<T>(url, { method: 'POST', body, ...options });
  }

  async put<T>(
    url: string,
    body?: unknown,
    options?: { headers?: Record<string, string>; queueOffline?: boolean }
  ): Promise<ApiResponse<T>> {
    return this.request<T>(url, { method: 'PUT', body, ...options });
  }

  async patch<T>(
    url: string,
    body?: unknown,
    options?: { headers?: Record<string, string>; queueOffline?: boolean }
  ): Promise<ApiResponse<T>> {
    return this.request<T>(url, { method: 'PATCH', body, ...options });
  }

  async delete<T>(
    url: string,
    options?: { headers?: Record<string, string>; queueOffline?: boolean }
  ): Promise<ApiResponse<T>> {
    return this.request<T>(url, { method: 'DELETE', ...options });
  }
}

// Create and export singleton instance
export const apiClient = new ApiClient(BASE_URL);

// Export utilities
export { TokenManager, OfflineQueue };

// Process offline queue when back online
if (typeof window !== 'undefined') {
  window.addEventListener('online', async () => {
    const queue = OfflineQueue.getAll();
    for (const request of queue) {
      try {
        await apiClient.request(request.url, {
          method: request.method,
          body: request.body,
        });
        OfflineQueue.remove(request.id);
      } catch {
        OfflineQueue.incrementRetry(request.id);
        // Remove if too many retries
        if (request.retryCount >= 3) {
          OfflineQueue.remove(request.id);
        }
      }
    }
  });
}
