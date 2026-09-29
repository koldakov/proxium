import { Stack, Typography } from '@mui/material'
import { useGetList, useRecordContext } from 'react-admin'

import { countNetworks } from './overlaps'

// Only the total is needed: one record per page.
const useActiveCount = (filter: Record<string, string>, enabled: boolean) =>
  useGetList(
    'trusted-networks',
    { filter: { ...filter, isActive: true }, pagination: { page: 1, perPage: 1 } },
    { enabled },
  ).total ?? 0

/** What deleting the network in context changes, with the networks that keep trusting its addresses. */
export const DeleteConfirmContent = () => {
  const record = useRecordContext()
  const network: string = record?.network ?? ''
  const containing = useActiveCount({ contains: network }, network !== '')
  const inside = useActiveCount({ within: network }, network !== '')

  return (
    <Stack spacing={1}>
      <Typography>New connections from this network will need a password.</Typography>
      {containing > 0 && (
        <Typography>
          Its addresses stay trusted through {countNetworks(containing, 'active')} containing it.
        </Typography>
      )}
      {inside > 0 && (
        <Typography>
          {countNetworks(inside, 'active')} inside it stay trusted on their own.
        </Typography>
      )}
      <Typography color="text.secondary">
        Clients connected right now keep their open connections until they close. The networks are
        listed on this page.
      </Typography>
    </Stack>
  )
}
