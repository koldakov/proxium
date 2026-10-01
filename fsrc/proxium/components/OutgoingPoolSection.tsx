import DeleteIcon from '@mui/icons-material/Delete'
import {
  Autocomplete,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { keepPreviousData, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import {
  type Identifier,
  type RaRecord,
  useDataProvider,
  useGetList,
  useNotify,
  useRecordContext,
  useResourceContext,
} from 'react-admin'

import type { ProxiumDataProvider } from '../providers'
import { AddOutgoingIPLink } from './AddOutgoingIPLink'
import { ShowSection } from './ShowSection'

const PER_PAGE_OPTIONS = [10, 25, 50]

// Options shown while typing: the search narrows them, the rest stay out of the request.
const OPTIONS_LIMIT = 20

const ipText = (record: RaRecord) => `${record.ip} · ${record.name}`

interface AddToPoolProps {
  resource: string
  id: Identifier
  onAdded: () => void
}

/** Offers only IPs the pool can take: not in it yet and of its family, the API picks them. */
const AddToPool = ({ resource, id, onAdded }: AddToPoolProps) => {
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const notify = useNotify()
  const [query, setQuery] = useState('')
  const {
    data: options = [],
    isFetching,
    refetch,
  } = useGetList(
    `${resource}/${id}/outgoing-ips/available`,
    // An empty query is refused by the API: no filter lists every IP.
    { filter: query ? { query } : {}, pagination: { page: 1, perPage: OPTIONS_LIMIT } },
    { placeholderData: keepPreviousData },
  )

  const { mutate, isPending } = useMutation({
    mutationFn: (outgoingIpId: Identifier) =>
      dataProvider.addToOutgoingPool(resource, { id, outgoingIpId }),
    onSuccess: () => {
      setQuery('')
      notify('Added to the pool', { type: 'success' })
      // The added IP leaves the options.
      refetch()
      onAdded()
    },
    onError: (error: Error) => notify(error.message, { type: 'error' }),
  })

  return (
    <Stack spacing={0.5}>
      <Autocomplete
        options={options}
        getOptionLabel={ipText}
        filterOptions={(items) => items}
        loading={isFetching}
        disabled={isPending}
        noOptionsText="No IPs to add"
        inputValue={query}
        onInputChange={(_, value, reason) => reason === 'input' && setQuery(value)}
        // Cleared after every pick: the input is for adding, not for holding a value.
        value={null}
        onChange={(_, record) => record && mutate(record.id)}
        renderInput={(params) => (
          <TextField
            {...params}
            size="small"
            label="Add an IP"
            // Inside a form Enter would submit it.
            onKeyDown={(event) => event.key === 'Enter' && event.preventDefault()}
          />
        )}
        sx={{ maxWidth: 480 }}
      />
      <AddOutgoingIPLink />
    </Stack>
  )
}

/**
 * The outgoing IP pool of the record in context, page by page, with adding and taking out IPs.
 * Changes apply at once, without saving the form around it.
 */
export const OutgoingPoolSection = () => {
  const resource = useResourceContext()
  const record = useRecordContext()
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const notify = useNotify()
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(PER_PAGE_OPTIONS[0])

  const {
    data = [],
    total = 0,
    refetch,
  } = useGetList(
    `${resource}/${record?.id}/outgoing-ips`,
    { pagination: { page, perPage } },
    // The old page stays on screen while the next one loads.
    { enabled: resource !== undefined && record !== undefined, placeholderData: keepPreviousData },
  )

  const { mutate: remove, isPending: isRemoving } = useMutation({
    mutationFn: (outgoingIpId: Identifier) =>
      dataProvider.removeFromOutgoingPool(resource!, { id: record!.id, outgoingIpId }),
    onSuccess: () => {
      notify('Taken out of the pool', { type: 'success' })
      // The last row of a page gone: back to the page before.
      if (data.length === 1 && page > 1) {
        setPage(page - 1)
      } else {
        refetch()
      }
    },
    onError: (error: Error) => notify(error.message, { type: 'error' }),
  })

  if (resource === undefined || record === undefined) {
    return null
  }

  // The saved mode, not the form's: the API keeps the last IP of a pool in use.
  const keepsLast = record.outgoingMode === 'pool' && total === 1

  return (
    <ShowSection title="Outgoing IP pool">
      <Typography variant="body2" color="text.secondary">
        Each connection goes out from a random IP of the pool. Changes apply at once.
      </Typography>
      <AddToPool resource={resource} id={record.id} onAdded={() => refetch()} />
      {total === 0 ? (
        <Typography variant="body2" color="text.secondary">
          The pool is empty: add an IP to go out through it
        </Typography>
      ) : (
        <>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>IP</TableCell>
                <TableCell>Name</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {data.map((outgoingIp) => (
                <TableRow key={outgoingIp.id}>
                  <TableCell>{outgoingIp.ip}</TableCell>
                  <TableCell>{outgoingIp.name}</TableCell>
                  <TableCell align="right">
                    <Tooltip
                      title={
                        keepsLast
                          ? 'The pool is in use and needs an IP: add another one first'
                          : 'Take out of the pool'
                      }
                    >
                      {/* A disabled button gets no hover, the span shows the reason. */}
                      <span>
                        <IconButton
                          size="small"
                          aria-label="Take out of the pool"
                          disabled={isRemoving || keepsLast}
                          onClick={() => remove(outgoingIp.id)}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={total}
            page={page - 1}
            rowsPerPage={perPage}
            rowsPerPageOptions={PER_PAGE_OPTIONS}
            onPageChange={(_, value) => setPage(value + 1)}
            onRowsPerPageChange={(event) => {
              setPerPage(Number(event.target.value))
              setPage(1)
            }}
          />
        </>
      )}
    </ShowSection>
  )
}
