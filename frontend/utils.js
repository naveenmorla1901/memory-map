// src/utils/api.js
import authService from '../services/authService';

const API_URL = 'http://localhost:8000/api';

export const handleResponse = async (response) => {
    const data = await response.json();
    if (!response.ok) {
        if (response.status === 401) {
            // Token expired or invalid
            authService.logout();
            window.location.reload();
        }
        throw new Error(data.error || 'Something went wrong');
    }
    return data;
};

export const handleError = (error) => {
    console.error('API Error:', error);
    return {
        error: error.message || 'Something went wrong'
    };
};

export const api = {
    get: async (endpoint) => {
        try {
            const response = await fetch(`${API_URL}${endpoint}`, {
                headers: {
                    ...authService.getAuthHeader()
                }
            });
            return handleResponse(response);
        } catch (error) {
            return handleError(error);
        }
    },

    post: async (endpoint, data) => {
        try {
            const response = await fetch(`${API_URL}${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...authService.getAuthHeader()
                },
                body: JSON.stringify(data)
            });
            return handleResponse(response);
        } catch (error) {
            return handleError(error);
        }
    },

    put: async (endpoint, data) => {
        try {
            const response = await fetch(`${API_URL}${endpoint}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    ...authService.getAuthHeader()
                },
                body: JSON.stringify(data)
            });
            return handleResponse(response);
        } catch (error) {
            return handleError(error);
        }
    },

    delete: async (endpoint) => {
        try {
            const response = await fetch(`${API_URL}${endpoint}`, {
                method: 'DELETE',
                headers: {
                    ...authService.getAuthHeader()
                }
            });
            return handleResponse(response);
        } catch (error) {
            return handleError(error);
        }
    }
};

// src/utils/validation.js
export const validateEmail = (email) => {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
};

export const validatePassword = (password) => {
    // At least 8 characters, 1 uppercase, 1 lowercase, 1 number
    const re = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[a-zA-Z\d]{8,}$/;
    return re.test(password);
};

export const validateUsername = (username) => {
    // 3-20 characters, letters, numbers, underscores, hyphens
    const re = /^[a-zA-Z0-9_-]{3,20}$/;
    return re.test(username);
};
