import { useContext } from 'react';
import { AuthContext, AuthContextValue } from './AuthProvider';

/**
 * Hook to access authentication state and functions
 *
 * @returns Authentication context value
 * @throws Error if used outside of AuthProvider
 *
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { user, isAuthenticated, login, logout } = useAuth();
 *
 *   if (!isAuthenticated) {
 *     return <LoginForm onSubmit={login} />;
 *   }
 *
 *   return (
 *     <div>
 *       <p>Welcome, {user?.fullName}</p>
 *       <button onClick={logout}>Logout</button>
 *     </div>
 *   );
 * }
 * ```
 */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }

  return context;
}

/**
 * Hook to check if user has required permission
 * Returns false if not authenticated
 *
 * @param permission - The permission to check
 * @returns Whether the user has the permission
 *
 * @example
 * ```tsx
 * function AdminButton() {
 *   const canEdit = usePermission('invoices.edit');
 *
 *   if (!canEdit) return null;
 *
 *   return <button>Edit Invoice</button>;
 * }
 * ```
 */
export function usePermission(permission: string): boolean {
  const { hasPermission } = useAuth();
  return hasPermission(permission);
}

/**
 * Hook to check if user has any of the required permissions
 *
 * @param permissions - Array of permissions to check
 * @returns Whether the user has any of the permissions
 */
export function useAnyPermission(permissions: string[]): boolean {
  const { hasAnyPermission } = useAuth();
  return hasAnyPermission(permissions);
}

/**
 * Hook to check if user has all of the required permissions
 *
 * @param permissions - Array of permissions to check
 * @returns Whether the user has all of the permissions
 */
export function useAllPermissions(permissions: string[]): boolean {
  const { hasAllPermissions } = useAuth();
  return hasAllPermissions(permissions);
}

/**
 * Hook to get the current authenticated user
 * Returns null if not authenticated
 *
 * @returns The current user or null
 */
export function useUser() {
  const { user } = useAuth();
  return user;
}

/**
 * Hook to check authentication status
 *
 * @returns Object with isAuthenticated and isLoading flags
 */
export function useAuthStatus() {
  const { isAuthenticated, isLoading } = useAuth();
  return { isAuthenticated, isLoading };
}
