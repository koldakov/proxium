// Where the FastAPI app lives, override with VITE_API_URL.
export const apiUrl: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
