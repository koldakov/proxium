import { Alert } from '@mui/material'
import { useGetList } from 'react-admin'

import { describeCertificate, isExpired, isExpiringSoon } from './expiry'

/** Whether TLS clients get in right now, and with which certificate: atop the certificates list. */
export const TlsStatusAlert = () => {
  const { data, isPending, error } = useGetList('certificates', {
    filter: { isActive: true },
    pagination: { page: 1, perPage: 1 },
  })
  // The list below shows its own error.
  if (isPending || error) {
    return null
  }

  const active = data[0]
  if (active === undefined) {
    return (
      <Alert severity="info" sx={{ mb: 2 }}>
        TLS is off: clients connecting with TLS (<code>https://</code> proxy URLs) are refused,
        plain HTTP and SOCKS5 work. Add a certificate and activate it to turn TLS on.
      </Alert>
    )
  }

  const until = new Date(active.notValidAfter).toLocaleDateString()
  if (isExpired(active)) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        The active certificate for {describeCertificate(active)} expired on {until}: TLS clients
        refuse it. Add a new one and activate it.
      </Alert>
    )
  }
  return (
    <Alert severity={isExpiringSoon(active) ? 'warning' : 'success'} sx={{ mb: 2 }}>
      TLS is on: clients get the certificate for {describeCertificate(active)}, valid until {until}.
      {isExpiringSoon(active) && ' It expires soon, add a new one and activate it.'}
      <br />
      Activating another certificate applies to new connections within a few seconds, open ones keep
      theirs.
    </Alert>
  )
}
