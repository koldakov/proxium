import KeyIcon from '@mui/icons-material/Key'
import { Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material'
import { useState } from 'react'
import {
  Button,
  Form,
  PasswordInput,
  type RaRecord,
  SaveButton,
  minLength,
  required,
  useCanAccess,
  useDataProvider,
  useGetMany,
  useNotify,
  useRecordContext,
} from 'react-admin'

import { useMyPermissions } from '../../components/permissions'
import type { ProxiumDataProvider } from '../../providers'

// The API's limit too.
const MIN_PASSWORD_LENGTH = 8

const sameAsPassword = (value: string, values: Partial<RaRecord>) =>
  value === values.password ? undefined : "Doesn't match the password"

const SetPasswordDialog = ({ id, onClose }: { id: RaRecord['id']; onClose: () => void }) => {
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const notify = useNotify()

  const save = async (values: Partial<RaRecord>) => {
    try {
      await dataProvider.setUserPassword({ id, password: values.password })
    } catch (error) {
      notify((error as Error).message, { type: 'error' })
      return
    }
    onClose()
    notify('Password set', { type: 'success' })
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <Form onSubmit={save}>
        <DialogTitle>Set password</DialogTitle>
        <DialogContent>
          <PasswordInput
            source="password"
            label="New password"
            validate={[required(), minLength(MIN_PASSWORD_LENGTH)]}
            helperText={`At least ${MIN_PASSWORD_LENGTH} characters, the user can change it under Profile`}
          />
          <PasswordInput
            source="confirmPassword"
            label="New password again"
            validate={[required(), sameAsPassword]}
          />
        </DialogContent>
        <DialogActions>
          <Button label="Cancel" onClick={onClose} />
          <SaveButton label="Set password" icon={<KeyIcon />} />
        </DialogActions>
      </Form>
    </Dialog>
  )
}

/**
 * Sets the password of the user in context, e.g. a forgotten one. The password gives all the user's permissions,
 * so it's hidden unless the logged-in user has them too, as the API checks. Hidden for oneself: that's Profile.
 */
export const SetPasswordButton = () => {
  const record = useRecordContext()
  const me = useMyPermissions()
  const [open, setOpen] = useState(false)
  const { canAccess } = useCanAccess({ resource: 'users', action: 'edit' })
  const { canAccess: canListGroups } = useCanAccess({ resource: 'groups', action: 'list' })
  // Missing in the list's record, which react-admin shows until the user itself loads.
  const groupIds: number[] = record?.groupIds ?? []
  const { data: groups } = useGetMany(
    'groups',
    { ids: groupIds },
    { enabled: canListGroups === true && groupIds.length > 0 },
  )

  if (record === undefined || me === undefined || !canAccess || record.id === me.id) {
    return null
  }
  if (!me.isSuperuser) {
    const isLoadingGroups = canListGroups && groupIds.length > 0 && groups === undefined
    if (record.isSuperuser || isLoadingGroups) {
      return null
    }
    // Without `groups.view` the groups' permissions are unknown: the API decides.
    const permissions: string[] = [
      ...(record.permissions ?? []),
      ...(groups?.flatMap((group) => group.permissions) ?? []),
    ]
    if (permissions.some((code) => !me.permissions.includes(code))) {
      return null
    }
  }

  return (
    <>
      <Button label="Set password" onClick={() => setOpen(true)}>
        <KeyIcon />
      </Button>
      {open && <SetPasswordDialog id={record.id} onClose={() => setOpen(false)} />}
    </>
  )
}
