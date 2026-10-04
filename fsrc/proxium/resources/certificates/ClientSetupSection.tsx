import DownloadIcon from '@mui/icons-material/Download'
import { Box, Typography } from '@mui/material'
import { Button, useRecordContext } from 'react-admin'

import { ShowSection } from '../../components/ShowSection'

// The proxy doesn't know the port clients reach it on: it may be behind NAT or listen on many.
const PORT = 'PORT'

// Long enough for any browser to have taken the file, like FileSaver.js does.
const REVOKE_DELAY_MS = 40_000

/** How clients connect over TLS with the certificate in context, and the file a self-signed one needs. */
export const ClientSetupSection = () => {
  const record = useRecordContext()
  if (record === undefined) {
    return null
  }

  const fileName = `proxium-${record.id}.pem`
  const host: string = record.names[0] ?? 'PROXY_HOST'
  const proxy = `https://USERNAME:PASSWORD@${host.includes(':') ? `[${host}]` : host}:${PORT}`
  const example = record.isSelfSigned
    ? `curl -x ${proxy} --proxy-cacert ${fileName} https://example.com`
    : `curl -x ${proxy} https://example.com`

  const download = () => {
    const url = URL.createObjectURL(
      new Blob([record.certificate], { type: 'application/x-pem-file' }),
    )
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    link.click()
    // Later, not at once: the browser may start reading the file after `click` returns.
    setTimeout(() => URL.revokeObjectURL(url), REVOKE_DELAY_MS)
  }

  return (
    <ShowSection title="Clients">
      <Typography variant="body2">
        Clients connect to any port of the proxy with an <code>https://</code> proxy URL, HTTP and
        SOCKS5 stay available on the same ports.
        {record.isSelfSigned &&
          ' The certificate is self-signed: clients trust it only if given this file, or with the check skipped, e.g. curl’s --proxy-insecure.'}
      </Typography>
      <Box
        component="pre"
        sx={{ m: 0, p: 1.5, bgcolor: 'action.hover', borderRadius: 1, overflowX: 'auto' }}
      >
        {example}
      </Box>
      {record.isSelfSigned && (
        <Box>
          <Button label={`Download ${fileName}`} onClick={download}>
            <DownloadIcon />
          </Button>
        </Box>
      )}
    </ShowSection>
  )
}
