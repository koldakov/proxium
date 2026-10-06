import { Typography } from '@mui/material'
import {
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
} from 'react-admin'

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

/** Read-only, an empty list of limits says so instead of showing nothing under its heading. */
const NoLimits = ({ field }: { field: 'connectionLimits' | 'speedLimits' | 'trafficQuotas' }) => (
  <FormDataConsumer>
    {({ formData }) =>
      formData.rules?.[0]?.[field]?.length ? null : (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          No limits
        </Typography>
      )
    }
  </FormDataConsumer>
)

/** The fields of a policy, shared by create and edit, read-only on the show page. */
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
      Connections
    </Typography>
    {readOnly && <NoLimits field="connectionLimits" />}
    <ArrayInput source="rules.0.connectionLimits" label={false}>
      {/* The iterator holds the add and remove buttons. */}
      <SimpleFormIterator inline disableReordering disabled={readOnly}>
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

    <Typography variant="subtitle1" sx={{ mt: 2 }}>
      Speed
    </Typography>
    {readOnly && <NoLimits field="speedLimits" />}
    <ArrayInput source="rules.0.speedLimits" label={false}>
      <SimpleFormIterator inline disableReordering disabled={readOnly}>
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

    <Typography variant="subtitle1" sx={{ mt: 2 }}>
      Traffic
    </Typography>
    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
      Per account or network. Past a quota new connections are refused and open ones are cut
    </Typography>
    {readOnly && <NoLimits field="trafficQuotas" />}
    <ArrayInput source="rules.0.trafficQuotas" label={false}>
      <SimpleFormIterator inline disableReordering disabled={readOnly}>
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
    {/* Where periods start matters only with quotas. */}
    <FormDataConsumer>
      {({ formData }) =>
        formData.rules?.[0]?.trafficQuotas?.length > 0 &&
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
