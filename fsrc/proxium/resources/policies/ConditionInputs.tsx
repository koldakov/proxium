import { Typography } from '@mui/material'
import {
  AddItemButton,
  ArrayInput,
  AutocompleteInput,
  BooleanInput,
  CheckboxGroupInput,
  FormDataConsumer,
  SelectInput,
  SimpleFormIterator,
  TextInput,
  required,
} from 'react-admin'

import {
  CONDITION_KINDS,
  CONDITION_MATCHES,
  LIST_HELPER,
  PROTOCOLS,
  TIME_ZONES,
  WEEKDAYS,
  browserTimeZone,
  domainsList,
  networksList,
  portsList,
} from './conditions'

// The time input shows a placeholder of its own: the label stays above it.
const SHRUNK_LABEL = { inputLabel: { shrink: true } }

/** The fields of one check, by its kind. */
const BlockParams = ({ readOnly }: { readOnly: boolean }) => (
  <FormDataConsumer>
    {({ scopedFormData }) => {
      switch (scopedFormData?.kind) {
        case 'schedule':
          return (
            <>
              <CheckboxGroupInput
                source="days"
                choices={WEEKDAYS}
                readOnly={readOnly}
                validate={required()}
              />
              <TextInput
                source="start"
                type="time"
                defaultValue="09:00"
                slotProps={SHRUNK_LABEL}
                readOnly={readOnly}
                validate={required()}
              />
              <TextInput
                source="end"
                type="time"
                defaultValue="18:00"
                slotProps={SHRUNK_LABEL}
                readOnly={readOnly}
                validate={required()}
                helperText="Before the start: till the next day. Same as the start: all day"
              />
              <AutocompleteInput
                source="timezone"
                label="Time zone"
                choices={TIME_ZONES}
                defaultValue={browserTimeZone()}
                readOnly={readOnly}
                validate={required()}
              />
            </>
          )
        case 'target_host':
          return (
            <TextInput
              source="domains"
              multiline
              readOnly={readOnly}
              validate={domainsList()}
              helperText={`Subdomains match too. ${LIST_HELPER}`}
            />
          )
        case 'target_network':
          return (
            <TextInput
              source="networks"
              multiline
              readOnly={readOnly}
              validate={networksList()}
              helperText={`When the client asks for an IP, not a name. ${LIST_HELPER}`}
            />
          )
        case 'client_network':
          return (
            <TextInput
              source="networks"
              multiline
              readOnly={readOnly}
              validate={networksList()}
              helperText={`Where the client connects from. ${LIST_HELPER}`}
            />
          )
        case 'target_port':
          return (
            <TextInput
              source="ports"
              readOnly={readOnly}
              validate={portsList()}
              helperText="E.g. 80, 443, 8000-8999"
            />
          )
        case 'protocol':
          return (
            <CheckboxGroupInput
              source="protocols"
              choices={PROTOCOLS}
              readOnly={readOnly}
              validate={required()}
            />
          )
        default:
          return null
      }
    }}
  </FormDataConsumer>
)

/** When a rule applies: checks that all must match or any one, none for always. Inside a rule of the form. */
export const ConditionInputs = ({ readOnly }: { readOnly: boolean }) => (
  <FormDataConsumer>
    {({ scopedFormData }) => {
      // A deeper tree than the form shows: saved untouched.
      if (scopedFormData?.complexCondition) {
        return (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Set through the API and kept as is: the form can't show it
          </Typography>
        )
      }

      const count = scopedFormData?.blocks?.length ?? 0
      return (
        <>
          {count === 0 && (
            <Typography variant="body2" color="text.secondary">
              No conditions: the rule always applies
            </Typography>
          )}
          {count > 1 && (
            <SelectInput
              source="match"
              label="Applies when"
              choices={CONDITION_MATCHES}
              defaultValue="all"
              readOnly={readOnly}
              validate={required()}
            />
          )}
          <ArrayInput source="blocks" label={false}>
            <SimpleFormIterator
              inline
              disableReordering
              disableClear
              disabled={readOnly}
              addButton={<AddItemButton label="Add condition" />}
            >
              <SelectInput
                source="kind"
                label="Condition"
                choices={CONDITION_KINDS}
                readOnly={readOnly}
                validate={required()}
              />
              <BooleanInput
                source="negate"
                label="Not"
                defaultValue={false}
                readOnly={readOnly}
                helperText="Matches when this doesn't"
              />
              <BlockParams readOnly={readOnly} />
            </SimpleFormIterator>
          </ArrayInput>
        </>
      )
    }}
  </FormDataConsumer>
)
