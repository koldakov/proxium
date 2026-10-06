import {
  AutocompleteArrayInput,
  FormDataConsumer,
  type Identifier,
  type RaRecord,
  ReferenceArrayInput,
  useCanAccess,
} from 'react-admin'

import { useConfigs } from './configs'

// Options offered at once: the search finds the rest, they stay out of the request.
const OPTIONS_LIMIT = 5

// An empty query is refused by the API: no filter lists every policy.
const toQuery = (query: string) => (query ? { query } : {})

/**
 * The policies of a record being created. Global ones apply anyway, so they aren't offered.
 * A saved record assigns them in its Policies section.
 */
export const NewPoliciesInput = () => {
  // Picking means seeing them: without it the record starts with the global policies only.
  const { canAccess: canPick } = useCanAccess({ resource: 'policies', action: 'list' })
  const max = useConfigs()?.policiesMaxPerOwner
  if (!canPick) {
    return null
  }

  return (
    <FormDataConsumer>
      {({ formData }) => {
        const ids: Identifier[] = formData.policyIds ?? []
        // One more would be refused: the rest of the options turn off, picked ones can still go.
        const isFull = max !== undefined && ids.length >= max

        return (
          <ReferenceArrayInput
            source="policyIds"
            reference="policies"
            filter={{ isGlobal: false }}
            perPage={OPTIONS_LIMIT}
          >
            <AutocompleteArrayInput
              label="Policies"
              optionText="name"
              filterToQuery={toQuery}
              getOptionDisabled={(policy: RaRecord) => isFull && !ids.includes(policy.id)}
              helperText={
                isFull
                  ? `The limit of ${max} policies is reached: remove one to pick another`
                  : 'Type to find a policy. Their limits apply on top of the global policies. ' +
                    'Empty: global ones only'
              }
            />
          </ReferenceArrayInput>
        )
      }}
    </FormDataConsumer>
  )
}
