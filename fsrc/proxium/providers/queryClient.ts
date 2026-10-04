import { QueryClient } from '@tanstack/react-query'

// Shared by react-admin and the auth provider: a refused request makes the UI check permissions again.
export const queryClient = new QueryClient()
