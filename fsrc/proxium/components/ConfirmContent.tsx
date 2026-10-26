import { Alert, DialogContentText } from '@mui/material'
import type { ReactNode } from 'react'

interface ConfirmContentProps {
  // A string is styled as `Confirm` styles its own.
  text: ReactNode
  // Of the last try: the dialog stays open to try again or cancel.
  error: Error | null
}

/** A confirmation's text and, when the action failed, why: in the dialog instead of a toast behind it. */
export const ConfirmContent = ({ text, error }: ConfirmContentProps) => (
  <>
    {typeof text === 'string' ? <DialogContentText>{text}</DialogContentText> : text}
    {error !== null && (
      <Alert severity="error" sx={{ mt: 2 }}>
        {error.message}
      </Alert>
    )}
  </>
)
