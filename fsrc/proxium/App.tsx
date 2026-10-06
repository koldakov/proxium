import polyglotI18nProvider from 'ra-i18n-polyglot'
import englishMessages from 'ra-language-english'
import type { ReactNode } from 'react'
import { Admin, AppBar, CustomRoutes, Layout, Resource } from 'react-admin'
import { Route } from 'react-router-dom'

import { AppUserMenu } from './components/AppUserMenu'
import { useConfigs } from './components/configs'
import { GroupedMenu } from './components/GroupedMenu'
import { PROFILE_PATH, ProfilePage } from './pages/profile'
import { SettingsPage, settingsLink } from './pages/settings'
import { authProvider, dataProvider, queryClient } from './providers'
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

const AppAppBar = () => <AppBar userMenu={<AppUserMenu profilePath={PROFILE_PATH} />} />

const AppLayout = ({ children }: { children: ReactNode }) => {
  // Loaded once after login, the pages read them from the cache.
  useConfigs()

  return (
    <Layout menu={AppMenu} appBar={AppAppBar}>
      {children}
    </Layout>
  )
}

const App = () => (
  <Admin
    title="Proxium"
    authProvider={authProvider}
    dataProvider={dataProvider}
    queryClient={queryClient}
    i18nProvider={i18nProvider}
    layout={AppLayout}
    requireAuth
  >
    {resources.map((resource) => (
      <Resource key={resource.name} {...resource} />
    ))}
    <CustomRoutes>
      <Route path={settingsLink.to} element={<SettingsPage />} />
      <Route path={PROFILE_PATH} element={<ProfilePage />} />
    </CustomRoutes>
  </Admin>
)

export default App
