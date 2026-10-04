import { useQuery } from '@tanstack/react-query'
import { useDataProvider, usePermissions } from 'react-admin'

import type { Me, ProxiumDataProvider } from '../providers'

export interface PermissionGroup {
  // As the API names it, e.g. `trusted_networks`.
  resource: string
  // E.g. "Trusted networks".
  label: string
  // In the order given, e.g. `['view', 'add']`.
  actions: string[]
}

const toLabel = (resource: string) => {
  const words = resource.replaceAll('_', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** `resource.action` codes by resource, both in the order given. */
export const groupPermissions = (codes: string[]): PermissionGroup[] => {
  const groups = new Map<string, PermissionGroup>()
  codes.forEach((code) => {
    const [resource, action] = code.split('.')
    if (!groups.has(resource)) {
      groups.set(resource, { resource, label: toLabel(resource), actions: [] })
    }
    groups.get(resource)!.actions.push(action)
  })
  return [...groups.values()]
}

/** Every permission there is, in the API's order: by resource, then view, add, change and the rest. */
export const useAllPermissions = () => {
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  return useQuery({
    queryKey: ['permissions'],
    queryFn: () => dataProvider.listPermissions(),
    // From the code: they change only with a new release.
    staleTime: Infinity,
  })
}

/**
 * The logged-in user's permissions, every one for a superuser. Undefined while loading.
 * Fetched on mount: the auth provider keeps them a minute, react-admin's own five would hide changes longer.
 */
export const useMyPermissions = (): Me | undefined =>
  usePermissions<Me>({}, { staleTime: 0 }).permissions
