import { Alert } from '@mui/material'
import { useFormState } from 'react-hook-form'

/** Why the last save failed, when it's about no single input: in the form, above its buttons. */
export const FormErrorAlert = () => {
  // react-hook-form changes `errors` in place: React Compiler would keep the first, empty, one.
  'use no memo'
  const { errors } = useFormState()
  const message = errors.root?.serverError?.message
  if (!message) {
    return null
  }

  return (
    <Alert severity="error" sx={{ width: '100%', mt: 1, whiteSpace: 'pre-line' }}>
      {message}
    </Alert>
  )
}
