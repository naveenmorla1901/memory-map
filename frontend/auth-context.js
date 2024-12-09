// src/context/AuthContext.js
import React, { createContext, useState, useContext, useEffect } from 'react';
import authService from '../services/authService';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const initAuth = () => {
            const storedUser = authService.getCurrentUser();
            if (storedUser) {
                setUser(storedUser);
            }
            setLoading(false);
        };
        initAuth();
    }, []);

    const login = async (username, password) => {
        try {
            setError(null);
            const response = await authService.login(username, password);
            if (response.user) {
                setUser(response.user);
                return { success: true };
            } else {
                setError(response.error || 'Login failed');
                return { success: false, error: response.error };
            }
        } catch (err) {
            const errorMessage = err.response?.data?.error || 'Login failed';
            setError(errorMessage);
            return { success: false, error: errorMessage };
        }
    };

    const register = async (userData) => {
        try {
            setError(null);
            const response = await authService.register(
                userData.username,
                userData.email,
                userData.password,
                userData.password2,
                userData.firstName,
                userData.lastName
            );
            if (response.user) {
                setUser(response.user);
                return { success: true };
            } else {
                setError(response.error || 'Registration failed');
                return { success: false, error: response.error };
            }
        } catch (err) {
            const errorMessage = err.response?.data?.error || 'Registration failed';
            setError(errorMessage);
            return { success: false, error: errorMessage };
        }
    };

    const logout = () => {
        authService.logout();
        setUser(null);
    };

    const updateProfile = async (profileData) => {
        try {
            const response = await authService.updateProfile(profileData);
            if (response.user) {
                setUser(response.user);
                return { success: true };
            }
            return { success: false, error: response.error };
        } catch (err) {
            return { success: false, error: 'Failed to update profile' };
        }
    };

    const clearError = () => setError(null);

    const value = {
        user,
        loading,
        error,
        login,
        register,
        logout,
        updateProfile,
        clearError
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};
