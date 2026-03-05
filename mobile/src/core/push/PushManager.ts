/**
 * AZALPLUS Mobile - Push Manager
 *
 * Manages push notification subscriptions and token registration with FCM.
 *
 * Features:
 * - Request permission for notifications
 * - Get FCM token
 * - Register token with backend
 * - Unregister token on logout
 * - Handle permission changes
 *
 * Multi-tenant: Token is associated with current user and tenant.
 */

import { apiClient } from '../api/client';

// VAPID public key for web push (FCM)
// In production, this should come from environment variables
const VAPID_PUBLIC_KEY = import.meta.env.VITE_FIREBASE_VAPID_KEY || '';

// Firebase configuration
const FIREBASE_CONFIG = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || '',
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || '',
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || '',
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || '',
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || '',
  appId: import.meta.env.VITE_FIREBASE_APP_ID || '',
};

// Storage keys
const STORAGE_KEYS = {
  PUSH_TOKEN: 'azalplus_push_token',
  PUSH_PERMISSION: 'azalplus_push_permission',
  PUSH_SUBSCRIBED: 'azalplus_push_subscribed',
} as const;

// Types
export type PushPermissionStatus = 'granted' | 'denied' | 'default' | 'unsupported';

export interface PushSubscriptionResult {
  success: boolean;
  token?: string;
  error?: string;
}

export interface DeviceInfo {
  userAgent: string;
  language: string;
  platform: string;
  screenWidth: number;
  screenHeight: number;
  timezone: string;
}

// Get device information for registration
function getDeviceInfo(): DeviceInfo {
  return {
    userAgent: navigator.userAgent,
    language: navigator.language,
    platform: navigator.platform || 'unknown',
    screenWidth: window.screen.width,
    screenHeight: window.screen.height,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  };
}

// Firebase initialization state
let firebaseApp: unknown = null;
let messaging: unknown = null;
let firebaseInitialized = false;

/**
 * Initialize Firebase if not already initialized.
 */
async function initializeFirebase(): Promise<boolean> {
  if (firebaseInitialized) {
    return true;
  }

  // Check if Firebase config is available
  if (!FIREBASE_CONFIG.apiKey || !FIREBASE_CONFIG.projectId) {
    console.warn('[PushManager] Firebase configuration not provided');
    return false;
  }

  try {
    // Dynamic import to avoid loading Firebase when not needed
    const firebase = await import('firebase/app');
    const firebaseMessaging = await import('firebase/messaging');

    // Initialize Firebase app
    firebaseApp = firebase.initializeApp(FIREBASE_CONFIG);
    messaging = firebaseMessaging.getMessaging(firebaseApp as never);

    firebaseInitialized = true;
    console.log('[PushManager] Firebase initialized successfully');
    return true;
  } catch (error) {
    console.error('[PushManager] Failed to initialize Firebase:', error);
    return false;
  }
}

/**
 * Push Manager class for handling push notifications.
 */
export class PushManager {
  private static instance: PushManager;
  private currentToken: string | null = null;
  private isSubscribed = false;

  private constructor() {
    // Restore state from storage
    this.currentToken = localStorage.getItem(STORAGE_KEYS.PUSH_TOKEN);
    this.isSubscribed = localStorage.getItem(STORAGE_KEYS.PUSH_SUBSCRIBED) === 'true';
  }

  /**
   * Get singleton instance.
   */
  static getInstance(): PushManager {
    if (!PushManager.instance) {
      PushManager.instance = new PushManager();
    }
    return PushManager.instance;
  }

  /**
   * Check if push notifications are supported.
   */
  static isSupported(): boolean {
    return (
      'serviceWorker' in navigator &&
      'PushManager' in window &&
      'Notification' in window
    );
  }

  /**
   * Get current permission status.
   */
  static getPermissionStatus(): PushPermissionStatus {
    if (!PushManager.isSupported()) {
      return 'unsupported';
    }
    return Notification.permission as PushPermissionStatus;
  }

  /**
   * Request permission for push notifications.
   */
  async requestPermission(): Promise<PushPermissionStatus> {
    if (!PushManager.isSupported()) {
      return 'unsupported';
    }

    try {
      const permission = await Notification.requestPermission();
      localStorage.setItem(STORAGE_KEYS.PUSH_PERMISSION, permission);
      return permission as PushPermissionStatus;
    } catch (error) {
      console.error('[PushManager] Permission request failed:', error);
      return 'denied';
    }
  }

  /**
   * Get FCM token from Firebase.
   */
  private async getFirebaseToken(): Promise<string | null> {
    const initialized = await initializeFirebase();
    if (!initialized || !messaging) {
      console.warn('[PushManager] Firebase not available');
      return null;
    }

    try {
      const firebaseMessaging = await import('firebase/messaging');

      // Get token with VAPID key
      const token = await firebaseMessaging.getToken(messaging as never, {
        vapidKey: VAPID_PUBLIC_KEY,
      });

      if (token) {
        console.log('[PushManager] FCM token obtained');
        return token;
      } else {
        console.warn('[PushManager] No FCM token available');
        return null;
      }
    } catch (error) {
      console.error('[PushManager] Failed to get FCM token:', error);
      return null;
    }
  }

  /**
   * Subscribe to push notifications.
   * Requests permission, gets token, and registers with backend.
   */
  async subscribe(): Promise<PushSubscriptionResult> {
    // Check support
    if (!PushManager.isSupported()) {
      return {
        success: false,
        error: 'Push notifications not supported on this device',
      };
    }

    // Request permission if not granted
    const permission = PushManager.getPermissionStatus();
    if (permission === 'denied') {
      return {
        success: false,
        error: 'Notification permission denied',
      };
    }

    if (permission !== 'granted') {
      const newPermission = await this.requestPermission();
      if (newPermission !== 'granted') {
        return {
          success: false,
          error: 'Notification permission not granted',
        };
      }
    }

    try {
      // Get FCM token
      const token = await this.getFirebaseToken();
      if (!token) {
        return {
          success: false,
          error: 'Failed to obtain push token',
        };
      }

      // Register with backend
      const deviceInfo = getDeviceInfo();
      const response = await apiClient.post<{ token_id: string }>('/push/register', {
        token,
        platform: 'web',
        device_info: deviceInfo,
      });

      if (response.success) {
        // Store token locally
        this.currentToken = token;
        this.isSubscribed = true;
        localStorage.setItem(STORAGE_KEYS.PUSH_TOKEN, token);
        localStorage.setItem(STORAGE_KEYS.PUSH_SUBSCRIBED, 'true');

        console.log('[PushManager] Successfully subscribed to push notifications');
        return {
          success: true,
          token,
        };
      } else {
        return {
          success: false,
          error: 'Failed to register push token with server',
        };
      }
    } catch (error) {
      console.error('[PushManager] Subscription failed:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  /**
   * Unsubscribe from push notifications.
   */
  async unsubscribe(): Promise<boolean> {
    if (!this.currentToken) {
      return true; // Already unsubscribed
    }

    try {
      // Unregister from backend
      await apiClient.delete('/push/unregister', {
        body: { token: this.currentToken },
      } as never);

      // Clear local state
      this.currentToken = null;
      this.isSubscribed = false;
      localStorage.removeItem(STORAGE_KEYS.PUSH_TOKEN);
      localStorage.removeItem(STORAGE_KEYS.PUSH_SUBSCRIBED);

      console.log('[PushManager] Successfully unsubscribed from push notifications');
      return true;
    } catch (error) {
      console.error('[PushManager] Unsubscribe failed:', error);
      return false;
    }
  }

  /**
   * Check if currently subscribed.
   */
  isCurrentlySubscribed(): boolean {
    return this.isSubscribed && this.currentToken !== null;
  }

  /**
   * Get current token.
   */
  getCurrentToken(): string | null {
    return this.currentToken;
  }

  /**
   * Send a test notification to verify setup.
   */
  async sendTestNotification(): Promise<boolean> {
    if (!this.isSubscribed) {
      console.warn('[PushManager] Not subscribed - cannot send test notification');
      return false;
    }

    try {
      const response = await apiClient.post('/push/test', {
        title: 'Test AZALPLUS',
        body: 'Les notifications push fonctionnent correctement!',
      });

      return response.success;
    } catch (error) {
      console.error('[PushManager] Test notification failed:', error);
      return false;
    }
  }

  /**
   * Get push notification status.
   */
  async getStatus(): Promise<{
    enabled: boolean;
    deviceCount: number;
    platforms: string[];
  }> {
    try {
      const response = await apiClient.get<{
        enabled: boolean;
        device_count: number;
        platforms: string[];
      }>('/push/status');

      return {
        enabled: response.data?.enabled ?? false,
        deviceCount: response.data?.device_count ?? 0,
        platforms: response.data?.platforms ?? [],
      };
    } catch (error) {
      console.error('[PushManager] Failed to get status:', error);
      return {
        enabled: false,
        deviceCount: 0,
        platforms: [],
      };
    }
  }

  /**
   * Setup message handler for foreground messages.
   * Returns cleanup function.
   */
  async setupMessageHandler(
    handler: (payload: NotificationPayload) => void
  ): Promise<() => void> {
    const initialized = await initializeFirebase();
    if (!initialized || !messaging) {
      return () => {};
    }

    try {
      const firebaseMessaging = await import('firebase/messaging');

      const unsubscribe = firebaseMessaging.onMessage(
        messaging as never,
        (payload: unknown) => {
          console.log('[PushManager] Foreground message received:', payload);
          const typedPayload = payload as {
            notification?: { title?: string; body?: string; image?: string };
            data?: Record<string, string>;
          };
          handler({
            title: typedPayload.notification?.title ?? 'Notification',
            body: typedPayload.notification?.body ?? '',
            image: typedPayload.notification?.image,
            data: typedPayload.data ?? {},
          });
        }
      );

      return unsubscribe;
    } catch (error) {
      console.error('[PushManager] Failed to setup message handler:', error);
      return () => {};
    }
  }
}

/**
 * Notification payload structure.
 */
export interface NotificationPayload {
  title: string;
  body: string;
  image?: string;
  data: Record<string, string>;
}

// Export singleton instance
export const pushManager = PushManager.getInstance();
