import { BooleanField, DateField, EmailField, Show, SimpleShowLayout, TextField } from 'react-admin'

export const UserShow = () => (
  <Show>
    <SimpleShowLayout>
      <TextField source="id" />
      <EmailField source="email" />
      <TextField source="name" />
      <TextField source="surname" />
      <BooleanField source="isActive" label="Active" />
      <BooleanField source="isSuperuser" label="Superuser" />
      <DateField source="createdAt" label="Created" showTime />
      <DateField source="updatedAt" label="Updated" showTime />
    </SimpleShowLayout>
  </Show>
)
