/**
 * Dashboard Widgets for AZALPLUS Mobile PWA
 *
 * A collection of mobile-optimized dashboard widgets with:
 * - Loading state skeletons
 * - Touch-friendly interactions
 * - Consistent styling with Tailwind CSS
 * - TypeScript interfaces for type safety
 */

// StatCard - Metric display widget
export { StatCard, type StatCardProps, type ChangeType } from './StatCard';

// RecentList - Recent items widget
export {
  RecentList,
  type RecentListProps,
  type RecentListItem,
} from './RecentList';

// ChartWidget - Simple bar/line chart
export {
  ChartWidget,
  type ChartWidgetProps,
  type ChartDataPoint,
  type ChartType,
} from './ChartWidget';

// QuickActionsWidget - Grid of quick action buttons
export {
  QuickActionsWidget,
  type QuickActionsWidgetProps,
  type QuickAction,
} from './QuickActionsWidget';

// AlertsWidget - Notifications/alerts list
export {
  AlertsWidget,
  type AlertsWidgetProps,
  type AlertItem,
  type AlertPriority,
} from './AlertsWidget';

// CalendarWidget - Mini calendar/agenda
export {
  CalendarWidget,
  type CalendarWidgetProps,
  type CalendarEvent,
} from './CalendarWidget';
