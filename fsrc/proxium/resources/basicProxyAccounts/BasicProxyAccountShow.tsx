import { Grid, Stack, Typography } from '@mui/material'
import { DateField, EditButton, Labeled, ReferenceField, Show, TopToolbar } from 'react-admin'

import { CopyableField } from '../../components/CopyableField'
import { ExpiresField } from '../../components/ExpiresField'
import { ProxyAccountHeader } from '../../components/ProxyAccountHeader'
import { RevokeButton } from '../../components/RevokeButton'
import { ShowSection } from '../../components/ShowSection'

export const BasicProxyAccountShow = () => (
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
            <Labeled label="Username">
              <CopyableField source="username" />
            </Labeled>
            <Labeled label="Password">
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
        <Grid size={12}>
          <ShowSection title="History">
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 2, sm: 6 }}>
              <Labeled label="Created by">
                <ReferenceField source="createdById" reference="users" link="show" />
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
