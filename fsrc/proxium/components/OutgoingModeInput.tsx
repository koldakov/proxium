import { Stack } from '@mui/material'
import ipaddr from 'ipaddr.js'
import {
  AutocompleteArrayInput,
  FormDataConsumer,
  type RaRecord,
  ReferenceArrayInput,
  SelectInput,
  required,
  useCanAccess,
  useGetMany,
  useRecordContext,
} from 'react-admin'

import { AddOutgoingIPLink } from './AddOutgoingIPLink'
import { OUTGOING_MODES } from './outgoing'
import { OutgoingPoolSection } from './OutgoingPoolSection'

const MODE_HELP: Record<string, string> = {
  system: 'The OS picks, usually the main IP of the server',
  listener: 'The IP the client connected to',
  pool: 'A random IP of the pool, per connection',
}

// An empty query is refused by the API: no filter lists every IP.
const toQuery = (query: string) => (query ? { query } : {})

const ipText = (record: RaRecord) => `${record.ip} · ${record.name}`

/** The pool of a record being created: IPs of one family, the first one picked sets it. */
const NewPoolInput = ({ ids }: { ids: number[] }) => {
  // Only the first: it tells the family of the rest.
  const { data: [first] = [] } = useGetMany('outgoing-ips', { ids: ids.slice(0, 1) })
  const version = first ? (ipaddr.parse(first.ip).kind() === 'ipv6' ? 6 : 4) : undefined

  return (
    <Stack spacing={0.5} sx={{ mb: 2 }}>
      <ReferenceArrayInput
        source="outgoingIpIds"
        reference="outgoing-ips"
        filter={version ? { version } : {}}
      >
        <AutocompleteArrayInput
          label="Pool"
          optionText={ipText}
          filterToQuery={toQuery}
          validate={required()}
          // Leaves the form data with the input: another mode sends no pool.
          shouldUnregister
          helperText={
            version ? `IPv${version}, like the first IP` : 'IPs of one family, IPv4 or IPv6'
          }
        />
      </ReferenceArrayInput>
      <AddOutgoingIPLink />
    </Stack>
  )
}

/**
 * The outgoing mode of an account or trusted network, with its pool for `pool`.
 * A new record picks the pool in the form, a saved one edits it in place.
 */
export const OutgoingModeInput = () => {
  const record = useRecordContext()
  const isNew = record?.id === undefined
  // Filling a pool means picking IPs. A saved pool stays, its section shows it.
  const { canAccess: canPick } = useCanAccess({ resource: 'outgoing-ips', action: 'list' })
  const choices =
    canPick || record?.outgoingMode === 'pool'
      ? OUTGOING_MODES
      : OUTGOING_MODES.filter(({ id }) => id !== 'pool')

  return (
    <FormDataConsumer>
      {({ formData }) => (
        <>
          <SelectInput
            source="outgoingMode"
            label="Outgoing IP"
            choices={choices}
            validate={required()}
            helperText={MODE_HELP[formData.outgoingMode] ?? false}
          />
          {formData.outgoingMode === 'pool' &&
            (isNew ? <NewPoolInput ids={formData.outgoingIpIds ?? []} /> : <OutgoingPoolSection />)}
        </>
      )}
    </FormDataConsumer>
  )
}
