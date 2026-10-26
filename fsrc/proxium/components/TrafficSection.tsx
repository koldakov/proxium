import BarChartIcon from '@mui/icons-material/BarChart'
import TableRowsIcon from '@mui/icons-material/TableRows'
import { Box, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import { BarChart } from '@mui/x-charts/BarChart'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import prettyBytes from 'pretty-bytes'
import {
  DataTable,
  DateField,
  type Identifier,
  Labeled,
  ListContextProvider,
  type ListControllerResult,
  Pagination,
  type RaRecord,
  useCanAccess,
  useDataProvider,
  useGetList,
  useListContext,
  useListController,
  useLocation,
  useNavigate,
  useRecordContext,
  useResourceContext,
} from 'react-admin'

import type { ProxiumDataProvider } from '../providers'
import { ShowSection } from './ShowSection'

const DAY_MS = 24 * 60 * 60 * 1000

// The proxy writes traffic about once a minute. Only these queries poll, the rest of the page stays.
const REFRESH_MS = 60 * 1000

const PER_PAGE_OPTIONS = [7, 30, 90]

// Own names: they survive a reload and don't clash with other lists on the page.
const PAGE_PARAM = 'trafficPage'
const PER_PAGE_PARAM = 'trafficPerPage'
const VIEW_PARAM = 'trafficView'
const CHART_DAYS_PARAM = 'trafficDays'

const VIEWS = ['chart', 'table']
const CHART_DAYS_OPTIONS = [7, 30, 90]

// UTC, like the days the proxy counts.
const utcDaysAgo = (days: number) => new Date(Date.now() - days * DAY_MS).toISOString().slice(0, 10)

const formatDay = (day: string) =>
  new Date(day).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })

interface TrafficTotalProps {
  resource: string
  id: Identifier
  label: string
  since?: string
}

const TrafficTotal = ({ resource, id, label, since }: TrafficTotalProps) => {
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const { data } = useQuery({
    queryKey: [resource, 'getTrafficTotal', { id, since }],
    queryFn: () => dataProvider.getTrafficTotal(resource, { id, since }),
    refetchInterval: REFRESH_MS,
  })

  return (
    <Labeled label={label}>
      <Typography variant="body2">
        {data === undefined
          ? '…'
          : `${prettyBytes(data.bytesSent)} sent, ${prettyBytes(data.bytesReceived)} received`}
      </Typography>
    </Labeled>
  )
}

/** Page and page size from the URL. Replaced, not pushed: Back leaves the page instead of paging back. */
const useUrlPagination = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const search = new URLSearchParams(location.search)

  const page = Math.max(1, Math.trunc(Number(search.get(PAGE_PARAM))) || 1)
  const perPageParam = Number(search.get(PER_PAGE_PARAM))
  const perPage = PER_PAGE_OPTIONS.includes(perPageParam) ? perPageParam : PER_PAGE_OPTIONS[0]

  const update = (changes: Record<string, number>) => {
    const next = new URLSearchParams(location.search)
    Object.entries(changes).forEach(([key, value]) => next.set(key, String(value)))
    navigate({ search: `?${next}` }, { replace: true })
  }

  return {
    page,
    perPage,
    setPage: (value: number) => update({ [PAGE_PARAM]: value }),
    setPerPage: (value: number) => update({ [PER_PAGE_PARAM]: value, [PAGE_PARAM]: 1 }),
  }
}

/** One of `options` from the URL, the first by default. Replaced, not pushed, like the pagination. */
const useUrlChoice = <T extends string | number>(param: string, options: T[]) => {
  const location = useLocation()
  const navigate = useNavigate()
  const current = new URLSearchParams(location.search).get(param)
  const value = options.find((option) => String(option) === current) ?? options[0]

  const setValue = (next: T) => {
    const search = new URLSearchParams(location.search)
    search.set(param, String(next))
    navigate({ search: `?${search}` }, { replace: true })
  }

  return [value, setValue] as const
}

/**
 * A list context paged through the URL. React-admin's own URL sync uses the page's `page` and scrolls
 * to the top on every page change, the traffic sits at the bottom.
 */
const TrafficListBase = ({ resource, children }: { resource: string; children: ReactNode }) => {
  const pagination = useUrlPagination()
  // Only for the parts a list context needs besides the data: selection, sort, filters. Never fetches.
  const controller = useListController({
    resource,
    disableSyncWithLocation: true,
    queryOptions: { enabled: false },
  })
  const { data, total, isPending, isFetching, isLoading, error, refetch } = useGetList(
    resource,
    { pagination: { page: pagination.page, perPage: pagination.perPage } },
    // The old page stays on screen while the next one loads.
    { refetchInterval: REFRESH_MS, placeholderData: keepPreviousData },
  )

  const value = {
    ...controller,
    ...pagination,
    data,
    total,
    isPending,
    isFetching,
    isLoading,
    error,
    refetch,
    hasPreviousPage: pagination.page > 1,
    hasNextPage: total !== undefined && pagination.page * pagination.perPage < total,
  } as ListControllerResult

  return <ListContextProvider value={value}>{children}</ListContextProvider>
}

const TrafficTable = () => {
  const { total } = useListContext()

  return (
    <>
      <DataTable
        bulkActionButtons={false}
        rowClick={false}
        empty={
          <Typography variant="body2" color="text.secondary">
            No traffic yet
          </Typography>
        }
      >
        <DataTable.Col source="day" label="Day" disableSort>
          <DateField source="day" options={{ timeZone: 'UTC' }} />
        </DataTable.Col>
        <DataTable.Col
          source="bytesSent"
          label="Sent"
          disableSort
          render={(record: RaRecord) => prettyBytes(record.bytesSent)}
        />
        <DataTable.Col
          source="bytesReceived"
          label="Received"
          disableSort
          render={(record: RaRecord) => prettyBytes(record.bytesReceived)}
        />
      </DataTable>
      {!!total && <Pagination rowsPerPageOptions={PER_PAGE_OPTIONS} />}
    </>
  )
}

/** The last days, today included, oldest first. Days without traffic come as zeros, the API skips them. */
const TrafficChart = ({ resource }: { resource: string }) => {
  const [days, setDays] = useUrlChoice(CHART_DAYS_PARAM, CHART_DAYS_OPTIONS)
  const since = utcDaysAgo(days - 1)
  // At most one row per day, so one page holds them all.
  const { data } = useGetList(
    resource,
    { pagination: { page: 1, perPage: days }, filter: { since } },
    { refetchInterval: REFRESH_MS, placeholderData: keepPreviousData },
  )

  const byDay = new Map(data?.map((record) => [record.day, record]))
  const dataset = Array.from({ length: days }, (_, index) => {
    const day = utcDaysAgo(days - 1 - index)
    const record = byDay.get(day)
    return { day, bytesSent: record?.bytesSent ?? 0, bytesReceived: record?.bytesReceived ?? 0 }
  })
  const formatBytes = (value: number | null) => prettyBytes(value ?? 0)

  return (
    <Stack spacing={1}>
      <ToggleButtonGroup
        value={days}
        exclusive
        size="small"
        onChange={(_, value: number | null) => value !== null && setDays(value)}
      >
        {CHART_DAYS_OPTIONS.map((option) => (
          <ToggleButton key={option} value={option}>
            {option} days
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
      {/* Empty days are the chart's own overlay: the page keeps its height when switching days. */}
      <BarChart
        height={300}
        loading={data === undefined}
        dataset={data?.length === 0 ? [] : dataset}
        localeText={{ noData: `No traffic in the last ${days} days` }}
        borderRadius={4}
        xAxis={[{ scaleType: 'band', dataKey: 'day', valueFormatter: formatDay }]}
        yAxis={[{ valueFormatter: formatBytes, width: 70 }]}
        series={[
          { dataKey: 'bytesSent', label: 'Sent', valueFormatter: formatBytes },
          { dataKey: 'bytesReceived', label: 'Received', valueFormatter: formatBytes },
        ]}
      />
    </Stack>
  )
}

/**
 * Traffic of the record in context: totals, then days as a chart or as a table newest first, paged
 * through the URL. Hidden without `traffic.view`: seeing a record doesn't mean seeing its traffic.
 */
export const TrafficSection = () => {
  const resource = useResourceContext()
  const record = useRecordContext()
  const { canAccess } = useCanAccess({ resource: 'traffic', action: 'list' })
  const [view, setView] = useUrlChoice(VIEW_PARAM, VIEWS)
  if (resource === undefined || record === undefined || !canAccess) {
    return null
  }

  return (
    <ShowSection title="Traffic">
      <Typography variant="body2" color="text.secondary">
        Per UTC day, updated about once a minute. Sent is from the client, received is to it.
      </Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 2, sm: 6 }}>
        {/* Today included, so 30 days start 29 days ago. */}
        <TrafficTotal
          resource={resource}
          id={record.id}
          label="Last 30 days"
          since={utcDaysAgo(29)}
        />
        <TrafficTotal resource={resource} id={record.id} label="All time" />
      </Stack>
      <ToggleButtonGroup
        value={view}
        exclusive
        size="small"
        onChange={(_, value: string | null) => value !== null && setView(value)}
      >
        <ToggleButton value="chart" aria-label="Chart">
          <BarChartIcon fontSize="small" />
        </ToggleButton>
        <ToggleButton value="table" aria-label="Table">
          <TableRowsIcon fontSize="small" />
        </ToggleButton>
      </ToggleButtonGroup>
      {/*
        Both stay mounted and loaded: a view loading from scratch would shrink the page and scroll it up.
        One grid cell, the hidden chart keeps its space: a short table is as tall as the chart, the page
        below doesn't move when switching.
      */}
      <Box sx={{ display: 'grid', '& > *': { gridArea: '1 / 1', minWidth: 0 } }}>
        <Box sx={{ visibility: view === 'chart' ? 'visible' : 'hidden' }}>
          <TrafficChart resource={`traffic/${resource}/${record.id}`} />
        </Box>
        <Box sx={{ display: view === 'table' ? 'block' : 'none' }}>
          <TrafficListBase resource={`traffic/${resource}/${record.id}`}>
            <TrafficTable />
          </TrafficListBase>
        </Box>
      </Box>
    </ShowSection>
  )
}
