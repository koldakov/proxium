import { addRefreshAuthToAuthProvider, addRefreshAuthToDataProvider } from 'react-admin'

import { apiUrl } from '../config'
import { createAuthProvider } from './authProvider'
import { createDataProvider } from './dataProvider'
import { queryClient } from './queryClient'
import { refreshTokens } from './tokens'

export type { Me } from './authProvider'
export type {
  OutgoingPoolParams,
  PasswordChange,
  Profile,
  ProfileChanges,
  ProxiumDataProvider,
  Settings,
  TrafficTotal,
} from './dataProvider'

export { queryClient }

export const authProvider = addRefreshAuthToAuthProvider(
  createAuthProvider(apiUrl, { queryClient }),
  refreshTokens,
)
export const dataProvider = addRefreshAuthToDataProvider(createDataProvider(apiUrl), refreshTokens)
