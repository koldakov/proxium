import { Grid, Stack, Typography } from '@mui/material'
import {
  BooleanField,
  ChipField,
  DateField,
  EditButton,
  Labeled,
  ReferenceArrayField,
  Show,
  SingleFieldList,
  TextField,
  TopToolbar,
  useCanAccess,
  useRecordContext,
} from 'react-admin'

import { CopyableField } from '../../components/CopyableField'
import { useMyPermissions } from '../../components/permissions'
import { PermissionsField } from '../../components/PermissionsField'
import { ShowSection } from '../../components/ShowSection'
import { UserHeader } from './UserHeader'

// Only superusers change superusers: the API refuses the rest.
const UserEditButton = () => {
  const record = useRecordContext()
  const me = useMyPermissions()
  if (record === undefined || me === undefined || (record.isSuperuser && !me.isSuperuser)) {
    return null
  }

  return <EditButton />
}

const GroupsField = () => {
  const record = useRecordContext()
  const { canAccess } = useCanAccess({ resource: 'groups', action: 'list' })
  // Missing in the list's record, which react-admin shows until the user itself loads.
  if (record?.groupIds === undefined) {
    return null
  }
  if (record.groupIds.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        None
      </Typography>
    )
  }
  // Without `groups.view` the names can't be loaded.
  if (!canAccess) {
    return (
      <Typography variant="body2">
        {record.groupIds.map((id: number) => `#${id}`).join(', ')}
      </Typography>
    )
  }

  return (
    <ReferenceArrayField source="groupIds" reference="groups">
      <SingleFieldList linkType={false}>
        <ChipField source="name" size="small" />
      </SingleFieldList>
    </ReferenceArrayField>
  )
}

export const UserShow = () => (
  <Show
    component="div"
    actions={
      <TopToolbar>
        <UserEditButton />
      </TopToolbar>
    }
  >
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
            <Labeled label="Groups">
              <GroupsField />
            </Labeled>
            <Labeled label="Own permissions, besides the groups'">
              <PermissionsField />
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
