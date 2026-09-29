import polyglotI18nProvider from 'ra-i18n-polyglot'
import englishMessages from 'ra-language-english'
import { Admin, Resource } from 'react-admin'

import { authProvider, dataProvider } from './providers'
import { resources } from './resources'

// The API logs in by email: relabel the stock login form.
const i18nProvider = polyglotI18nProvider(
  () => ({
    ...englishMessages,
    ra: { ...englishMessages.ra, auth: { ...englishMessages.ra.auth, username: 'Email' } },
  }),
  'en',
)

const App = () => (
  <Admin
    title="Proxium"
    authProvider={authProvider}
    dataProvider={dataProvider}
    i18nProvider={i18nProvider}
    requireAuth
  >
    {resources.map((resource) => (
      <Resource key={resource.name} {...resource} />
    ))}
  </Admin>
)

export default App
