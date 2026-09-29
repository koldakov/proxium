import { Create, email, PasswordInput, SimpleForm, TextInput, required } from 'react-admin'

export const UserCreate = () => (
  <Create redirect="show">
    <SimpleForm>
      <TextInput source="email" validate={[required(), email()]} />
      <TextInput source="name" validate={required()} />
      <TextInput source="surname" validate={required()} />
      <PasswordInput source="password" validate={required()} />
    </SimpleForm>
  </Create>
)
