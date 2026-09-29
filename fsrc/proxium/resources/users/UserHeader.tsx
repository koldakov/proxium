import { Avatar, Chip, Stack, Typography } from '@mui/material'
import { useRecordContext } from 'react-admin'

/** The user's full name with initials, status and id, atop the show page. */
export const UserHeader = () => {
  const record = useRecordContext()
  if (record === undefined) {
    return null
  }

  const initials = `${record.name.charAt(0)}${record.surname.charAt(0)}`.toUpperCase()

  return (
    <Stack direction="row" alignItems="center" spacing={2}>
      <Avatar sx={{ width: 56, height: 56 }}>{initials}</Avatar>
      <Stack spacing={0.5}>
        <Stack direction="row" alignItems="center" spacing={1.5}>
          <Typography variant="h5">
            {record.name} {record.surname}
          </Typography>
          {record.isActive ? (
            <Chip label="Active" color="success" size="small" />
          ) : (
            <Chip label="Inactive" size="small" />
          )}
          {record.isSuperuser && <Chip label="Superuser" color="primary" size="small" />}
        </Stack>
        <Typography variant="body2" color="text.secondary">
          #{record.id}
        </Typography>
      </Stack>
    </Stack>
  )
}
