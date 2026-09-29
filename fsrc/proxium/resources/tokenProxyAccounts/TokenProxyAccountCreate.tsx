import { useState } from 'react'
import { Create, type RaRecord, SimpleForm, TextInput, required, useRedirect } from 'react-admin'

import { AwareDateTimeInput } from '../../components/AwareDateTimeInput'
import { SecretDialog } from '../../components/SecretDialog'

export const TokenProxyAccountCreate = () => {
  const redirect = useRedirect()
  // The token comes only in the create response: show it before leaving the page.
  const [created, setCreated] = useState<RaRecord | null>(null)

  return (
    <>
      <Create mutationOptions={{ onSuccess: setCreated }}>
        <SimpleForm>
          <TextInput source="name" validate={required()} />
          <AwareDateTimeInput source="expiresAt" label="Expires" helperText="Empty: never" />
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
