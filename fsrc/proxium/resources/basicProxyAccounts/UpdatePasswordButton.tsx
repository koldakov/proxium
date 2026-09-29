import PasswordIcon from '@mui/icons-material/Password'
import { Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import {
  Button,
  Form,
  PasswordInput,
  SaveButton,
  required,
  useDataProvider,
  useNotify,
  useRecordContext,
  useResourceContext,
} from 'react-admin'

import type { ProxiumDataProvider } from '../../providers'

interface PasswordForm {
  password: string
}

export const UpdatePasswordButton = () => {
  const record = useRecordContext()
  const resource = useResourceContext()
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const notify = useNotify()
  const [open, setOpen] = useState(false)

  const { mutate, isPending } = useMutation({
    mutationFn: ({ password }: PasswordForm) =>
      dataProvider.updatePassword(resource!, { id: record!.id, password }),
    onSuccess: () => {
      setOpen(false)
      notify('Password updated', { type: 'success' })
    },
    onError: (error: Error) => notify(error.message, { type: 'error' }),
  })

  if (record === undefined) {
    return null
  }

  return (
    <>
      <Button label="Set password" onClick={() => setOpen(true)}>
        <PasswordIcon />
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
        <Form onSubmit={(data: Partial<PasswordForm>) => mutate(data as PasswordForm)}>
          <DialogTitle>Set password</DialogTitle>
          <DialogContent>
            <PasswordInput source="password" validate={required()} fullWidth />
          </DialogContent>
          <DialogActions>
            <Button label="Cancel" onClick={() => setOpen(false)} />
            <SaveButton disabled={isPending} alwaysEnable />
          </DialogActions>
        </Form>
      </Dialog>
    </>
  )
}
