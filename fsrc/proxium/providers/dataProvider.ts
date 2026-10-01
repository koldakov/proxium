import type { DataProvider, DeleteParams, Identifier, RaRecord } from 'react-admin'

import { httpClient as defaultHttpClient, type HttpClient } from './httpClient'

export interface RevokeParams {
  id: Identifier
}

// UTC days as `YYYY-MM-DD`, both inclusive. All time without them.
export interface TrafficTotalParams {
  id: Identifier
  since?: string
  until?: string
}

// An IP in the outgoing IP pool of the record `id`.
export interface OutgoingPoolParams {
  id: Identifier
  outgoingIpId: Identifier
}

export interface TrafficTotal {
  bytesSent: number
  bytesReceived: number
}

/** CRUD plus the actions some resources have on top of it. */
export interface ProxiumDataProvider extends DataProvider {
  revoke: (resource: string, params: RevokeParams) => Promise<void>
  getTrafficTotal: (resource: string, params: TrafficTotalParams) => Promise<TrafficTotal>
  addToOutgoingPool: (resource: string, params: OutgoingPoolParams) => Promise<void>
  removeFromOutgoingPool: (resource: string, params: OutgoingPoolParams) => Promise<void>
}

const unsupported = (method: string) => (): never => {
  throw new Error(`The API doesn't support ${method}.`)
}

// Only what the user changed: PATCH leaves missing fields as they are.
const changedFields = (data: Partial<RaRecord>, previousData: Partial<RaRecord>) =>
  Object.fromEntries(Object.entries(data).filter(([key, value]) => value !== previousData[key]))

/**
 * Maps a react-admin resource to `/api/<resource>`: pages of `{ items, total }`, filters as query params.
 */
export const createDataProvider = (
  apiUrl: string,
  httpClient: HttpClient = defaultHttpClient,
): ProxiumDataProvider => {
  const resourceUrl = (resource: string, ...path: Identifier[]) =>
    [`${apiUrl}/api/${resource}`, ...path.map((part) => encodeURIComponent(part))].join('/')

  const getOne = async (resource: string, id: Identifier) => {
    const { json } = await httpClient(resourceUrl(resource, id))
    return json
  }

  return {
    getList: async (resource, { pagination, filter }) => {
      const query = new URLSearchParams(filter)
      if (pagination !== undefined) {
        query.set('page', String(pagination.page))
        query.set('size', String(pagination.perPage))
      }
      const { json } = await httpClient(`${resourceUrl(resource)}?${query}`)
      return { data: json.items, total: json.total }
    },

    getOne: async (resource, { id }) => ({ data: await getOne(resource, id) }),

    // No batch endpoint: one request per record.
    getMany: async (resource, { ids }) => ({
      data: await Promise.all(ids.map((id) => getOne(resource, id))),
    }),

    create: async (resource, { data }) => {
      const { json } = await httpClient(resourceUrl(resource), {
        method: 'POST',
        body: JSON.stringify(data),
      })
      return { data: json }
    },

    update: async (resource, { id, data, previousData }) => {
      const { json } = await httpClient(resourceUrl(resource, id), {
        method: 'PATCH',
        body: JSON.stringify(changedFields(data, previousData)),
      })
      return { data: json }
    },

    revoke: async (resource, { id }) => {
      await httpClient(resourceUrl(resource, id, 'revoke'), { method: 'POST' })
    },

    getTrafficTotal: async (resource, { id, ...range }) => {
      const query = new URLSearchParams(
        Object.entries(range).filter((entry): entry is [string, string] => entry[1] !== undefined),
      )
      const { json } = await httpClient(`${resourceUrl(resource, id, 'traffic', 'total')}?${query}`)
      return json
    },

    addToOutgoingPool: async (resource, { id, outgoingIpId }) => {
      await httpClient(resourceUrl(resource, id, 'outgoing-ips', outgoingIpId), { method: 'PUT' })
    },

    removeFromOutgoingPool: async (resource, { id, outgoingIpId }) => {
      await httpClient(resourceUrl(resource, id, 'outgoing-ips', outgoingIpId), {
        method: 'DELETE',
      })
    },

    // No content in the response: react-admin gets the record it already had.
    delete: async <RecordType extends RaRecord>(
      resource: string,
      { id, previousData }: DeleteParams<RecordType>,
    ) => {
      await httpClient(resourceUrl(resource, id), { method: 'DELETE' })
      return { data: previousData as RecordType }
    },

    getManyReference: unsupported('getManyReference'),
    updateMany: unsupported('updateMany'),
    deleteMany: unsupported('deleteMany'),
  }
}
