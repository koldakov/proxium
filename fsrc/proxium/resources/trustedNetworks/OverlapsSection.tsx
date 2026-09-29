import { Stack, Typography } from '@mui/material'
import { BooleanField, DataTable, ListBase, Pagination, useListContext } from 'react-admin'

import { ShowSection } from '../../components/ShowSection'
import { NetworkLinkField } from './NetworkLinkField'
import { isComplete, useDebounced } from './overlaps'

interface OverlapsTableProps {
  title: string
  hint: string
}

// Hidden while empty or loading: most networks meet no others.
const OverlapsTable = ({ title, hint }: OverlapsTableProps) => {
  const { total, isPending, error } = useListContext()
  if (isPending || error || !total) {
    return null
  }

  return (
    <ShowSection title={`${title} (${total})`}>
      <Typography variant="body2" color="text.secondary">
        {hint}
      </Typography>
      <DataTable bulkActionButtons={false} rowClick={false}>
        <DataTable.Col source="network" disableSort field={NetworkLinkField} />
        <DataTable.Col source="name" disableSort />
        <DataTable.Col source="isActive" label="Active" field={BooleanField} disableSort />
      </DataTable>
      <Pagination rowsPerPageOptions={[5, 10, 25]} />
    </ShowSection>
  )
}

interface OverlapsListProps extends OverlapsTableProps {
  filter: Record<string, string>
}

// Its own pagination, apart from the URL and the main list.
const OverlapsList = ({ filter, ...props }: OverlapsListProps) => (
  <ListBase resource="trusted-networks" filter={filter} perPage={5} disableSyncWithLocation>
    <OverlapsTable {...props} />
  </ListBase>
)

/** Networks that contain `network` or lie inside it, while it's typed. Nothing is forbidden, only explained. */
export const OverlapsSection = ({ network }: { network: string | undefined }) => {
  const value = useDebounced((network ?? '').trim())
  if (!isComplete(value)) {
    return null
  }

  return (
    <Stack spacing={2} sx={{ mb: 2, width: '100%' }}>
      <OverlapsList
        filter={{ contains: value }}
        title="Networks containing this one"
        hint="Active ones keep trusting these addresses even if this network is turned off or deleted."
      />
      <OverlapsList
        filter={{ within: value }}
        title="Networks inside this one"
        hint="Active ones stay trusted on their own even if this network is turned off or deleted."
      />
    </Stack>
  )
}
