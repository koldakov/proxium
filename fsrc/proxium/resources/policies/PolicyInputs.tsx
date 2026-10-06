import { Typography } from '@mui/material'
import {
  ArrayInput,
  BooleanInput,
  NumberInput,
  SelectInput,
  SimpleFormIterator,
  TextInput,
  minValue,
  required,
} from 'react-admin'

import {
  DIRECTIONS,
  LIMIT_SCOPES,
  formatMbits,
  formatMegabytes,
  parseMbits,
  parseMegabytes,
} from './limits'

/** The fields of a policy, shared by create and edit. */
export const PolicyInputs = () => (
  <>
    <TextInput source="name" validate={required()} helperText="E.g. Basic 50 Mbit/s" />
    <BooleanInput source="isActive" label="Active" helperText="Off: the policy applies to no one" />
    <BooleanInput
      source="isGlobal"
      label="Global"
      helperText="Applies to every client. Otherwise assign it on the page of an account or network"
    />

    <Typography variant="subtitle1" sx={{ mt: 2 }}>
      Connections
    </Typography>
    <ArrayInput source="rules.0.connectionLimits" label={false}>
      <SimpleFormIterator inline disableReordering>
        <SelectInput source="scope" choices={LIMIT_SCOPES} validate={required()} />
        <NumberInput
          source="maxConnections"
          label="At most"
          validate={[required(), minValue(1)]}
          helperText="Open at once, more are refused"
        />
      </SimpleFormIterator>
    </ArrayInput>

    <Typography variant="subtitle1" sx={{ mt: 2 }}>
      Speed
    </Typography>
    <ArrayInput source="rules.0.speedLimits" label={false}>
      <SimpleFormIterator inline disableReordering>
        <SelectInput source="scope" choices={LIMIT_SCOPES} validate={required()} />
        <SelectInput
          source="direction"
          choices={DIRECTIONS}
          defaultValue="both"
          validate={required()}
        />
        <NumberInput
          source="rate"
          label="Mbit/s"
          format={formatMbits}
          parse={parseMbits}
          validate={[required(), minValue(1)]}
          helperText="Shared by the connections in scope"
        />
        <NumberInput
          source="burst"
          label="Burst, MB"
          format={formatMegabytes}
          parse={parseMegabytes}
          validate={minValue(1)}
          helperText="At once after a pause. Empty: one second of the rate"
        />
      </SimpleFormIterator>
    </ArrayInput>
  </>
)
