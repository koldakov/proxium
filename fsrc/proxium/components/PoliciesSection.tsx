import DeleteIcon from '@mui/icons-material/Delete'
import EditCalendarIcon from '@mui/icons-material/EditCalendar'
import {
  Autocomplete,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { keepPreviousData, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import {
  type Identifier,
  Link,
  useCanAccess,
  useCreatePath,
  useDataProvider,
  useGetList,
  useNotify,
  useRecordContext,
  useResourceContext,
} from 'react-admin'

import type { ProxiumDataProvider } from '../providers'
import { useDetailPage } from './detailPage'
import { useConfigs } from './configs'
import { ShowSection } from './ShowSection'

// The API caps assigned policies at `API_POLICIES_MAX_PER_OWNER`, up to 100, the largest page:
// one shows them all.
const ASSIGNED_LIMIT = 100

// Options offered at once: the search finds the rest, they stay out of the request.
const OPTIONS_LIMIT = 5

// Global policies named next to the assigned ones, the rest are behind the link to the list.
const GLOBAL_LIMIT = 10

interface AssignProps {
  resource: string
  id: Identifier
  onAssigned: () => void
}

/** Offers only policies the record can take: not assigned yet and not global, the API picks them. */
const Assign = ({ resource, id, onAssigned }: AssignProps) => {
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const notify = useNotify()
  const [query, setQuery] = useState('')
  const {
    data: options = [],
    total = 0,
    isFetching,
    refetch,
  } = useGetList(
    `${resource}/${id}/policies/available`,
    // An empty query is refused by the API: no filter lists every policy.
    { filter: query ? { query } : {}, pagination: { page: 1, perPage: OPTIONS_LIMIT } },
    { placeholderData: keepPreviousData },
  )

  const { mutate, isPending } = useMutation({
    mutationFn: (policyId: Identifier) => dataProvider.assignPolicy(resource, { id, policyId }),
    onSuccess: () => {
      setQuery('')
      notify('Policy assigned', { type: 'success' })
      // The assigned policy leaves the options.
      refetch()
      onAssigned()
    },
    onError: (error: Error) => notify(error.message, { type: 'error' }),
  })

  return (
    <Autocomplete
      options={options}
      getOptionLabel={(policy) => (policy.isActive ? policy.name : `${policy.name} (inactive)`)}
      filterOptions={(items) => items}
      loading={isFetching}
      disabled={isPending}
      noOptionsText="No policies to assign"
      inputValue={query}
      onInputChange={(_, value, reason) => reason === 'input' && setQuery(value)}
      // Cleared after every pick: the input is for assigning, not for holding a value.
      value={null}
      onChange={(_, policy) => policy && mutate(policy.id)}
      renderInput={(params) => (
        <TextField
          {...params}
          size="small"
          label="Assign a policy"
          helperText={
            total > options.length && `First ${options.length} of ${total}, type to find the rest`
          }
          // Inside a form Enter would submit it.
          onKeyDown={(event) => event.key === 'Enter' && event.preventDefault()}
        />
      )}
      sx={{ maxWidth: 480 }}
    />
  )
}

// A UTC day `YYYY-MM-DD` as people read it, e.g. "Oct 6, 2026". Not shifted by the local time zone.
const formatDay = (day: string) =>
  new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, {
    timeZone: 'UTC',
    dateStyle: 'medium',
  })

interface StartsOnDialogProps {
  resource: string
  id: Identifier
  policyId: Identifier
  policyName: string
  startsOn: string
  onClose: () => void
  onChanged: () => void
}

/** Picks the new day and asks to confirm it: the change recounts usage at once. */
const StartsOnDialog = ({
  resource,
  id,
  policyId,
  policyName,
  startsOn,
  onClose,
  onChanged,
}: StartsOnDialogProps) => {
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const notify = useNotify()
  const [value, setValue] = useState(startsOn)

  const { mutate, isPending } = useMutation({
    mutationFn: (day: string) =>
      dataProvider.setPolicyStart(resource, { id, policyId, startsOn: day }),
    onSuccess: () => {
      notify('Quota periods start changed', { type: 'success' })
      onChanged()
      onClose()
    },
    onError: (error: Error) => notify(error.message, { type: 'error' }),
  })

  // Empty while the date is cleared or half-typed.
  const canSave = value !== '' && value !== startsOn && !isPending

  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Quota periods of {policyName}</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>
          Periods follow one another from this UTC day, e.g. the day the client paid. Usage is
          recounted for the new period at once: a client over its quota may be cut, or let back in.
        </DialogContentText>
        <TextField
          type="date"
          label="Count from"
          size="small"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
          autoFocus
          fullWidth
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!canSave} onClick={() => mutate(value)}>
          Change
        </Button>
      </DialogActions>
    </Dialog>
  )
}

interface StartsOnFieldProps extends Omit<StartsOnDialogProps, 'onClose'> {
  // Unknown while the permissions load: no button until they say so.
  canChange?: boolean
}

/** The day quota periods of an assigned policy count from for the record, changed in a dialog. */
const StartsOnField = ({ canChange, ...dialogProps }: StartsOnFieldProps) => {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
      <Typography variant="body2">{formatDay(dialogProps.startsOn)}</Typography>
      {canChange && (
        <Tooltip title="Change">
          <IconButton size="small" aria-label="Change" onClick={() => setIsOpen(true)}>
            <EditCalendarIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
      {isOpen && <StartsOnDialog {...dialogProps} onClose={() => setIsOpen(false)} />}
    </Stack>
  )
}

/** The active global policies, which apply to every client without assigning. */
const GlobalPolicies = () => {
  const createPath = useCreatePath()
  const detailPage = useDetailPage('policies')
  const { data = [], total = 0 } = useGetList('policies', {
    filter: { isGlobal: true },
    pagination: { page: 1, perPage: GLOBAL_LIMIT },
  })
  const active = data.filter((policy) => policy.isActive)
  if (active.length === 0) {
    return null
  }

  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
      <Typography variant="body2" color="text.secondary">
        Global, apply to every client:
      </Typography>
      {active.map((policy) => (
        <Link
          key={policy.id}
          to={createPath({ resource: 'policies', type: detailPage, id: policy.id })}
        >
          <Chip size="small" label={policy.name} clickable />
        </Link>
      ))}
      {total > GLOBAL_LIMIT && (
        <Link to={createPath({ resource: 'policies', type: 'list' })}>and more</Link>
      )}
    </Stack>
  )
}

/**
 * The policies of the record in context, with assigning and taking them off.
 * Changes apply at once, without saving the form around it.
 */
export const PoliciesSection = () => {
  const resource = useResourceContext()
  const record = useRecordContext()
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const notify = useNotify()
  const createPath = useCreatePath()
  const detailPage = useDetailPage('policies')
  // Assigning is changing the record, picking a policy needs seeing them.
  const { canAccess: canChange } = useCanAccess({ resource, action: 'edit' })
  const { canAccess: canPick } = useCanAccess({ resource: 'policies', action: 'list' })

  const configs = useConfigs()

  const {
    data = [],
    total = 0,
    refetch,
  } = useGetList(
    `${resource}/${record?.id}/policies`,
    { pagination: { page: 1, perPage: ASSIGNED_LIMIT } },
    { enabled: resource !== undefined && record !== undefined },
  )

  const { mutate: unassign, isPending: isUnassigning } = useMutation({
    mutationFn: (policyId: Identifier) =>
      dataProvider.unassignPolicy(resource!, { id: record!.id, policyId }),
    onSuccess: () => {
      notify('Policy taken off', { type: 'success' })
      refetch()
    },
    onError: (error: Error) => notify(error.message, { type: 'error' }),
  })

  if (resource === undefined || record === undefined) {
    return null
  }

  const max = configs?.policiesMaxPerOwner
  // Assigning one more would be refused: no picker, the reason instead.
  const isFull = max !== undefined && total >= max
  // Where quota periods start matters only for policies with quotas.
  const hasQuotas = data.some((policy) => policy.hasTrafficQuotas)

  return (
    <ShowSection title="Policies">
      <Typography variant="body2" color="text.secondary">
        Limits of every policy apply at once.
        {canChange && ' Changes reach the proxy within the cache TTL from the settings.'}
        {max !== undefined && ` Assigned ${total} of ${max} at most.`}
      </Typography>
      {canPick && <GlobalPolicies />}
      {canChange &&
        canPick &&
        (isFull ? (
          <Typography variant="body2" color="warning.main">
            The limit of {max} policies is reached: take one off to assign another
          </Typography>
        ) : (
          <Assign resource={resource} id={record.id} onAssigned={() => refetch()} />
        ))}
      {data.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No policies assigned
        </Typography>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Status</TableCell>
              {hasQuotas && (
                <TableCell>
                  <Tooltip title="UTC day quota periods count from for this record, e.g. the day it paid. The day of assigning unless changed">
                    <span>Quotas count from</span>
                  </Tooltip>
                </TableCell>
              )}
              {canChange && <TableCell />}
            </TableRow>
          </TableHead>
          <TableBody>
            {data.map((policy) => (
              <TableRow key={policy.id}>
                <TableCell>
                  {canPick ? (
                    <Link
                      to={createPath({ resource: 'policies', type: detailPage, id: policy.id })}
                    >
                      {policy.name}
                    </Link>
                  ) : (
                    policy.name
                  )}
                </TableCell>
                <TableCell>
                  {policy.isActive ? (
                    <Chip size="small" color="success" label="Active" />
                  ) : (
                    <Tooltip title="Turned off on the policy page: it applies to no one">
                      <Chip size="small" label="Inactive" />
                    </Tooltip>
                  )}
                </TableCell>
                {hasQuotas && (
                  <TableCell>
                    {policy.hasTrafficQuotas ? (
                      <StartsOnField
                        canChange={canChange}
                        resource={resource}
                        id={record.id}
                        policyId={policy.id}
                        policyName={policy.name}
                        startsOn={policy.startsOn}
                        onChanged={() => refetch()}
                      />
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        No quotas
                      </Typography>
                    )}
                  </TableCell>
                )}
                {canChange && (
                  <TableCell align="right">
                    <Tooltip title="Take off">
                      <span>
                        <IconButton
                          size="small"
                          aria-label="Take off"
                          disabled={isUnassigning}
                          onClick={() => unassign(policy.id)}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </ShowSection>
  )
}
