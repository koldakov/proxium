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
  TextField,
} from '@mui/material'
import { useNotify } from 'react-admin'

interface SecretDialogProps {
  title: string
  secret: string
  onClose: () => void
}

/** Shows a secret the API returns only once, with a copy button. */
export const SecretDialog = ({ title, secret, onClose }: SecretDialogProps) => {
  const notify = useNotify()

  const copy = async () => {
    await navigator.clipboard.writeText(secret)
    notify('Copied', { type: 'info' })
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>
          Copy it now: it won't be shown again.
        </Alert>
        <TextField
          value={secret}
          fullWidth
          slotProps={{
            input: {
              readOnly: true,
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton onClick={copy} aria-label="Copy">
                    <ContentCopyIcon />
                  </IconButton>
                </InputAdornment>
              ),
            },
          }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Done</Button>
      </DialogActions>
    </Dialog>
  )
}
