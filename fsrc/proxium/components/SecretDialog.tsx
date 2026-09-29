import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  Stack,
  TextField,
} from '@mui/material'
import { useNotify } from 'react-admin'

export interface SecretValue {
  label: string
  value: string
  // Returned only once, e.g. a password. Others, e.g. a username, stay visible later.
  secret?: boolean
}

interface SecretDialogProps {
  title: string
  values: SecretValue[]
  onClose: () => void
}

/** Shows freshly created credentials, each with a copy button, and warns about the ones shown only once. */
export const SecretDialog = ({ title, values, onClose }: SecretDialogProps) => {
  const notify = useNotify()
  const secrets = values.filter(({ secret }) => secret).map(({ label }) => label.toLowerCase())

  const copy = async (value: string) => {
    await navigator.clipboard.writeText(value)
    notify('Copied', { type: 'info' })
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>
          Copy the {secrets.join(' and ')} now: it won't be shown again.
        </Alert>
        <Stack spacing={2}>
          {values.map(({ label, value }) => (
            <TextField
              key={label}
              label={label}
              value={value}
              fullWidth
              slotProps={{
                input: {
                  readOnly: true,
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton onClick={() => copy(value)} aria-label={`Copy ${label}`}>
                        <ContentCopyIcon />
                      </IconButton>
                    </InputAdornment>
                  ),
                },
              }}
            />
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Done</Button>
      </DialogActions>
    </Dialog>
  )
}
