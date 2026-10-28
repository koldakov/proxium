import { Chip, Stack, TablePagination, Typography } from '@mui/material'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useDataProvider, useRecordContext } from 'react-admin'

import type { ProxiumDataProvider } from '../../providers'

const PER_PAGE_OPTIONS = [50, 100, 250]

/** The IPs of the instance in context as of its last report, page by page, under its row. */
export const ProxyInstanceIPs = () => {
  const record = useRecordContext()
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(PER_PAGE_OPTIONS[0])
  const { data } = useQuery({
    queryKey: ['proxy-instances', 'getProxyInstanceIps', record?.id, page, perPage],
    queryFn: () => dataProvider.getProxyInstanceIps({ id: record!.id, page, perPage }),
    enabled: record !== undefined,
    // The old page stays on screen while the next one loads.
    placeholderData: keepPreviousData,
  })
  if (data === undefined) {
    return null
  }

  return (
    <Stack spacing={1} sx={{ py: 1 }}>
      <Typography variant="body2" color="text.secondary">
        IPs on its interfaces, the outgoing IPs it can connect from. In Docker bridge networking
        they are the container's, not the host's.
      </Typography>
      {data.total === 0 ? (
        <Typography variant="body2" color="text.secondary">
          None reported yet
        </Typography>
      ) : (
        <>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }} useFlexGap>
            {data.ips.map((ip) => (
              <Chip key={ip} label={ip} size="small" sx={{ fontFamily: 'monospace' }} />
            ))}
          </Stack>
          {data.total > PER_PAGE_OPTIONS[0] && (
            <TablePagination
              component="div"
              count={data.total}
              page={page - 1}
              rowsPerPage={perPage}
              rowsPerPageOptions={PER_PAGE_OPTIONS}
              onPageChange={(_, value) => setPage(value + 1)}
              onRowsPerPageChange={(event) => {
                setPerPage(Number(event.target.value))
                setPage(1)
              }}
            />
          )}
        </>
      )}
    </Stack>
  )
}
