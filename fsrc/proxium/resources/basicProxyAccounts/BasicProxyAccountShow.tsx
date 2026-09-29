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

import { RevokeButton } from '../../components/RevokeButton'

export const BasicProxyAccountShow = () => (
  <Show
    actions={
      <TopToolbar>
        <RevokeButton />
        <EditButton />
      </TopToolbar>
    }
  >
    <SimpleShowLayout>
      <TextField source="id" />
      <TextField source="name" />
      <TextField source="username" />
      <BooleanField source="isActive" label="Active" />
      <DateField source="expiresAt" label="Expires" showTime emptyText="Never" />
      <ReferenceField source="createdById" label="Created by" reference="users" link="show" />
      <DateField source="createdAt" label="Created" showTime />
      <DateField source="updatedAt" label="Updated" showTime />
    </SimpleShowLayout>
  </Show>
)
