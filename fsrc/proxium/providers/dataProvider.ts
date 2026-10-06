import type { DataProvider, DeleteParams, Identifier, RaRecord } from 'react-admin'

import { httpClient as defaultHttpClient, type HttpClient } from './httpClient'
import { saveTokens } from './tokens'

export interface RevokeParams {
  id: Identifier
}

export interface ActivateParams {
  id: Identifier
  // The active record the user saw, null if none: the API refuses if it has changed since.
  replaces: Identifier | null
}

export interface DeactivateParams {
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

// A policy assigned to the record `id`.
export interface PolicyAssignmentParams {
  id: Identifier
  policyId: Identifier
}

// The UTC day as `YYYY-MM-DD` quota periods of an assigned policy count from for the record.
export interface PolicyStartParams extends PolicyAssignmentParams {
  startsOn: string
}

export interface TrafficTotal {
  bytesSent: number
  bytesReceived: number
}

// The logged-in user. The email is the login, only an admin changes it.
export interface Profile {
  id: number
  email: string
  name: string
  surname: string
}

export interface ProfileChanges {
  name: string
  surname: string
}

export interface PasswordChange {
  oldPassword: string
  newPassword: string
}

// Another user's password, the old one isn't needed.
export interface UserPasswordParams {
  id: Identifier
  password: string
}

// Timeouts and the cache TTL in seconds. Networks in CIDR notation, a bare address is taken as /32 or /128.
export interface Settings {
  guardAllow: string[]
  handshakeTimeout: number
  idleTimeout: number
  connectTimeout: number
  cacheTtl: number
}

// Read-only, from the API's environment.
export interface Configs {
  policiesMaxPerOwner: number
}

/** CRUD plus the actions some resources have on top of it. */
export interface ProxiumDataProvider extends DataProvider {
  revoke: (resource: string, params: RevokeParams) => Promise<void>
  activate: (resource: string, params: ActivateParams) => Promise<void>
  deactivate: (resource: string, params: DeactivateParams) => Promise<void>
  getTrafficTotal: (resource: string, params: TrafficTotalParams) => Promise<TrafficTotal>
  addToOutgoingPool: (resource: string, params: OutgoingPoolParams) => Promise<void>
  removeFromOutgoingPool: (resource: string, params: OutgoingPoolParams) => Promise<void>
  assignPolicy: (resource: string, params: PolicyAssignmentParams) => Promise<void>
  unassignPolicy: (resource: string, params: PolicyAssignmentParams) => Promise<void>
  setPolicyStart: (resource: string, params: PolicyStartParams) => Promise<void>
  // The logged-in user's own record, no permission needed.
  getProfile: () => Promise<Profile>
  updateProfile: (data: ProfileChanges) => Promise<Profile>
  updatePassword: (data: PasswordChange) => Promise<void>
  setUserPassword: (params: UserPasswordParams) => Promise<void>
  // Every permission code, e.g. `trusted_networks.view`. Not paged.
  listPermissions: () => Promise<string[]>
  // One record, not a resource: no id, no list.
  getSettings: () => Promise<Settings>
  updateSettings: (data: Settings) => Promise<Settings>
  // Any active user, no permission needed.
  getConfigs: () => Promise<Configs>
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

    activate: async (resource, { id, replaces }) => {
      await httpClient(resourceUrl(resource, id, 'activate'), {
        method: 'POST',
        body: JSON.stringify({ replaces }),
      })
    },

    deactivate: async (resource, { id }) => {
      await httpClient(resourceUrl(resource, id, 'deactivate'), { method: 'POST' })
    },

    getTrafficTotal: async (resource, { id, ...range }) => {
      const query = new URLSearchParams(
        Object.entries(range).filter((entry): entry is [string, string] => entry[1] !== undefined),
      )
      // Traffic is its own resource: `/traffic/<resource>/<id>`.
      const { json } = await httpClient(`${resourceUrl('traffic', resource, id, 'total')}?${query}`)
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

    assignPolicy: async (resource, { id, policyId }) => {
      await httpClient(resourceUrl(resource, id, 'policies', policyId), { method: 'PUT' })
    },

    unassignPolicy: async (resource, { id, policyId }) => {
      await httpClient(resourceUrl(resource, id, 'policies', policyId), { method: 'DELETE' })
    },

    setPolicyStart: async (resource, { id, policyId, startsOn }) => {
      await httpClient(resourceUrl(resource, id, 'policies', policyId), {
        method: 'PATCH',
        body: JSON.stringify({ startsOn }),
      })
    },

    getProfile: async () => {
      const { json } = await httpClient(resourceUrl('users', 'me'))
      return json
    },

    updateProfile: async (data) => {
      const { json } = await httpClient(resourceUrl('users', 'me'), {
        method: 'PATCH',
        body: JSON.stringify(data),
      })
      return json
    },

    // The new password revokes every token issued before: the session goes on with the returned pair.
    updatePassword: async (data) => {
      const { json } = await httpClient(resourceUrl('users', 'me', 'password'), {
        method: 'PUT',
        body: JSON.stringify(data),
      })
      saveTokens(json)
    },

    setUserPassword: async ({ id, password }) => {
      await httpClient(resourceUrl('users', id, 'password'), {
        method: 'PUT',
        body: JSON.stringify({ password }),
      })
    },

    listPermissions: async () => {
      const { json } = await httpClient(resourceUrl('permissions'))
      return json.map(({ id }: { id: string }) => id)
    },

    getSettings: async () => {
      const { json } = await httpClient(resourceUrl('settings'))
      return json
    },

    // All settings at once: PUT replaces them.
    updateSettings: async (data) => {
      const { json } = await httpClient(resourceUrl('settings'), {
        method: 'PUT',
        body: JSON.stringify(data),
      })
      return json
    },

    getConfigs: async () => {
      const { json } = await httpClient(resourceUrl('configs'))
      return json
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
