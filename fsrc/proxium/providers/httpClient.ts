import { fetchUtils, HttpError } from 'react-admin'

import { toHttpError } from './errors'
import { getAccessToken } from './tokens'

/** `fetchJson` with the access token and FastAPI errors turned into react-admin ones. */
export const httpClient = async (
  url: string,
  options: fetchUtils.Options = {},
): ReturnType<typeof fetchUtils.fetchJson> => {
  const token = getAccessToken()
  const user = token === null ? options.user : { authenticated: true, token: `Bearer ${token}` }
  try {
    return await fetchUtils.fetchJson(url, { ...options, user })
  } catch (error) {
    throw error instanceof HttpError ? toHttpError(error) : error
  }
}

export type HttpClient = typeof httpClient
