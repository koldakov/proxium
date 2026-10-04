import { Alert, Card, CardContent, Typography } from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrayInput,
  Form,
  FormDataConsumer,
  Loading,
  NumberInput,
  type RaRecord,
  ResourceContextProvider,
  SaveButton,
  SaveContextProvider,
  SimpleFormIterator,
  TextInput,
  Title,
  Toolbar,
  maxValue,
  minValue,
  required,
  useDataProvider,
  useNotify,
} from 'react-admin'

import { ipNetwork, toCidr } from '../../components/validators'
import type { ProxiumDataProvider, Settings } from '../../providers'

const QUERY_KEY = ['settings']

// A day: the API's limit too.
const MAX_TIMEOUT = 86400

// Networks are `{ network }` rows in the form, the API takes strings.
interface SettingsForm extends Omit<Settings, 'guardAllow'> {
  guardAllow: { network: string }[]
}

const toForm = (settings: Settings): SettingsForm => ({
  ...settings,
  guardAllow: settings.guardAllow.map((network) => ({ network })),
})

const fromForm = (form: SettingsForm): Settings => ({
  handshakeTimeout: form.handshakeTimeout,
  idleTimeout: form.idleTimeout,
  connectTimeout: form.connectTimeout,
  guardAllow: form.guardAllow.map(({ network }) => network.trim()),
})

// 10.0.0.5 and 10.0.0.5/32 are the same network: the API refuses both at once.
const uniqueNetworks = () => (rows: { network: string }[] | undefined) => {
  const cidrs = (rows ?? []).map(({ network }) => toCidr((network ?? '').trim()).toLowerCase())
  return new Set(cidrs).size === cidrs.length ? undefined : 'Each network once'
}

const timeoutValidators = [required(), minValue(1), maxValue(MAX_TIMEOUT)]

const GuardInputs = () => (
  <>
    <Typography variant="h6">Private networks</Typography>
    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
      The proxy reaches only the public internet: loopback, private networks and cloud metadata
      (169.254.169.254) are blocked, so clients can&apos;t get into this server&apos;s network. List
      the ones clients may reach anyway, e.g. an internal service.
    </Typography>
    <ArrayInput
      source="guardAllow"
      label="Allowed networks"
      validate={uniqueNetworks()}
      helperText="Empty: the public internet only"
    >
      <SimpleFormIterator inline disableReordering>
        <TextInput
          source="network"
          label="Network"
          validate={[required(), ipNetwork()]}
          helperText="E.g. 10.0.0.0/8, or 10.0.0.5 for a single address"
        />
      </SimpleFormIterator>
    </ArrayInput>
    <FormDataConsumer<SettingsForm>>
      {({ formData }) =>
        formData.guardAllow?.length ? (
          <Alert severity="warning" sx={{ mb: 2, width: '100%' }}>
            Every client of the proxy can reach these networks, accounts and trusted networks alike.
            Allow only what they need.
          </Alert>
        ) : null
      }
    </FormDataConsumer>
  </>
)

const TimeoutInputs = () => (
  <>
    <Typography variant="h6">Timeouts, seconds</Typography>
    <NumberInput
      source="handshakeTimeout"
      label="Handshake"
      validate={timeoutValidators}
      helperText="For a client to authenticate and send its request. Default 10"
    />
    <NumberInput
      source="idleTimeout"
      label="Idle"
      validate={timeoutValidators}
      helperText="A tunnel with no bytes either way for this long is closed. Default 300"
    />
    <NumberInput
      source="connectTimeout"
      label="Connect"
      validate={timeoutValidators}
      helperText="To resolve and connect to a target. Default 10"
    />
  </>
)

/** Proxy settings: one record, applied by the proxy to new connections within a few seconds. */
export const SettingsPage = () => {
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const queryClient = useQueryClient()
  const notify = useNotify()

  const { data, error } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => dataProvider.getSettings(),
  })
  const { mutate, isPending } = useMutation({
    mutationFn: (form: SettingsForm) => dataProvider.updateSettings(fromForm(form)),
    onSuccess: (saved) => {
      queryClient.setQueryData(QUERY_KEY, saved)
      notify('Saved: new connections get it within a few seconds, open ones keep the old', {
        type: 'success',
      })
    },
    onError: (error: Error) => notify(error.message, { type: 'error' }),
  })

  if (error) {
    return <Alert severity="error">{error.message}</Alert>
  }
  if (data === undefined) {
    return <Loading />
  }

  // Not a <Resource>, but inputs like SimpleFormIterator need a resource name in context.
  return (
    <ResourceContextProvider value="settings">
      <SaveContextProvider
        value={{
          save: (form: Partial<RaRecord>) => mutate(form as SettingsForm),
          saving: isPending,
        }}
      >
        <Title title="Settings" />
        <Card sx={{ mt: 2 }}>
          {/* Remounted on save: the form starts clean from what the API stored, e.g. 10.0.0.5/32. */}
          <Form key={JSON.stringify(data)} record={toForm(data)}>
            <CardContent>
              <GuardInputs />
              <TimeoutInputs />
            </CardContent>
            <Toolbar>
              <SaveButton />
            </Toolbar>
          </Form>
        </Card>
      </SaveContextProvider>
    </ResourceContextProvider>
  )
}
