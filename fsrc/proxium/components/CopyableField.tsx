import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import { IconButton, Stack, Tooltip, Typography } from '@mui/material'
import { useNotify, useRecordContext } from 'react-admin'

interface CopyableFieldProps {
  source: string
  // Read by `Labeled`.
  label?: string
}

/** A monospace value of the record in context with a copy button. */
export const CopyableField = ({ source }: CopyableFieldProps) => {
  const record = useRecordContext()
  const notify = useNotify()
  const value: string | undefined = record?.[source]
  if (value === undefined) {
    return null
  }

  const copy = async () => {
    await navigator.clipboard.writeText(value)
    notify('Copied', { type: 'info' })
  }

  return (
    <Stack direction="row" alignItems="center" spacing={0.5}>
      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
        {value}
      </Typography>
      <Tooltip title="Copy">
        <IconButton size="small" onClick={copy} aria-label={`Copy ${source}`}>
          <ContentCopyIcon fontSize="inherit" />
        </IconButton>
      </Tooltip>
    </Stack>
  )
}
