import type { QueryClient } from '@tanstack/react-query'
import type { AuthProvider, HttpError } from 'react-admin'

import { httpClient as defaultHttpClient, type HttpClient } from './httpClient'
import { clearTokens, getAccessToken, saveTokens } from './tokens'

interface LoginParams {
  username: string
  password: string
}

interface CanAccessParams {
  resource: string
  action: string
}

// The API checks on every request, this only hides what it would refuse. A change shows up within it, or at
// the first refusal.
const ME_TTL_MS = 60 * 1000

// React-admin actions by the API's names, the rest are the same, e.g. `revoke`.
const ACTIONS: Record<string, string> = {
  list: 'view',
  show: 'view',
  create: 'add',
  edit: 'change',
  delete: 'delete',
}

export interface Me {
  id: number
  email: string
  name: string
  surname: string
  isSuperuser: boolean
  // Every permission for a superuser.
  permissions: string[]
}

/**
 * The API permission for a react-admin check: `trusted-networks` and `edit` give `trusted_networks.change`.
 * Nested resources, e.g. `traffic/trusted-networks/1`, take the first part.
 */
export const toPermission = (resource: string, action: string): string =>
  `${resource.split('/')[0].replaceAll('-', '_')}.${ACTIONS[action] ?? action}`

export interface AuthProviderOptions {
  httpClient?: HttpClient
  // The one react-admin uses: a 403 re-runs its permission checks at once.
  queryClient?: QueryClient
}

/** JWT login against `/api/tokens`, the identity and permissions from `/api/users/me`. */
export const createAuthProvider = (
  apiUrl: string,
  { httpClient = defaultHttpClient, queryClient }: AuthProviderOptions = {},
): AuthProvider => {
  // Shared by the checks react-admin fires at once.
  let me: { promise: Promise<Me>; expiresAt: number } | null = null

  const getMe = (): Promise<Me> => {
    if (me === null || me.expiresAt < Date.now()) {
      const promise = httpClient(`${apiUrl}/api/users/me`).then(({ json }) => json as Me)
      // A failed request isn't kept: the next check asks again.
      promise.catch(() => {
        me = null
      })
      me = { promise, expiresAt: Date.now() + ME_TTL_MS }
    }
    return me.promise
  }

  return {
    login: async ({ username, password }: LoginParams) => {
      const { json } = await httpClient(`${apiUrl}/api/tokens`, {
        method: 'POST',
        body: JSON.stringify({ email: username, password }),
      })
      saveTokens(json)
      me = null
    },

    logout: async () => {
      clearTokens()
      me = null
    },

    checkAuth: async () => {
      if (getAccessToken() === null) {
        throw new Error('Not logged in.')
      }
    },

    checkError: async (error: HttpError) => {
      if (error.status === 401) {
        clearTokens()
        me = null
        throw error
      }
      // Permissions were taken away since the UI last asked: hide what the API refuses now. Not a logout.
      if (error.status === 403) {
        me = null
        void queryClient?.invalidateQueries({ queryKey: ['auth'] })
      }
    },

    getIdentity: async () => {
      const { id, name, surname, email } = await getMe()
      const fullName = [name, surname].filter(Boolean).join(' ')
      return { id, fullName: fullName || email }
    },

    getPermissions: async () => getMe(),

    canAccess: async ({ resource, action }: CanAccessParams) => {
      const { isSuperuser, permissions } = await getMe()
      return isSuperuser || permissions.includes(toPermission(resource, action))
    },
  }
}
