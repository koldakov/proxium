import { SearchInput, type SearchInputProps } from 'react-admin'

/**
 * `SearchInput` that Safari doesn't take for a login field and fill with saved passwords.
 *
 * Give `source` and `alwaysOn` on the element: react-admin reads them from the `filters` entry itself.
 */
export const QuerySearchInput = ({ sx, ...props }: SearchInputProps) => (
  <SearchInput
    type="search"
    autoComplete="off"
    // WebKit draws its own clear button for `type="search"`, next to the react-admin one.
    sx={[
      { '& input::-webkit-search-cancel-button': { WebkitAppearance: 'none', display: 'none' } },
      ...(Array.isArray(sx) ? sx : [sx]),
    ]}
    {...props}
  />
)
