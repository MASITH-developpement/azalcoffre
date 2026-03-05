import React, { useMemo, useState } from 'react';

export interface CalendarEvent {
  /** Unique identifier */
  id: string;
  /** Event title */
  title: string;
  /** Event date (ISO string or Date) */
  date: string | Date;
  /** Event color */
  color?: 'primary' | 'success' | 'warning' | 'error';
  /** Additional metadata */
  meta?: Record<string, unknown>;
}

export interface CalendarWidgetProps {
  /** Events to display */
  events: CalendarEvent[];
  /** Handler when a day is clicked */
  onDayClick?: (date: Date, events: CalendarEvent[]) => void;
  /** Loading state */
  loading?: boolean;
  /** Widget title */
  title?: string;
}

const eventColorStyles = {
  primary: 'bg-primary-500',
  success: 'bg-green-500',
  warning: 'bg-amber-500',
  error: 'bg-red-500',
};

const DAYS_FR = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const MONTHS_FR = [
  'Janvier',
  'Fevrier',
  'Mars',
  'Avril',
  'Mai',
  'Juin',
  'Juillet',
  'Aout',
  'Septembre',
  'Octobre',
  'Novembre',
  'Decembre',
];

/**
 * Get the Monday of the current week
 */
function getWeekStart(date: Date): Date {
  const d = new Date(date);
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  d.setDate(diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

/**
 * Format date as YYYY-MM-DD for comparison
 */
function formatDateKey(date: Date): string {
  return date.toISOString().split('T')[0] ?? '';
}

/**
 * Check if two dates are the same day
 */
function isSameDay(date1: Date, date2: Date): boolean {
  return formatDateKey(date1) === formatDateKey(date2);
}

/**
 * Skeleton loader for CalendarWidget
 */
const CalendarSkeleton: React.FC = () => (
  <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden animate-pulse">
    <div className="px-4 py-3 border-b border-gray-100">
      <div className="h-5 w-32 bg-gray-200 rounded" />
    </div>
    <div className="p-4">
      {/* Day headers */}
      <div className="grid grid-cols-7 gap-1 mb-2">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="h-4 bg-gray-100 rounded" />
        ))}
      </div>
      {/* Day cells */}
      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: 7 }).map((_, i) => (
          <div
            key={i}
            className="aspect-square bg-gray-100 rounded-lg p-2 flex flex-col items-center justify-center"
          >
            <div className="h-5 w-5 bg-gray-200 rounded" />
          </div>
        ))}
      </div>
    </div>
  </div>
);

/**
 * Day cell component
 */
const DayCell: React.FC<{
  date: Date;
  isToday: boolean;
  events: CalendarEvent[];
  onClick?: () => void;
}> = ({ date, isToday, events, onClick }) => {
  const dayNumber = date.getDate();
  const hasEvents = events.length > 0;

  // Group events by color for dots
  const eventDots = useMemo(() => {
    const colors = new Set(events.map((e) => e.color || 'primary'));
    return Array.from(colors).slice(0, 3); // Max 3 dots
  }, [events]);

  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        aspect-square rounded-lg p-1
        flex flex-col items-center justify-center
        transition-all duration-150
        touch-manipulation
        min-h-[44px]
        ${isToday ? 'bg-primary-600 text-white' : 'bg-gray-50 text-gray-700 hover:bg-gray-100 active:bg-gray-200'}
        ${hasEvents && !isToday ? 'ring-1 ring-primary-200' : ''}
      `}
    >
      <span className={`text-sm font-medium ${isToday ? 'text-white' : ''}`}>
        {dayNumber}
      </span>

      {/* Event dots */}
      {eventDots.length > 0 && (
        <div className="flex gap-0.5 mt-1">
          {eventDots.map((color, i) => (
            <span
              key={i}
              className={`
                w-1.5 h-1.5 rounded-full
                ${isToday ? 'bg-white' : eventColorStyles[color]}
              `}
            />
          ))}
        </div>
      )}
    </button>
  );
};

/**
 * Events popup/list for selected day
 */
const DayEventsPopup: React.FC<{
  date: Date;
  events: CalendarEvent[];
  onClose: () => void;
}> = ({ date, events, onClose }) => {
  const dateStr = date.toLocaleDateString('fr-FR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });

  return (
    <div className="mt-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-sm font-medium text-gray-900 capitalize">
          {dateStr}
        </h4>
        <button
          type="button"
          onClick={onClose}
          className="p-1 text-gray-400 hover:text-gray-600 touch-manipulation"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>

      {events.length === 0 ? (
        <p className="text-sm text-gray-500">Aucun evenement</p>
      ) : (
        <ul className="space-y-2">
          {events.map((event) => (
            <li key={event.id} className="flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full ${eventColorStyles[event.color || 'primary']}`}
              />
              <span className="text-sm text-gray-700">{event.title}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

/**
 * CalendarWidget - Mini calendar/agenda widget for dashboards.
 * Shows current week with event indicators.
 * Mobile-optimized with touch-friendly day selection.
 */
export const CalendarWidget: React.FC<CalendarWidgetProps> = ({
  events,
  onDayClick,
  loading = false,
  title = 'Calendrier',
}) => {
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);

  const today = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }, []);

  const weekStart = useMemo(() => getWeekStart(today), [today]);

  const weekDays = useMemo(() => {
    const days: Date[] = [];
    for (let i = 0; i < 7; i++) {
      const day = new Date(weekStart);
      day.setDate(weekStart.getDate() + i);
      days.push(day);
    }
    return days;
  }, [weekStart]);

  // Group events by date
  const eventsByDate = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    events.forEach((event) => {
      const date = new Date(event.date);
      const key = formatDateKey(date);
      const existing = map.get(key) || [];
      map.set(key, [...existing, event]);
    });
    return map;
  }, [events]);

  const getEventsForDate = (date: Date): CalendarEvent[] => {
    return eventsByDate.get(formatDateKey(date)) || [];
  };

  const handleDayClick = (date: Date) => {
    const dayEvents = getEventsForDate(date);

    if (selectedDate && isSameDay(selectedDate, date)) {
      setSelectedDate(null);
    } else {
      setSelectedDate(date);
    }

    onDayClick?.(date, dayEvents);
  };

  const selectedEvents = selectedDate ? getEventsForDate(selectedDate) : [];

  // Week navigation label
  const weekLabel = useMemo(() => {
    const start = weekDays[0];
    const end = weekDays[6];
    if (!start || !end) return '';
    const startMonth = MONTHS_FR[start.getMonth()] ?? '';
    const endMonth = MONTHS_FR[end.getMonth()] ?? '';

    if (start.getMonth() === end.getMonth()) {
      return `${start.getDate()} - ${end.getDate()} ${startMonth}`;
    }
    return `${start.getDate()} ${startMonth} - ${end.getDate()} ${endMonth}`;
  }, [weekDays]);

  if (loading) {
    return <CalendarSkeleton />;
  }

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <h3 className="text-base font-semibold text-gray-900">{title}</h3>
        <span className="text-sm text-gray-500">{weekLabel}</span>
      </div>

      {/* Calendar */}
      <div className="p-4">
        {/* Day headers */}
        <div className="grid grid-cols-7 gap-1 mb-2">
          {DAYS_FR.map((day) => (
            <div
              key={day}
              className="text-center text-xs font-medium text-gray-500 py-1"
            >
              {day}
            </div>
          ))}
        </div>

        {/* Day cells */}
        <div className="grid grid-cols-7 gap-1">
          {weekDays.map((date) => (
            <DayCell
              key={formatDateKey(date)}
              date={date}
              isToday={isSameDay(date, today)}
              events={getEventsForDate(date)}
              onClick={() => handleDayClick(date)}
            />
          ))}
        </div>

        {/* Selected day events */}
        {selectedDate && (
          <DayEventsPopup
            date={selectedDate}
            events={selectedEvents}
            onClose={() => setSelectedDate(null)}
          />
        )}
      </div>
    </div>
  );
};

CalendarWidget.displayName = 'CalendarWidget';

export default CalendarWidget;
