/**
 * AZALPLUS Mobile - Push Notifications Hook
 *
 * React hook for managing push notification state and subscriptions.
 *
 * Features:
 * - Permission state management
 * - Subscription state
 * - Subscribe/unsubscribe actions
 * - Test notification
 * - Auto-subscribe on first grant
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  PushManager,
  pushManager,
  PushPermissionStatus,
  PushSubscriptionResult,
  NotificationPayload,
} from './PushManager';

// Hook return type
export interface UsePushNotificationsResult {
  // State
  isSupported: boolean;
  permissionStatus: PushPermissionStatus;
  isSubscribed: boolean;
  isLoading: boolean;
  error: string | null;

  // Actions
  subscribe: () => Promise<PushSubscriptionResult>;
  unsubscribe: () => Promise<boolean>;
  requestPermission: () => Promise<PushPermissionStatus>;
  sendTestNotification: () => Promise<boolean>;
  clearError: () => void;

  // Token info
  currentToken: string | null;
}

/**
 * Hook for managing push notifications.
 *
 * @param options - Configuration options
 * @returns Push notification state and actions
 */
export function usePushNotifications(options?: {
  /**
   * Auto-subscribe when permission is granted.
   * @default false
   */
  autoSubscribe?: boolean;

  /**
   * Callback when a notification is received in foreground.
   */
  onNotification?: (payload: NotificationPayload) => void;
}): UsePushNotificationsResult {
  const { autoSubscribe = false, onNotification } = options ?? {};

  // State
  const [permissionStatus, setPermissionStatus] = useState<PushPermissionStatus>(
    PushManager.getPermissionStatus()
  );
  const [isSubscribed, setIsSubscribed] = useState<boolean>(
    pushManager.isCurrentlySubscribed()
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentToken, setCurrentToken] = useState<string | null>(
    pushManager.getCurrentToken()
  );

  const isSupported = useMemo(() => PushManager.isSupported(), []);

  // Update permission status on visibility change
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        setPermissionStatus(PushManager.getPermissionStatus());
        setIsSubscribed(pushManager.isCurrentlySubscribed());
        setCurrentToken(pushManager.getCurrentToken());
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  // Setup foreground message handler
  useEffect(() => {
    if (!onNotification || !isSubscribed) {
      return;
    }

    let cleanup: (() => void) | undefined;

    const setup = async () => {
      cleanup = await pushManager.setupMessageHandler(onNotification);
    };

    setup();

    return () => {
      if (cleanup) {
        cleanup();
      }
    };
  }, [onNotification, isSubscribed]);

  // Auto-subscribe when permission is granted
  useEffect(() => {
    if (
      autoSubscribe &&
      isSupported &&
      permissionStatus === 'granted' &&
      !isSubscribed &&
      !isLoading
    ) {
      // Small delay to avoid race conditions
      const timeout = setTimeout(() => {
        subscribe();
      }, 100);

      return () => clearTimeout(timeout);
    }
  }, [autoSubscribe, isSupported, permissionStatus, isSubscribed, isLoading]);

  /**
   * Request notification permission.
   */
  const requestPermission = useCallback(async (): Promise<PushPermissionStatus> => {
    setIsLoading(true);
    setError(null);

    try {
      const status = await pushManager.requestPermission();
      setPermissionStatus(status);
      return status;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Permission request failed';
      setError(message);
      return 'denied';
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Subscribe to push notifications.
   */
  const subscribe = useCallback(async (): Promise<PushSubscriptionResult> => {
    setIsLoading(true);
    setError(null);

    try {
      const result = await pushManager.subscribe();

      if (result.success) {
        setIsSubscribed(true);
        setCurrentToken(result.token ?? null);
        setPermissionStatus('granted');
      } else {
        setError(result.error ?? 'Subscription failed');
      }

      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Subscription failed';
      setError(message);
      return { success: false, error: message };
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Unsubscribe from push notifications.
   */
  const unsubscribe = useCallback(async (): Promise<boolean> => {
    setIsLoading(true);
    setError(null);

    try {
      const success = await pushManager.unsubscribe();

      if (success) {
        setIsSubscribed(false);
        setCurrentToken(null);
      } else {
        setError('Failed to unsubscribe');
      }

      return success;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unsubscribe failed';
      setError(message);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Send a test notification.
   */
  const sendTestNotification = useCallback(async (): Promise<boolean> => {
    setIsLoading(true);
    setError(null);

    try {
      const success = await pushManager.sendTestNotification();

      if (!success) {
        setError('Test notification failed');
      }

      return success;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Test failed';
      setError(message);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Clear error state.
   */
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    // State
    isSupported,
    permissionStatus,
    isSubscribed,
    isLoading,
    error,

    // Actions
    subscribe,
    unsubscribe,
    requestPermission,
    sendTestNotification,
    clearError,

    // Token info
    currentToken,
  };
}

/**
 * Hook for simplified push notification subscription management.
 *
 * Returns a simple boolean and toggle function.
 */
export function usePushSubscription(): {
  enabled: boolean;
  toggle: () => Promise<void>;
  isLoading: boolean;
} {
  const {
    isSupported,
    isSubscribed,
    isLoading,
    permissionStatus,
    subscribe,
    unsubscribe,
  } = usePushNotifications();

  const toggle = useCallback(async () => {
    if (!isSupported) {
      return;
    }

    if (isSubscribed) {
      await unsubscribe();
    } else {
      await subscribe();
    }
  }, [isSupported, isSubscribed, subscribe, unsubscribe]);

  const enabled = isSupported && permissionStatus === 'granted' && isSubscribed;

  return {
    enabled,
    toggle,
    isLoading,
  };
}

// Export types
export type { NotificationPayload, PushSubscriptionResult, PushPermissionStatus };
