import { fetchUtils, HttpError } from 'react-admin'

import { getAccessToken } from './tokens'

// FastAPI error body: a message, or field errors for a 422.
interface ValidationIssue {
  loc: (string | number)[]
  msg: string
}

interface ErrorBody {
  detail?: string | ValidationIssue[]
}

// Body fields as keys, so react-admin shows them next to the inputs.
const toFieldErrors = (issues: ValidationIssue[]): Record<string, string> =>
  Object.fromEntries(
    issues
      .filter(({ loc }) => loc[0] === 'body' && loc.length > 1)
      .map(({ loc, msg }) => [loc.slice(1).join('.'), msg]),
  )

const toHttpError = (error: HttpError): HttpError => {
  const body = (error.body ?? {}) as ErrorBody
  if (typeof body.detail === 'string') {
    return new HttpError(body.detail, error.status, body)
  }
  if (Array.isArray(body.detail)) {
    const message = body.detail.map(({ msg }) => msg).join('\n')
    return new HttpError(message, error.status, { ...body, errors: toFieldErrors(body.detail) })
  }
  return error
}

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
