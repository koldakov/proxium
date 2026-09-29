/** Rejects a date not in the future. Empty passes: pair with `required()` if needed. */
export const future = () => (value: string | null) =>
  value && new Date(value) <= new Date() ? 'Must be in the future' : undefined
