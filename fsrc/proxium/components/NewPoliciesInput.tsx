import { AutocompleteArrayInput, ReferenceArrayInput, useCanAccess } from 'react-admin'

// An empty query is refused by the API: no filter lists every policy.
const toQuery = (query: string) => (query ? { query } : {})

/**
 * The policies of a record being created. Global ones apply anyway, so they aren't offered.
 * A saved record assigns them in its Policies section.
 */
export const NewPoliciesInput = () => {
  // Picking means seeing them: without it the record starts with the global policies only.
  const { canAccess: canPick } = useCanAccess({ resource: 'policies', action: 'list' })
  if (!canPick) {
    return null
  }

  return (
    <ReferenceArrayInput source="policyIds" reference="policies" filter={{ isGlobal: false }}>
      <AutocompleteArrayInput
        label="Policies"
        optionText="name"
        filterToQuery={toQuery}
        helperText="Their limits apply on top of the global policies. Empty: global ones only"
      />
    </ReferenceArrayInput>
  )
}
