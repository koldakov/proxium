import { Alert, Card, CardContent, Stack, Typography } from '@mui/material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  Form,
  HttpError,
  Loading,
  PasswordInput,
  type RaRecord,
  SaveButton,
  TextInput,
  Title,
  Toolbar,
  minLength,
  required,
  useDataProvider,
  useGetIdentity,
  useNotify,
} from 'react-admin'

import type { PasswordChange, Profile, ProfileChanges, ProxiumDataProvider } from '../../providers'

const QUERY_KEY = ['profile']

// The API's limit too.
const MIN_PASSWORD_LENGTH = 8

const sameAsNew = (value: string, values: Partial<RaRecord>) =>
  value === values.newPassword ? undefined : "Doesn't match the new password"

const ProfileForm = ({ profile }: { profile: Profile }) => {
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const queryClient = useQueryClient()
  const notify = useNotify()
  // The name in the app bar.
  const { refetch: refetchIdentity } = useGetIdentity()

  const save = async (values: Partial<RaRecord>) => {
    const { name, surname } = values as ProfileChanges
    try {
      const saved = await dataProvider.updateProfile({ name, surname })
      queryClient.setQueryData(QUERY_KEY, saved)
      refetchIdentity()
      notify('Saved', { type: 'success' })
    } catch (error) {
      notify((error as Error).message, { type: 'error' })
    }
  }

  return (
    // Remounted on save: the form starts clean from what the API stored.
    <Form key={JSON.stringify(profile)} record={profile} onSubmit={save}>
      <CardContent>
        <Typography variant="h6">Profile</Typography>
        <TextInput
          source="email"
          readOnly
          helperText="Your login, an admin with access to users can change it"
        />
        <TextInput source="name" validate={required()} />
        <TextInput source="surname" validate={required()} />
      </CardContent>
      <Toolbar>
        <SaveButton />
      </Toolbar>
    </Form>
  )
}

const PasswordForm = () => {
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const notify = useNotify()
  // Bumped on success: an empty form again.
  const [generation, setGeneration] = useState(0)

  const save = async (values: Partial<RaRecord>) => {
    const { oldPassword, newPassword } = values as PasswordChange
    try {
      await dataProvider.updatePassword({ oldPassword, newPassword })
    } catch (error) {
      // A wrong old password goes next to its input.
      if (error instanceof HttpError && error.status === 400) {
        return { oldPassword: error.message }
      }
      notify((error as Error).message, { type: 'error' })
      return undefined
    }
    setGeneration(generation + 1)
    notify('Password changed', { type: 'success' })
    return undefined
  }

  return (
    <Form key={generation} onSubmit={save}>
      <CardContent>
        <Typography variant="h6">Password</Typography>
        <PasswordInput source="oldPassword" label="Current password" validate={required()} />
        <PasswordInput
          source="newPassword"
          label="New password"
          validate={[required(), minLength(MIN_PASSWORD_LENGTH)]}
          helperText={`At least ${MIN_PASSWORD_LENGTH} characters`}
        />
        <PasswordInput
          source="confirmPassword"
          label="New password again"
          validate={[required(), sameAsNew]}
        />
      </CardContent>
      <Toolbar>
        <SaveButton label="Change password" />
      </Toolbar>
    </Form>
  )
}

/** The logged-in user's own name and password: no permission needed, unlike the users section. */
export const ProfilePage = () => {
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const { data, error } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => dataProvider.getProfile(),
  })

  if (error) {
    return <Alert severity="error">{error.message}</Alert>
  }
  if (data === undefined) {
    return <Loading />
  }

  return (
    <>
      <Title title="Profile" />
      <Stack spacing={2} sx={{ mt: 2 }}>
        <Card>
          <ProfileForm profile={data} />
        </Card>
        <Card>
          <PasswordForm />
        </Card>
      </Stack>
    </>
  )
}
