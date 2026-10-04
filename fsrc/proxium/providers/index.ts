import { addRefreshAuthToAuthProvider, addRefreshAuthToDataProvider } from 'react-admin'

import { apiUrl } from '../config'
import { createAuthProvider } from './authProvider'
import { createDataProvider } from './dataProvider'
import { refreshTokens } from './tokens'

export type { Me } from './authProvider'
export type {
  OutgoingPoolParams,
  ProxiumDataProvider,
  Settings,
  TrafficTotal,
} from './dataProvider'

export const authProvider = addRefreshAuthToAuthProvider(createAuthProvider(apiUrl), refreshTokens)
export const dataProvider = addRefreshAuthToDataProvider(createDataProvider(apiUrl), refreshTokens)
