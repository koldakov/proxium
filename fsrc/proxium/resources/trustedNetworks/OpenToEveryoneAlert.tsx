import { Alert } from '@mui/material'
import { useGetList } from 'react-admin'

import { isEveryone } from './everyone'
import { NetworkLinks } from './NetworkLinks'

/** Caution while an active /0 network lets the whole internet use the proxy without a password. */
export const OpenToEveryoneAlert = () => {
  const { data } = useGetList('trusted-networks', {
    filter: { isActive: true, prefixLength: 0 },
    pagination: { page: 1, perPage: 10 },
  })
  // Saving changes cached records in place without a refetch: a network just turned off may still be here.
  const open = (data ?? []).filter((record) => record.isActive && isEveryone(record.network))
  if (open.length === 0) {
    return null
  }

  return (
    <Alert severity="error" sx={{ mb: 2 }}>
      The proxy is open to everyone: <NetworkLinks records={open} /> lets anyone on the internet use
      it without a password. Turn it off unless this is a development machine.
    </Alert>
  )
}

/** The same caution for a /0 network being typed, before it's saved. */
export const TypedEveryoneAlert = ({ network }: { network: string | undefined }) =>
  isEveryone(network) ? (
    <Alert severity="error" sx={{ mb: 2, width: '100%' }}>
      {network?.trim()} lets anyone on the internet use the proxy without a password.
    </Alert>
  ) : null
