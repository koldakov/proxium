import type { AuthProvider, HttpError } from 'react-admin'

import { httpClient as defaultHttpClient, type HttpClient } from './httpClient'
import { clearTokens, getAccessToken, saveTokens } from './tokens'

interface LoginParams {
  username: string
  password: string
}

/** JWT login against `/api/tokens`, the identity from `/api/users/me`. */
export const createAuthProvider = (
  apiUrl: string,
  httpClient: HttpClient = defaultHttpClient,
): AuthProvider => ({
  login: async ({ username, password }: LoginParams) => {
    const { json } = await httpClient(`${apiUrl}/api/tokens`, {
      method: 'POST',
      body: JSON.stringify({ email: username, password }),
    })
    saveTokens(json)
  },

  logout: async () => {
    clearTokens()
  },

  checkAuth: async () => {
    if (getAccessToken() === null) {
      throw new Error('Not logged in.')
    }
  },

  checkError: async (error: HttpError) => {
    if (error.status === 401) {
      clearTokens()
      throw error
    }
  },

  getIdentity: async () => {
    const { json } = await httpClient(`${apiUrl}/api/users/me`)
    const fullName = [json.name, json.surname].filter(Boolean).join(' ')
    return { id: json.id, fullName: fullName || json.email }
  },
})
