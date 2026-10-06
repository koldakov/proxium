import { useState } from 'react'
import { Create, type RaRecord, SimpleForm, TextInput, required, useRedirect } from 'react-admin'

import { AwareDateTimeInput } from '../../components/AwareDateTimeInput'
import { OutgoingModeInput } from '../../components/OutgoingModeInput'
import { NewPoliciesInput } from '../../components/NewPoliciesInput'
import { SecretDialog } from '../../components/SecretDialog'
import { future } from '../../components/validators'

export const TokenProxyAccountCreate = () => {
  const redirect = useRedirect()
  // The token comes only in the create response: show it before leaving the page.
  const [created, setCreated] = useState<RaRecord | null>(null)

  return (
    <>
      <Create mutationOptions={{ onSuccess: setCreated }}>
        <SimpleForm defaultValues={{ outgoingMode: 'system' }}>
          <TextInput source="name" validate={required()} />
          <AwareDateTimeInput
            source="expiresAt"
            label="Expires"
            helperText="Empty: never"
            validate={future()}
          />
          <OutgoingModeInput />
          <NewPoliciesInput />
        </SimpleForm>
      </Create>
      {created !== null && (
        <SecretDialog
          title="Token"
          values={[{ label: 'Token', value: created.token, secret: true }]}
          onClose={() => redirect('show', 'token-proxy-accounts', created.id)}
        />
      )}
    </>
  )
}
