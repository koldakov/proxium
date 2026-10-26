import { Stack } from '@mui/material'
import { useState } from 'react'
import { Create, type RaRecord, TextInput, required, useRedirect } from 'react-admin'

import { AwareDateTimeInput } from '../../components/PickerInputs'
import { OutgoingModeInput } from '../../components/OutgoingModeInput'
import { NewPoliciesInput } from '../../components/NewPoliciesInput'
import { SecretDialog } from '../../components/SecretDialog'
import { future } from '../../components/validators'
import { GuardedSimpleForm } from '../../components/UnsavedChangesGuard'

export const BasicProxyAccountCreate = () => {
  const redirect = useRedirect()
  // The generated password comes only in the create response: show it before leaving the page.
  const [created, setCreated] = useState<RaRecord | null>(null)

  return (
    <>
      <Create mutationOptions={{ onSuccess: setCreated }}>
        <GuardedSimpleForm defaultValues={{ outgoingMode: 'system' }}>
          <TextInput source="name" validate={required()} />
          {/* Short fields side by side, on a phone one under the other. */}
          <Stack direction={{ xs: 'column', sm: 'row' }} sx={{ width: '100%', columnGap: 2 }}>
            <AwareDateTimeInput
              source="expiresAt"
              label="Expires"
              helperText="Empty: never"
              validate={future()}
            />
            <OutgoingModeInput />
          </Stack>
          <NewPoliciesInput />
        </GuardedSimpleForm>
      </Create>
      {created !== null && (
        <SecretDialog
          title="Credentials"
          values={[
            { label: 'Username', value: created.username },
            { label: 'Password', value: created.password, secret: true },
          ]}
          onClose={() => redirect('show', 'basic-proxy-accounts', created.id)}
        />
      )}
    </>
  )
}
