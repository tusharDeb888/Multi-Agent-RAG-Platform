/**
 * Secure Storage Service
 * Wraps localStorage to enforce user isolation by scoping keys.
 */

const GLOBAL_KEYS = ['token', 'user'];

const getCurrentUser = () => {
    try {
        const userStr = localStorage.getItem('user');
        return userStr ? JSON.parse(userStr) : null;
    } catch (e) {
        return null;
    }
};

const getScopedKey = (key) => {
    if (GLOBAL_KEYS.includes(key)) return key;

    const user = getCurrentUser();
    // Use username or id for scoping. Fallback to 'guest'
    const scope = user ? (user.username || user.id) : 'guest';
    return `${key}_${scope}`;
};

const setItem = (key, value) => {
    if (value === undefined || value === null) {
        console.warn(`SecureStorage: Attempted to set null/undefined for key ${key}`);
        return;
    }
    const scopedKey = getScopedKey(key);
    // Auto-stringify if object/array
    const valToStore = typeof value === 'object' ? JSON.stringify(value) : value;
    localStorage.setItem(scopedKey, valToStore);
};

const getItem = (key, parseJson = true) => {
    const scopedKey = getScopedKey(key);
    const value = localStorage.getItem(scopedKey);

    if (!value) return null;

    if (parseJson) {
        try {
            return JSON.parse(value);
        } catch (e) {
            // Return raw if parse fails (maybe it wasn't JSON)
            return value;
        }
    }
    return value;
};

const removeItem = (key) => {
    const scopedKey = getScopedKey(key);
    localStorage.removeItem(scopedKey);
};

// Utilities for 'nuclear' options
const clearAll = () => {
    localStorage.clear();
};

const clearUserSession = () => {
    // Clear only current user's scoped keys (harder to implement perfectly without tracking)
    // For now, reliance on specific removeItem calls is better.
    // Or we could iterate and delete anything matching current scope.
    const user = getCurrentUser();
    const scope = user ? (user.username || user.id) : 'guest';

    Object.keys(localStorage).forEach(k => {
        if (k.endsWith(`_${scope}`)) {
            localStorage.removeItem(k);
        }
    });
};

export default {
    setItem,
    getItem,
    removeItem,
    clearAll,
    clearUserSession
};
