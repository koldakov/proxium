import { Grid, Stack, Typography } from '@mui/material'
import {
  DateField,
  DeleteButton,
  FunctionField,
  Labeled,
  Show,
  TopToolbar,
  WithRecord,
  useRecordContext,
} from 'react-admin'

import { CopyableField } from '../../components/CopyableField'
import { ExpiresField } from '../../components/ExpiresField'
import { ShowSection } from '../../components/ShowSection'
import { ActivationButton } from './ActivationButton'
import { CertificateStatusChip } from './CertificateStatusChip'
import { ClientSetupSection } from './ClientSetupSection'
import { describeCertificate } from './expiry'

const CertificateHeader = () => {
  const record = useRecordContext()
  if (record === undefined) {
    return null
  }

  return (
    <Stack spacing={0.5}>
      <Stack direction="row" alignItems="center" spacing={1.5}>
        <Typography variant="h5">{describeCertificate(record)}</Typography>
        <CertificateStatusChip />
      </Stack>
      <Typography variant="body2" color="text.secondary">
        #{record.id}
      </Typography>
    </Stack>
  )
}

const Actions = () => (
  <TopToolbar>
    <ActivationButton />
    <WithRecord
      render={(record) =>
        // The API keeps the active one: turning TLS off is a step of its own.
        !record.isActive && (
          <DeleteButton
            mutationMode="pessimistic"
            confirmTitle="Delete certificate"
            confirmContent="The certificate and its private key are deleted for good."
          />
        )
      }
    />
  </TopToolbar>
)

export const CertificateShow = () => (
  <Show component="div" actions={<Actions />}>
    <Stack spacing={2}>
      <CertificateHeader />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <ShowSection title="Certificate">
            <Labeled label="Names clients check">
              <FunctionField
                render={(record) => (record.names.length > 0 ? record.names.join(', ') : 'None')}
              />
            </Labeled>
            <Labeled label="SHA-256 fingerprint">
              <CopyableField source="fingerprint" />
            </Labeled>
            <Labeled label="Issued by">
              <FunctionField
                render={(record) => (record.isSelfSigned ? 'Itself (self-signed)' : 'A CA')}
              />
            </Labeled>
          </ShowSection>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <ShowSection title="Validity">
            <Labeled label="Valid from">
              <DateField source="notValidBefore" showTime />
            </Labeled>
            <Labeled label="Valid until">
              <ExpiresField source="notValidAfter" />
            </Labeled>
          </ShowSection>
        </Grid>
        <Grid size={12}>
          <ClientSetupSection />
        </Grid>
        <Grid size={12}>
          <ShowSection title="History">
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 2, sm: 6 }}>
              <Labeled label="Added">
                <DateField source="createdAt" showTime />
              </Labeled>
              <Labeled label="Updated">
                <DateField source="updatedAt" showTime />
              </Labeled>
            </Stack>
          </ShowSection>
        </Grid>
      </Grid>
    </Stack>
  </Show>
)
