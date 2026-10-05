import { HttpError } from 'react-admin'

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

/** A FastAPI error as react-admin's: the `detail` is the message, field errors go next to the inputs. */
export const toHttpError = (error: HttpError): HttpError => {
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
