/**
 * AZALPLUS Mobile - Notification Handler
 *
 * Handles incoming push notifications in foreground and background.
 *
 * Features:
 * - Show foreground notifications
 * - Handle notification clicks
 * - Route to appropriate screens
 * - Badge management
 * - Sound management
 */

// Notification types from backend
export type NotificationType = 'info' | 'warning' | 'success' | 'error';

// Notification priority
export type NotificationPriority = 'basse' | 'normale' | 'haute' | 'urgente';

/**
 * Parsed notification data from push payload.
 */
export interface ParsedNotification {
  id?: string;
  type: NotificationType;
  title: string;
  body: string;
  link?: string;
  recordId?: string;
  moduleSource?: string;
  priority?: NotificationPriority;
  tenantId?: string;
  image?: string;
  timestamp: Date;
}

/**
 * Configuration for notification display.
 */
export interface NotificationDisplayOptions {
  /** Show notification even when app is in foreground */
  showInForeground?: boolean;
  /** Play sound */
  playSound?: boolean;
  /** Vibrate device */
  vibrate?: boolean;
  /** Auto-dismiss after milliseconds (0 = never) */
  autoDismiss?: number;
  /** Show badge count */
  badge?: number;
}

// Default display options
const DEFAULT_OPTIONS: NotificationDisplayOptions = {
  showInForeground: true,
  playSound: true,
  vibrate: true,
  autoDismiss: 5000,
};

// Storage key for badge count
const BADGE_COUNT_KEY = 'azalplus_notification_badge';

/**
 * Parse notification data from push payload.
 */
export function parseNotificationData(
  payload: {
    title?: string;
    body?: string;
    image?: string;
    data?: Record<string, string>;
  }
): ParsedNotification {
  const data = payload.data ?? {};

  return {
    id: data.notification_id || data.id,
    type: (data.type as NotificationType) || 'info',
    title: payload.title ?? data.title ?? 'Notification',
    body: payload.body ?? data.body ?? '',
    link: data.link || data.url,
    recordId: data.record_id || data.recordId,
    moduleSource: data.module_source || data.module,
    priority: (data.priority as NotificationPriority) || 'normale',
    tenantId: data.tenant_id || data.tenantId,
    image: payload.image || data.image,
    timestamp: new Date(),
  };
}

/**
 * Notification Handler class.
 */
export class NotificationHandler {
  private static instance: NotificationHandler;
  private listeners: Set<(notification: ParsedNotification) => void> = new Set();
  private clickListeners: Set<(notification: ParsedNotification) => void> = new Set();

  private constructor() {
    // Initialize
    this.setupServiceWorkerListener();
  }

  /**
   * Get singleton instance.
   */
  static getInstance(): NotificationHandler {
    if (!NotificationHandler.instance) {
      NotificationHandler.instance = new NotificationHandler();
    }
    return NotificationHandler.instance;
  }

  /**
   * Setup listener for messages from service worker.
   */
  private setupServiceWorkerListener(): void {
    if (!('serviceWorker' in navigator)) {
      return;
    }

    navigator.serviceWorker.addEventListener('message', (event) => {
      const { type, payload } = event.data ?? {};

      if (type === 'NOTIFICATION_CLICK') {
        const notification = parseNotificationData(payload);
        this.handleClick(notification);
      } else if (type === 'NOTIFICATION_RECEIVED') {
        const notification = parseNotificationData(payload);
        this.notifyListeners(notification);
      }
    });
  }

  /**
   * Add listener for incoming notifications.
   */
  addListener(listener: (notification: ParsedNotification) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /**
   * Add listener for notification clicks.
   */
  addClickListener(listener: (notification: ParsedNotification) => void): () => void {
    this.clickListeners.add(listener);
    return () => this.clickListeners.delete(listener);
  }

  /**
   * Notify all listeners of a new notification.
   */
  private notifyListeners(notification: ParsedNotification): void {
    this.listeners.forEach((listener) => {
      try {
        listener(notification);
      } catch (error) {
        console.error('[NotificationHandler] Listener error:', error);
      }
    });
  }

  /**
   * Handle notification click.
   */
  handleClick(notification: ParsedNotification): void {
    // Notify click listeners
    this.clickListeners.forEach((listener) => {
      try {
        listener(notification);
      } catch (error) {
        console.error('[NotificationHandler] Click listener error:', error);
      }
    });

    // Navigate to link if provided
    if (notification.link) {
      this.navigateToLink(notification.link);
    }
  }

  /**
   * Navigate to a notification link.
   */
  private navigateToLink(link: string): void {
    try {
      // Handle internal links
      if (link.startsWith('/')) {
        // Use history API for SPA navigation
        window.history.pushState({}, '', link);
        window.dispatchEvent(new PopStateEvent('popstate'));
      } else if (link.startsWith('http')) {
        // External link - open in new tab
        window.open(link, '_blank', 'noopener,noreferrer');
      }
    } catch (error) {
      console.error('[NotificationHandler] Navigation error:', error);
    }
  }

  /**
   * Show a foreground notification.
   */
  async showForegroundNotification(
    notification: ParsedNotification,
    options: NotificationDisplayOptions = {}
  ): Promise<void> {
    const opts = { ...DEFAULT_OPTIONS, ...options };

    if (!opts.showInForeground) {
      return;
    }

    // Check permission
    if (Notification.permission !== 'granted') {
      console.warn('[NotificationHandler] Notification permission not granted');
      return;
    }

    try {
      // Get service worker registration
      const registration = await navigator.serviceWorker.getRegistration();

      if (!registration) {
        // Fallback to regular Notification API
        this.showBrowserNotification(notification, opts);
        return;
      }

      // Use service worker notification
      const notificationOptions: NotificationOptions = {
        body: notification.body,
        icon: '/icons/icon-192.png',
        badge: '/icons/badge-72.png',
        tag: notification.id || 'notification',
        renotify: true,
        data: {
          link: notification.link,
          type: notification.type,
          recordId: notification.recordId,
        },
        requireInteraction: notification.priority === 'urgente',
      };

      // Add vibration pattern based on priority
      if (opts.vibrate && 'vibrate' in navigator) {
        if (notification.priority === 'urgente') {
          notificationOptions.vibrate = [200, 100, 200, 100, 200];
        } else if (notification.priority === 'haute') {
          notificationOptions.vibrate = [200, 100, 200];
        } else {
          notificationOptions.vibrate = [100];
        }
      }

      // Add image if available
      if (notification.image) {
        notificationOptions.image = notification.image;
      }

      await registration.showNotification(notification.title, notificationOptions);

    } catch (error) {
      console.error('[NotificationHandler] Show notification error:', error);
      // Fallback to browser notification
      this.showBrowserNotification(notification, opts);
    }
  }

  /**
   * Show notification using browser Notification API.
   */
  private showBrowserNotification(
    notification: ParsedNotification,
    options: NotificationDisplayOptions
  ): void {
    try {
      const browserNotification = new Notification(notification.title, {
        body: notification.body,
        icon: '/icons/icon-192.png',
        tag: notification.id || 'notification',
        requireInteraction: notification.priority === 'urgente',
      });

      // Handle click
      browserNotification.onclick = () => {
        window.focus();
        this.handleClick(notification);
        browserNotification.close();
      };

      // Auto dismiss
      if (options.autoDismiss && options.autoDismiss > 0) {
        setTimeout(() => {
          browserNotification.close();
        }, options.autoDismiss);
      }
    } catch (error) {
      console.error('[NotificationHandler] Browser notification error:', error);
    }
  }

  /**
   * Get notification icon based on type.
   */
  static getIconForType(type: NotificationType): string {
    switch (type) {
      case 'success':
        return '/icons/notification-success.png';
      case 'warning':
        return '/icons/notification-warning.png';
      case 'error':
        return '/icons/notification-error.png';
      case 'info':
      default:
        return '/icons/notification-info.png';
    }
  }

  /**
   * Get badge count from storage.
   */
  static getBadgeCount(): number {
    try {
      const count = localStorage.getItem(BADGE_COUNT_KEY);
      return count ? parseInt(count, 10) : 0;
    } catch {
      return 0;
    }
  }

  /**
   * Set badge count in storage and update app badge.
   */
  static async setBadgeCount(count: number): Promise<void> {
    try {
      localStorage.setItem(BADGE_COUNT_KEY, String(count));

      // Update app badge if supported
      if ('setAppBadge' in navigator) {
        if (count > 0) {
          await (navigator as Navigator & { setAppBadge: (n: number) => Promise<void> })
            .setAppBadge(count);
        } else {
          await (navigator as Navigator & { clearAppBadge: () => Promise<void> })
            .clearAppBadge();
        }
      }
    } catch (error) {
      console.error('[NotificationHandler] Badge update error:', error);
    }
  }

  /**
   * Increment badge count.
   */
  static async incrementBadgeCount(): Promise<number> {
    const current = NotificationHandler.getBadgeCount();
    const newCount = current + 1;
    await NotificationHandler.setBadgeCount(newCount);
    return newCount;
  }

  /**
   * Clear badge count.
   */
  static async clearBadgeCount(): Promise<void> {
    await NotificationHandler.setBadgeCount(0);
  }
}

// Export singleton instance
export const notificationHandler = NotificationHandler.getInstance();

/**
 * Create a notification with standard formatting.
 */
export function createNotification(
  type: NotificationType,
  title: string,
  body: string,
  options?: {
    link?: string;
    recordId?: string;
    moduleSource?: string;
    priority?: NotificationPriority;
  }
): ParsedNotification {
  return {
    type,
    title,
    body,
    link: options?.link,
    recordId: options?.recordId,
    moduleSource: options?.moduleSource,
    priority: options?.priority ?? 'normale',
    timestamp: new Date(),
  };
}

/**
 * Show a toast-style notification in the app.
 * This should be connected to your app's toast/snackbar system.
 */
export function showInAppNotification(
  notification: ParsedNotification,
  toastHandler?: (notification: ParsedNotification) => void
): void {
  if (toastHandler) {
    toastHandler(notification);
  } else {
    // Default: log to console
    console.log('[Notification]', notification.type, notification.title, notification.body);
  }
}
