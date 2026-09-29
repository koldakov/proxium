import { Grid, Stack } from '@mui/material'
import { BooleanField, DateField, Labeled, Show, TextField } from 'react-admin'

import { CopyableField } from '../../components/CopyableField'
import { ShowSection } from '../../components/ShowSection'
import { UserHeader } from './UserHeader'

export const UserShow = () => (
  <Show component="div">
    <Stack spacing={2}>
      <UserHeader />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <ShowSection title="Profile">
            <Labeled label="Email">
              <CopyableField source="email" />
            </Labeled>
            <Labeled>
              <TextField source="name" />
            </Labeled>
            <Labeled>
              <TextField source="surname" />
            </Labeled>
          </ShowSection>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <ShowSection title="Access">
            <Labeled label="Active">
              <BooleanField source="isActive" />
            </Labeled>
            <Labeled label="Superuser">
              <BooleanField source="isSuperuser" />
            </Labeled>
          </ShowSection>
        </Grid>
        <Grid size={12}>
          <ShowSection title="History">
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 2, sm: 6 }}>
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
