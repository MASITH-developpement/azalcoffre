import React from 'react';

export interface RecentListItem {
  /** Unique identifier */
  id: string;
  /** Item icon (React node) */
  icon?: React.ReactNode;
  /** Item title */
  title: string;
  /** Item subtitle (optional) */
  subtitle?: string;
  /** Timestamp display string */
  timestamp?: string;
  /** Additional metadata */
  meta?: Record<string, unknown>;
}

export interface RecentListProps {
  /** Widget title */
  title: string;
  /** List of items to display */
  items: RecentListItem[];
  /** Handler when an item is clicked */
  onItemClick?: (item: RecentListItem) => void;
  /** Handler for "voir plus" link */
  onViewMore?: () => void;
  /** Maximum items to display (default: 5) */
  maxItems?: number;
  /** Loading state */
  loading?: boolean;
  /** Empty state message */
  emptyMessage?: string;
  /** "View more" link text */
  viewMoreText?: string;
}

/**
 * Skeleton loader for list items
 */
const ListItemSkeleton: React.FC = () => (
  <div className="flex items-center gap-3 py-3 animate-pulse">
    <div className="w-10 h-10 bg-gray-200 rounded-lg flex-shrink-0" />
    <div className="flex-1 min-w-0 space-y-2">
      <div className="h-4 w-32 bg-gray-200 rounded" />
      <div className="h-3 w-24 bg-gray-200 rounded" />
    </div>
    <div className="h-3 w-12 bg-gray-200 rounded" />
  </div>
);

/**
 * Empty state component
 */
const EmptyState: React.FC<{ message: string }> = ({ message }) => (
  <div className="py-8 text-center">
    <svg
      className="w-12 h-12 mx-auto text-gray-300"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={1.5}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
      />
    </svg>
    <p className="mt-3 text-sm text-gray-500">{message}</p>
  </div>
);

/**
 * Default icon when none provided
 */
const DefaultIcon: React.FC = () => (
  <svg
    className="w-5 h-5 text-gray-400"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    strokeWidth={1.5}
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
    />
  </svg>
);

/**
 * RecentList - Recent items widget for dashboards.
 * Displays a list of recent items with navigation capability.
 * Mobile-optimized with touch-friendly tap targets.
 */
export const RecentList: React.FC<RecentListProps> = ({
  title,
  items,
  onItemClick,
  onViewMore,
  maxItems = 5,
  loading = false,
  emptyMessage = 'Aucun element',
  viewMoreText = 'Voir plus',
}) => {
  const displayItems = items.slice(0, maxItems);
  const hasMore = items.length > maxItems;

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <h3 className="text-base font-semibold text-gray-900">{title}</h3>
        {(hasMore || onViewMore) && (
          <button
            type="button"
            onClick={onViewMore}
            className="text-sm font-medium text-primary-600 hover:text-primary-700 active:text-primary-800 touch-manipulation"
          >
            {viewMoreText}
          </button>
        )}
      </div>

      {/* Content */}
      <div className="px-4">
        {loading ? (
          // Loading skeleton
          <div className="divide-y divide-gray-100">
            {Array.from({ length: 3 }).map((_, i) => (
              <ListItemSkeleton key={i} />
            ))}
          </div>
        ) : displayItems.length === 0 ? (
          // Empty state
          <EmptyState message={emptyMessage} />
        ) : (
          // Items list
          <ul className="divide-y divide-gray-100">
            {displayItems.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onItemClick?.(item)}
                  disabled={!onItemClick}
                  className={`
                    w-full flex items-center gap-3 py-3
                    text-left
                    ${onItemClick ? 'cursor-pointer hover:bg-gray-50 active:bg-gray-100' : ''}
                    transition-colors duration-150
                    touch-manipulation
                    -mx-4 px-4
                  `}
                >
                  {/* Icon */}
                  <div className="flex-shrink-0 w-10 h-10 bg-gray-100 rounded-lg flex items-center justify-center">
                    {item.icon || <DefaultIcon />}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {item.title}
                    </p>
                    {item.subtitle && (
                      <p className="text-sm text-gray-500 truncate">
                        {item.subtitle}
                      </p>
                    )}
                  </div>

                  {/* Timestamp */}
                  {item.timestamp && (
                    <span className="flex-shrink-0 text-xs text-gray-400">
                      {item.timestamp}
                    </span>
                  )}

                  {/* Chevron (when clickable) */}
                  {onItemClick && (
                    <svg
                      className="w-5 h-5 text-gray-400 flex-shrink-0"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

RecentList.displayName = 'RecentList';

export default RecentList;
