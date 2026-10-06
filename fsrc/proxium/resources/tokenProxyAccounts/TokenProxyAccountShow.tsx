import { Grid, Stack, Typography } from '@mui/material'
import {
  DateField,
  EditButton,
  Labeled,
  SelectField,
  Show,
  TopToolbar,
  WithRecord,
} from 'react-admin'

import { CopyableField } from '../../components/CopyableField'
import { CreatedByField } from '../../components/CreatedByField'
import { ExpiresField } from '../../components/ExpiresField'
import { OUTGOING_MODES } from '../../components/outgoing'
import { OutgoingPoolSection } from '../../components/OutgoingPoolSection'
import { PoliciesSection } from '../../components/PoliciesSection'
import { ProxyAccountHeader } from '../../components/ProxyAccountHeader'
import { RevokeButton } from '../../components/RevokeButton'
import { ShowSection } from '../../components/ShowSection'
import { TrafficSection } from '../../components/TrafficSection'

export const TokenProxyAccountShow = () => (
  <Show
    component="div"
    actions={
      <TopToolbar>
        <RevokeButton />
        <EditButton />
      </TopToolbar>
    }
  >
    <Stack spacing={2}>
      <ProxyAccountHeader />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <ShowSection title="Credentials">
            <Labeled label="Key">
              <CopyableField source="key" />
            </Labeled>
            <Labeled label="Token">
              <Typography variant="body2" color="text.secondary">
                Shown only once, on creation
              </Typography>
            </Labeled>
          </ShowSection>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <ShowSection title="Validity">
            <Labeled label="Expires">
              <ExpiresField source="expiresAt" />
            </Labeled>
          </ShowSection>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <ShowSection title="Outgoing">
            <Labeled label="Outgoing IP">
              <SelectField source="outgoingMode" choices={OUTGOING_MODES} />
            </Labeled>
          </ShowSection>
        </Grid>
        <WithRecord
          render={(record) =>
            // Only while the account goes out through it: otherwise the pool is unused.
            record.outgoingMode === 'pool' && (
              <Grid size={12}>
                <OutgoingPoolSection />
              </Grid>
            )
          }
        />
        <Grid size={12}>
          <PoliciesSection />
        </Grid>
        <Grid size={12}>
          <TrafficSection />
        </Grid>
        <Grid size={12}>
          <ShowSection title="History">
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 2, sm: 6 }}>
              <Labeled label="Created by">
                <CreatedByField />
              </Labeled>
              <Labeled label="Created">
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
