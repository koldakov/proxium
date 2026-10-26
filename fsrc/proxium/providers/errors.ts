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

// A message of no field, as a form's `root.serverError`: a failed save shows it in the form, not in a toast.
const toFormError = (message: string) => ({ root: { serverError: message } })

/**
 * A FastAPI error as react-admin's: the `detail` is the message, field errors go next to the inputs, the rest
 * to the form as a whole.
 */
export const toHttpError = (error: HttpError): HttpError => {
  const body = (error.body ?? {}) as ErrorBody
  if (typeof body.detail === 'string') {
    return new HttpError(body.detail, error.status, { ...body, errors: toFormError(body.detail) })
  }
  if (Array.isArray(body.detail)) {
    const message = body.detail.map(({ msg }) => msg).join('\n')
    const fieldErrors = toFieldErrors(body.detail)
    const errors = Object.keys(fieldErrors).length > 0 ? fieldErrors : toFormError(message)
    return new HttpError(message, error.status, { ...body, errors })
  }
  return error
}
