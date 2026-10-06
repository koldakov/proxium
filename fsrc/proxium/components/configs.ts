import { useQuery } from '@tanstack/react-query'
import { useDataProvider } from 'react-admin'

import type { ProxiumDataProvider } from '../providers'

/** The API's configs, e.g. its caps. Undefined while loading. */
export const useConfigs = () => {
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  return useQuery({
    queryKey: ['configs'],
    queryFn: () => dataProvider.getConfigs(),
    // From the environment: they change only with a restart of the API.
    staleTime: Infinity,
  }).data
}
