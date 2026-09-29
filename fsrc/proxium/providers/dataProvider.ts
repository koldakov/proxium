import type { DataProvider, Identifier, RaRecord } from 'react-admin'

import { httpClient as defaultHttpClient, type HttpClient } from './httpClient'

export interface UpdatePasswordParams {
  id: Identifier
  password: string
}

export interface UpdateTokenParams {
  id: Identifier
}

export interface UpdateTokenResult {
  key: string
  token: string
}

/** CRUD plus the actions some resources have on top of it. */
export interface ProxiumDataProvider extends DataProvider {
  updatePassword: (resource: string, params: UpdatePasswordParams) => Promise<void>
  updateToken: (resource: string, params: UpdateTokenParams) => Promise<UpdateTokenResult>
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

    updatePassword: async (resource, { id, password }) => {
      await httpClient(resourceUrl(resource, id, 'password'), {
        method: 'PUT',
        body: JSON.stringify({ password }),
      })
    },

    updateToken: async (resource, { id }) => {
      const { json } = await httpClient(resourceUrl(resource, id, 'token'), { method: 'POST' })
      return json
    },

    getManyReference: unsupported('getManyReference'),
    updateMany: unsupported('updateMany'),
    delete: unsupported('delete'),
    deleteMany: unsupported('deleteMany'),
  }
}
