import {
  BooleanField,
  DateField,
  EditButton,
  ReferenceField,
  Show,
  SimpleShowLayout,
  TextField,
  TopToolbar,
} from 'react-admin'

import { UpdateTokenButton } from './UpdateTokenButton'

export const TokenProxyAccountShow = () => (
  <Show
    actions={
      <TopToolbar>
        <UpdateTokenButton />
        <EditButton />
      </TopToolbar>
    }
  >
    <SimpleShowLayout>
      <TextField source="id" />
      <TextField source="name" />
      <TextField source="key" />
      <BooleanField source="isActive" label="Active" />
      <DateField source="expiresAt" label="Expires" showTime emptyText="Never" />
      <ReferenceField source="createdById" label="Created by" reference="users" link="show" />
      <DateField source="createdAt" label="Created" showTime />
      <DateField source="updatedAt" label="Updated" showTime />
    </SimpleShowLayout>
  </Show>
)
