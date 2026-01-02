import api from './api';
import { jwtDecode } from "jwt-decode";
import storageService from './storageService';

const login = async (username, password) => {
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);

    const response = await api.post('/auth/login', formData, {
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
    });

    if (response.data.access_token) {
        storageService.setItem('token', response.data.access_token);
        storageService.setItem('user', response.data.user); // Store full user info incl roles
    }

    return response.data;
};

const logout = () => {
    storageService.removeItem('token');
    storageService.removeItem('chat_session_messages'); // Clear chat history (Must be before removing user to preserve scope)
    storageService.removeItem('user');
};

const getCurrentUser = () => {
    return storageService.getItem('user');
};

const isAuthenticated = () => {
    const token = storageService.getItem('token', false);
    if (!token) return false;

    try {
        const decoded = jwtDecode(token);
        const currentTime = Date.now() / 1000;
        if (decoded.exp < currentTime) {
            logout();
            return false;
        }
        return true;
    } catch (e) {
        return false;
    }
};

const getToken = () => {
    return storageService.getItem('token', false);
};

export default {
    login,
    logout,
    getCurrentUser,
    isAuthenticated,
    getToken
};
