import polyglotI18nProvider from 'ra-i18n-polyglot'
import englishMessages from 'ra-language-english'
import type { ReactNode } from 'react'
import { Admin, CustomRoutes, Layout, Resource } from 'react-admin'
import { Route } from 'react-router-dom'

import { GroupedMenu } from './components/GroupedMenu'
import { SettingsPage, settingsLink } from './pages/settings'
import { authProvider, dataProvider } from './providers'
import { menu, resources } from './resources'

// The API logs in by email: relabel the stock login form.
const i18nProvider = polyglotI18nProvider(
  () => ({
    ...englishMessages,
    ra: { ...englishMessages.ra, auth: { ...englishMessages.ra.auth, username: 'Email' } },
  }),
  'en',
)

const AppMenu = () => <GroupedMenu nodes={menu} />

const AppLayout = ({ children }: { children: ReactNode }) => (
  <Layout menu={AppMenu}>{children}</Layout>
)

const App = () => (
  <Admin
    title="Proxium"
    authProvider={authProvider}
    dataProvider={dataProvider}
    i18nProvider={i18nProvider}
    layout={AppLayout}
    requireAuth
  >
    {resources.map((resource) => (
      <Resource key={resource.name} {...resource} />
    ))}
    <CustomRoutes>
      <Route path={settingsLink.to} element={<SettingsPage />} />
    </CustomRoutes>
  </Admin>
)

export default App
