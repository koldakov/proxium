import { Alert } from '@mui/material'

/** What trusting a network means, atop every trusted networks page. */
export const TrustedNetworksWarning = () => (
  <Alert severity="warning" sx={{ mb: 2 }}>
    Clients from these networks use the proxy without a password. Add only networks you control,
    such as a local network or a development machine.
    <br />
    New connections follow your changes right away. Clients connected right now keep their open
    connections until they close, so removing a network doesn&apos;t cut them off at once.
  </Alert>
)
