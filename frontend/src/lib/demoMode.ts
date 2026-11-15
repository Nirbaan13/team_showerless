/** Explicit v1 build switch; ordinary builds retain their existing behavior. */
export const DEMO_REAL_ONLY = import.meta.env.VITE_DEMO_REAL_ONLY === 'true';

/** Separate storage prevents mock-era records from entering a real-only session. */
export const VERIFICATION_STORAGE_KEY = DEMO_REAL_ONLY ? 'spherex_real_community_comments' : 'spherex_community_comments';
