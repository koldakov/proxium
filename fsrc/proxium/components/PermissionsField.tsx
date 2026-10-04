import { Stack, Typography } from '@mui/material'
import { useRecordContext } from 'react-admin'

import { groupPermissions, useAllPermissions } from './permissions'

/** Permission codes of the record in context, a line per resource. */
export const PermissionsField = ({ source = 'permissions' }: { source?: string }) => {
  const record = useRecordContext()
  const { data: all } = useAllPermissions()
  const codes: string[] | undefined = record?.[source]
  // E.g. a list's record without them, shown until the full one loads.
  if (codes === undefined) {
    return null
  }
  if (codes.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        None
      </Typography>
    )
  }

  // The API's order, view before add, rather than the record's alphabetical one.
  const ordered = all === undefined ? codes : all.filter((code) => codes.includes(code))

  return (
    <Stack spacing={0.5}>
      {groupPermissions(ordered).map(({ resource, label, actions }) => (
        <Typography key={resource} variant="body2">
          {label}: {actions.join(', ')}
        </Typography>
      ))}
    </Stack>
  )
}
