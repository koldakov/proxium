import { jwtDecode } from 'jwt-decode'
import { fetchUtils } from 'react-admin'

import { apiUrl } from '../config'

export interface Tokens {
  access: string
  refresh: string
}

const ACCESS_KEY = 'proxium.access'
const REFRESH_KEY = 'proxium.refresh'
// Refresh ahead of time, so the token doesn't expire on the way to the server.
const EXPIRY_LEEWAY_SECONDS = 30

export const getAccessToken = (): string | null => localStorage.getItem(ACCESS_KEY)

export const saveTokens = ({ access, refresh }: Tokens): void => {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export const clearTokens = (): void => {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

const isExpiring = (token: string): boolean => {
  const { exp } = jwtDecode(token)
  return exp === undefined || exp - EXPIRY_LEEWAY_SECONDS < Date.now() / 1000
}

const requestTokens = async (refresh: string): Promise<void> => {
  const { json } = await fetchUtils.fetchJson(`${apiUrl}/api/tokens/refresh`, {
    method: 'POST',
    body: JSON.stringify({ refresh }),
  })
  saveTokens(json)
}

// Shared by the calls react-admin fires at once, so they wait for a single refresh.
let pending: Promise<void> | null = null

/** Swaps the refresh token for new tokens if the access one is about to expire. */
export const refreshTokens = async (): Promise<void> => {
  const access = localStorage.getItem(ACCESS_KEY)
  const refresh = localStorage.getItem(REFRESH_KEY)
  if (access === null || refresh === null || !isExpiring(access)) {
    return
  }
  pending ??= requestTokens(refresh).finally(() => {
    pending = null
  })
  await pending
}
