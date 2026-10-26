import { Alert, Box, Button, Card, Stack, Typography } from '@mui/material'
import { useState } from 'react'
import {
  Form,
  PasswordInput,
  TextInput,
  email,
  required,
  useAuthProvider,
  useLogin,
} from 'react-admin'

import type { ProxiumAuthProvider } from '../../providers'

interface Credentials {
  email: string
  password: string
}

/**
 * Sign-in in the admin's own style. A refused login is said under the password, not in a toast that goes away:
 * the line under an input is always there, so nothing moves.
 */
export const LoginPage = () => {
  const login = useLogin()
  const authProvider = useAuthProvider<ProxiumAuthProvider>()
  // There from the first render: shown in the card, nothing moves.
  const logoutReason = authProvider?.getLogoutReason() ?? null
  const [isPending, setIsPending] = useState(false)

  const submit = async (values: Partial<Credentials>) => {
    setIsPending(true)
    try {
      await login({ username: values.email, password: values.password })
    } catch (error) {
      setIsPending(false)
      // Either may be wrong: both outlined, the reason said once. A space keeps the email's line empty.
      return { email: ' ', password: (error as Error).message || 'Could not sign in' }
    }
    return undefined
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'background.default',
        px: 2,
      }}
    >
      <Card sx={{ width: '100%', maxWidth: 380, p: 4 }}>
        <Stack spacing={1} alignItems="center" sx={{ mb: 3 }}>
          <Box component="img" src="/favicon.svg" alt="" sx={{ width: 40, height: 40 }} />
          <Typography variant="h5">Proxium</Typography>
          <Typography variant="body2" color="text.secondary">
            Sign in to the admin
          </Typography>
        </Stack>
        {logoutReason !== null && (
          <Alert severity="info" sx={{ mb: 2 }}>
            {logoutReason}
          </Alert>
        )}
        {/* The errors are under the inputs, no toast to point at them. */}
        <Form onSubmit={submit} disableInvalidFormNotification>
          <Stack>
            <TextInput
              source="email"
              type="email"
              autoComplete="username"
              autoFocus
              validate={[required(), email()]}
            />
            <PasswordInput
              source="password"
              autoComplete="current-password"
              validate={required()}
            />
            <Button type="submit" variant="contained" loading={isPending} sx={{ mt: 2 }}>
              Sign in
            </Button>
          </Stack>
        </Form>
      </Card>
    </Box>
  )
}
