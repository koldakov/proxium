import { Alert } from '@mui/material'
import type { ChangeEvent } from 'react'
import {
  ArrayInput,
  BooleanInput,
  Create,
  FormDataConsumer,
  NumberInput,
  RadioButtonGroupInput,
  type RaRecord,
  SimpleForm,
  SimpleFormIterator,
  TextInput,
  maxValue,
  minValue,
  required,
  useGetList,
  useNotify,
  useRedirect,
} from 'react-admin'
import { useSearchParams } from 'react-router-dom'

import { describeCertificate } from './expiry'

const SOURCES = [
  { id: 'upload', name: 'Upload a certificate' },
  { id: 'generate', name: 'Generate a self-signed one' },
]

// Names are `{ name }` rows, the API takes strings. Only the chosen source's fields are sent.
const sourceFields = (data: RaRecord) =>
  data.source === 'upload'
    ? { source: 'upload', certificate: data.certificate, privateKey: data.privateKey }
    : {
        source: 'generate',
        names: data.names.map(({ name }: { name: string }) => name.trim()),
        days: data.days,
      }

const UploadInputs = () => (
  <>
    <TextInput
      source="certificate"
      label="Certificate chain (PEM)"
      multiline
      minRows={6}
      validate={required()}
      helperText="E.g. the contents of fullchain.pem: the server's certificate first, intermediates after it"
    />
    <TextInput
      source="privateKey"
      label="Private key (PEM)"
      multiline
      minRows={6}
      validate={required()}
      helperText="E.g. the contents of privkey.pem, without a password. Stored encrypted, never shown again"
    />
  </>
)

const GenerateInputs = () => (
  <>
    <Alert severity="info" sx={{ mb: 2 }}>
      Clients don&apos;t trust a self-signed certificate by default. Give them the certificate from
      its page, e.g. for curl&apos;s <code>--proxy-cacert</code>, or have them skip the check with{' '}
      <code>--proxy-insecure</code>.
    </Alert>
    <ArrayInput
      source="names"
      label="Names clients connect to"
      validate={required()}
      helperText="Only what clients check: the host or IP of the proxy URL, without the port. One certificate serves all ports"
    >
      <SimpleFormIterator inline disableReordering>
        <TextInput
          source="name"
          label="Host name or IP"
          validate={required()}
          helperText="E.g. proxy.example.com or 203.0.113.10"
        />
      </SimpleFormIterator>
    </ArrayInput>
    <NumberInput
      source="days"
      label="Valid for, days"
      validate={[required(), minValue(1), maxValue(3650)]}
      helperText="Clients refuse it afterwards. Nothing else, like organization or country, is needed: clients don't check it"
    />
  </>
)

export const CertificateCreate = () => {
  // The chosen source lives in `?source=`, so a reload or a shared link opens the same form.
  const [searchParams, setSearchParams] = useSearchParams()
  const sourceParam = searchParams.get('source')
  const source = SOURCES.some(({ id }) => id === sourceParam) ? sourceParam : 'upload'
  const notify = useNotify()
  const redirect = useRedirect()
  // The switch names the certificate it turns off, and the API checks it's still the active one.
  const {
    data: active,
    isPending,
    refetch,
  } = useGetList('certificates', {
    filter: { isActive: true },
    pagination: { page: 1, perPage: 1 },
  })

  // The switch defaults to the state it needs to know: render the form once it's known.
  if (isPending) {
    return null
  }
  const current: RaRecord | undefined = active?.[0]

  return (
    <Create
      transform={(data: RaRecord) => ({
        ...sourceFields(data),
        activate: data.activate,
        replaces: current?.id ?? null,
      })}
      mutationOptions={{
        onSuccess: (created: RaRecord) => {
          notify(
            created.isActive
              ? 'Added and active: TLS clients get it within a few seconds'
              : 'Added, not active yet: activate it on this page to give it to TLS clients',
            { type: created.isActive ? 'success' : 'info' },
          )
          redirect('show', 'certificates', created.id)
        },
        onError: (error: Error) => {
          notify(error.message, { type: 'error' })
          // E.g. another admin activated one meanwhile: the switch names the current one to decide again.
          refetch()
        },
      }}
    >
      {/* First certificate: activated by default, so it just works. Replacing one: only when asked. */}
      <SimpleForm
        defaultValues={{
          source,
          names: [{ name: '' }],
          days: 365,
          activate: current === undefined,
        }}
      >
        <RadioButtonGroupInput
          source="source"
          label="Certificate"
          choices={SOURCES}
          // Replaced, not pushed: Back leaves the form instead of stepping through the switches.
          onChange={(event: ChangeEvent<HTMLInputElement>) =>
            setSearchParams({ source: event.target.value }, { replace: true })
          }
        />
        <FormDataConsumer>
          {({ formData }) => (formData.source === 'upload' ? <UploadInputs /> : <GenerateInputs />)}
        </FormDataConsumer>
        <BooleanInput
          source="activate"
          label="Activate now"
          helperText={
            current === undefined
              ? 'TLS turns on with it: TLS clients get it within a few seconds. Off: added inactive, activate it later on its page'
              : `TLS clients get it within a few seconds instead of the certificate for ${describeCertificate(current)}, which is turned off. Off: added inactive, activate it later on its page`
          }
        />
      </SimpleForm>
    </Create>
  )
}
