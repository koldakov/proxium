import { Alert, Typography } from '@mui/material'
import {
  AddItemButton,
  ArrayInput,
  BooleanInput,
  DateInput,
  FormDataConsumer,
  NumberInput,
  SelectInput,
  SimpleFormIterator,
  TextInput,
  maxValue,
  minValue,
  required,
  useSimpleFormIteratorItem,
} from 'react-admin'
import type { RaRecord } from 'react-admin'

import { ConditionInputs } from './ConditionInputs'
import {
  DIRECTIONS,
  LIMIT_SCOPES,
  QUOTA_DIRECTIONS,
  QUOTA_PERIODS,
  formatGigabytes,
  formatMbits,
  formatMegabytes,
  parseGigabytes,
  parseMbits,
  parseMegabytes,
} from './limits'

/** Read-only, an empty list of limits says so instead of showing nothing under its heading. Inside a rule. */
const NoLimits = ({ field }: { field: 'connectionLimits' | 'speedLimits' | 'trafficQuotas' }) => (
  <FormDataConsumer>
    {({ scopedFormData }) =>
      scopedFormData?.[field]?.length ? null : (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          No limits
        </Typography>
      )
    }
  </FormDataConsumer>
)

const appliesAlways = (rule: RaRecord | undefined) =>
  !rule?.complexCondition && !(rule?.blocks?.length > 0)

/** A rule after one without conditions never applies: the first match wins. */
const UnreachableRuleWarning = () => {
  const { index } = useSimpleFormIteratorItem()
  return (
    <FormDataConsumer>
      {({ formData }) =>
        (formData.rules ?? []).slice(0, index).some(appliesAlways) && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Never applies: a rule above has no conditions and always applies first. Move this one up
            or add conditions to that one
          </Alert>
        )
      }
    </FormDataConsumer>
  )
}

/** The limits of one rule. */
const RuleLimits = ({ readOnly }: { readOnly: boolean }) => (
  <>
    <Typography variant="subtitle2" sx={{ mt: 2 }}>
      Connections
    </Typography>
    {readOnly && <NoLimits field="connectionLimits" />}
    <ArrayInput source="connectionLimits" label={false}>
      {/* The iterator holds the add and remove buttons. */}
      <SimpleFormIterator inline disableReordering disableClear disabled={readOnly}>
        <SelectInput
          source="scope"
          choices={LIMIT_SCOPES}
          readOnly={readOnly}
          validate={required()}
        />
        <NumberInput
          source="maxConnections"
          label="At most"
          readOnly={readOnly}
          validate={[required(), minValue(1)]}
          helperText="Open at once, more are refused"
        />
      </SimpleFormIterator>
    </ArrayInput>

    <Typography variant="subtitle2" sx={{ mt: 2 }}>
      Speed
    </Typography>
    {readOnly && <NoLimits field="speedLimits" />}
    <ArrayInput source="speedLimits" label={false}>
      <SimpleFormIterator inline disableReordering disableClear disabled={readOnly}>
        <SelectInput
          source="scope"
          choices={LIMIT_SCOPES}
          readOnly={readOnly}
          validate={required()}
        />
        <SelectInput
          source="direction"
          choices={DIRECTIONS}
          defaultValue="both"
          readOnly={readOnly}
          validate={required()}
        />
        <NumberInput
          source="rate"
          label="Mbit/s"
          format={formatMbits}
          parse={parseMbits}
          readOnly={readOnly}
          validate={[required(), minValue(1)]}
          helperText="Shared by the connections in scope"
        />
        <NumberInput
          source="burst"
          label="Burst, MB"
          format={formatMegabytes}
          parse={parseMegabytes}
          readOnly={readOnly}
          validate={minValue(1)}
          helperText="At once after a pause. Empty: one second of the rate"
        />
      </SimpleFormIterator>
    </ArrayInput>

    <Typography variant="subtitle2" sx={{ mt: 2 }}>
      Traffic
    </Typography>
    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
      Per account or network. Past a quota new connections are refused and open ones are cut
    </Typography>
    {readOnly && <NoLimits field="trafficQuotas" />}
    <ArrayInput source="trafficQuotas" label={false}>
      <SimpleFormIterator inline disableReordering disableClear disabled={readOnly}>
        <SelectInput
          source="direction"
          choices={QUOTA_DIRECTIONS}
          defaultValue="both"
          readOnly={readOnly}
          validate={required()}
          helperText="Both ways: counted together"
        />
        <NumberInput
          source="maxBytes"
          label="GB"
          format={formatGigabytes}
          parse={parseGigabytes}
          readOnly={readOnly}
          validate={[required(), minValue(1)]}
          helperText="Per period"
        />
        <SelectInput
          source="period"
          label="Resets"
          choices={QUOTA_PERIODS}
          defaultValue="month"
          readOnly={readOnly}
          validate={required()}
        />
        {/* A quota that never resets has no period length. */}
        <FormDataConsumer>
          {({ scopedFormData }) =>
            scopedFormData?.period !== 'total' && (
              <NumberInput
                source="periodLength"
                label={scopedFormData?.period === 'day' ? 'Every N days' : 'Every N months'}
                defaultValue={1}
                readOnly={readOnly}
                validate={[required(), minValue(1), maxValue(3650)]}
              />
            )
          }
        </FormDataConsumer>
      </SimpleFormIterator>
    </ArrayInput>
  </>
)

const hasQuotas = (rules: RaRecord[] | undefined) =>
  (rules ?? []).some((rule) => rule?.trafficQuotas?.length > 0)

/**
 * The fields of a policy, shared by create and edit, read-only on the show page. Edits the policy as
 * `toFormPolicy` gives it: each rule's condition split into form fields.
 */
export const PolicyInputs = ({ readOnly = false }: { readOnly?: boolean }) => (
  <>
    <TextInput
      source="name"
      readOnly={readOnly}
      validate={required()}
      helperText="E.g. Basic 50 Mbit/s"
    />
    <BooleanInput
      source="isActive"
      label="Active"
      readOnly={readOnly}
      helperText="Off: the policy applies to no one"
    />
    <BooleanInput
      source="isGlobal"
      label="Global"
      readOnly={readOnly}
      helperText="Applies to every client. Otherwise assign it on the page of an account or network"
    />

    <Typography variant="subtitle1" sx={{ mt: 2 }}>
      Rules
    </Typography>
    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
      The first rule whose conditions match applies its limits, the rest are skipped. Without a
      match the policy limits nothing. Open connections switch rules as conditions change, e.g. at
      night
    </Typography>
    <ArrayInput source="rules" label={false}>
      <SimpleFormIterator
        fullWidth
        disableClear
        disabled={readOnly}
        getItemLabel={(index) => `Rule ${index + 1}`}
        addButton={<AddItemButton label="Add rule" />}
      >
        <TextInput
          source="name"
          readOnly={readOnly}
          validate={required()}
          helperText="E.g. Working hours"
        />
        <UnreachableRuleWarning />
        <Typography variant="subtitle2">When</Typography>
        <ConditionInputs readOnly={readOnly} />
        <RuleLimits readOnly={readOnly} />
      </SimpleFormIterator>
    </ArrayInput>

    {/* Where periods start matters only with quotas. */}
    <FormDataConsumer>
      {({ formData }) =>
        hasQuotas(formData.rules) &&
        (formData.isGlobal ? (
          <DateInput
            source="globalStartsOn"
            label="Periods start on"
            readOnly={readOnly}
            validate={required()}
            helperText="UTC. Periods follow one another from this day, e.g. monthly from the 1st"
          />
        ) : (
          <Typography variant="body2" color="text.secondary">
            Periods count from the day set on each account or network the policy is assigned to: the
            day of assigning, unless changed there
          </Typography>
        ))
      }
    </FormDataConsumer>
  </>
)
