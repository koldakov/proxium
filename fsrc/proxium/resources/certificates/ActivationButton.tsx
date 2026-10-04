import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew'
import PowerOffIcon from '@mui/icons-material/PowerOff'
import { Typography } from '@mui/material'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import {
  Button,
  Confirm,
  useDataProvider,
  useGetList,
  useNotify,
  useRecordContext,
  useRefresh,
} from 'react-admin'

import type { ProxiumDataProvider } from '../../providers'
import { describeCertificate, isExpired } from './expiry'

/** Activates the certificate in context, or deactivates it if active. Hidden for an expired inactive one. */
export const ActivationButton = () => {
  const record = useRecordContext()
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const notify = useNotify()
  const refresh = useRefresh()
  const [confirming, setConfirming] = useState(false)
  // The confirmation names the certificate that activating turns off.
  const { data: active, isPending: isActivePending } = useGetList('certificates', {
    filter: { isActive: true },
    pagination: { page: 1, perPage: 1 },
  })

  const { mutate, isPending } = useMutation({
    mutationFn: () =>
      record!.isActive
        ? dataProvider.deactivate('certificates', { id: record!.id })
        : dataProvider.activate('certificates', {
            id: record!.id,
            replaces: active?.[0]?.id ?? null,
          }),
    onSuccess: () => {
      setConfirming(false)
      notify(record!.isActive ? 'Deactivated' : 'Activated', { type: 'success' })
      refresh()
    },
    onError: (error: Error) => {
      setConfirming(false)
      notify(error.message, { type: 'error' })
      // E.g. another admin activated one meanwhile: the page shows the current state to confirm again.
      refresh()
    },
  })

  // The API refuses an expired certificate: don't offer it. Nor before the active one is known: the confirmation
  // names it, and the API checks it's still the same.
  if (record === undefined || isActivePending || (!record.isActive && isExpired(record))) {
    return null
  }

  const current = active?.[0]
  const content = record.isActive ? (
    'TLS turns off: new TLS connections are refused, open ones stay. Plain HTTP and SOCKS5 keep working.'
  ) : current === undefined ? (
    'TLS turns on: new TLS connections get this certificate.'
  ) : (
    <>
      <Typography gutterBottom>New TLS connections get this certificate.</Typography>
      <Typography>
        The active certificate #{current.id} for {describeCertificate(current)}, valid until{' '}
        {new Date(current.notValidAfter).toLocaleDateString()}, will be <b>deactivated</b>. Open
        connections keep it until they close.
      </Typography>
    </>
  )

  return (
    <>
      {record.isActive ? (
        <Button label="Deactivate" color="error" onClick={() => setConfirming(true)}>
          <PowerOffIcon />
        </Button>
      ) : (
        <Button label="Activate" onClick={() => setConfirming(true)}>
          <PowerSettingsNewIcon />
        </Button>
      )}
      <Confirm
        isOpen={confirming}
        loading={isPending}
        title={record.isActive ? 'Deactivate' : 'Activate'}
        content={content}
        onConfirm={() => mutate()}
        onClose={() => setConfirming(false)}
      />
    </>
  )
}
