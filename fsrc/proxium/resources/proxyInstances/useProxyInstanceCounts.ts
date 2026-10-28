import { useQuery } from '@tanstack/react-query'
import { useDataProvider } from 'react-admin'

import type { ProxiumDataProvider, ProxyInstanceCounts } from '../../providers'
import { REFRESH_MS } from './statuses'

/** The number of instances in each status, refreshed on its own. One request for every caller on the page. */
export const useProxyInstanceCounts = (): ProxyInstanceCounts | undefined => {
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const { data } = useQuery({
    queryKey: ['proxy-instances', 'getProxyInstanceCounts'],
    queryFn: () => dataProvider.getProxyInstanceCounts(),
    refetchInterval: REFRESH_MS,
  })
  return data
}
