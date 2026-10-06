import {
  Checkbox,
  FormControlLabel,
  FormHelperText,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableRow,
  Typography,
} from '@mui/material'
import { Loading, useInput } from 'react-admin'

import { groupPermissions, useAllPermissions, useMyPermissions } from './permissions'

interface PermissionsInputProps {
  source?: string
  label?: string
  readOnly?: boolean
}

/**
 * Permission codes as checkboxes, a row per resource. Only the ones the logged-in user has can be ticked, the API
 * refuses the rest. Unticking is always allowed. Read-only, it only shows them.
 */
export const PermissionsInput = ({
  source = 'permissions',
  label = 'Permissions',
  readOnly = false,
}: PermissionsInputProps) => {
  const { field } = useInput({ source, defaultValue: [] })
  const { data: all } = useAllPermissions()
  const me = useMyPermissions()
  if (all === undefined || me === undefined) {
    return <Loading />
  }

  const value: string[] = field.value ?? []
  const toggle = (code: string, checked: boolean) =>
    // In the API's order, so an untouched form stays unchanged.
    field.onChange(all.filter((item) => (item === code ? checked : value.includes(item))))

  return (
    <Stack sx={{ mb: 2, width: '100%' }}>
      <Typography variant="subtitle1">{label}</Typography>
      <Table size="small">
        <TableBody>
          {groupPermissions(all).map(({ resource, label: resourceLabel, actions }) => (
            <TableRow key={resource}>
              <TableCell sx={{ whiteSpace: 'nowrap' }}>{resourceLabel}</TableCell>
              <TableCell>
                {actions.map((action) => {
                  const code = `${resource}.${action}`
                  const checked = value.includes(code)
                  return (
                    <FormControlLabel
                      key={code}
                      label={action}
                      disabled={readOnly || (!checked && !me.permissions.includes(code))}
                      control={
                        <Checkbox
                          size="small"
                          checked={checked}
                          onChange={(event) => toggle(code, event.target.checked)}
                        />
                      }
                    />
                  )
                })}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {!readOnly && !me.isSuperuser && (
        <FormHelperText>You can give only the permissions you have yourself</FormHelperText>
      )}
    </Stack>
  )
}
