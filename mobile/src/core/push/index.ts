/**
 * AZALPLUS Mobile - Push Notifications Module
 *
 * Exports all push notification functionality.
 *
 * Usage:
 * ```typescript
 * import { usePushNotifications, pushManager, notificationHandler } from '@/core/push';
 *
 * // In a component
 * const { isSubscribed, subscribe, unsubscribe } = usePushNotifications();
 *
 * // Direct manager access
 * const token = pushManager.getCurrentToken();
 *
 * // Handle notifications
 * notificationHandler.addListener((notification) => {
 *   console.log('Received:', notification);
 * });
 * ```
 */

// PushManager - Core push notification management
export {
  PushManager,
  pushManager,
  type PushPermissionStatus,
  type PushSubscriptionResult,
  type NotificationPayload,
  type DeviceInfo,
} from './PushManager';

// React hooks
export {
  usePushNotifications,
  usePushSubscription,
  type UsePushNotificationsResult,
} from './usePushNotifications';

// NotificationHandler - Handle incoming notifications
export {
  NotificationHandler,
  notificationHandler,
  parseNotificationData,
  createNotification,
  showInAppNotification,
  type ParsedNotification,
  type NotificationType,
  type NotificationPriority,
  type NotificationDisplayOptions,
} from './NotificationHandler';

// Re-export types for convenience
export type {
  NotificationPayload as PushNotificationPayload,
} from './PushManager';
